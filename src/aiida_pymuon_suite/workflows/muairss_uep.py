"""MuairssUepWorkChain and cluster_muon_sites calcfunction."""

import io
import tempfile
from pathlib import Path

from aiida.engine import ToContext, WorkChain, calcfunction
from aiida.orm import AbstractCode, Data, Dict, FolderData, SinglefileData
from aiida.plugins import CalculationFactory, DataFactory
from aiida.repository import FileType

MuairssCalculation = CalculationFactory("pymuon.muairss")
UepOptCalculation = CalculationFactory("pymuon.uep_opt")
UepParameters = DataFactory("pymuon.uep")


@calcfunction
def merge_uep_results(**kwargs):
    """Merge per-candidate uep_result FolderDatas into one, keyed by candidate name."""
    merged = FolderData()
    for candidate_name, folder in kwargs.items():
        for filepath in _list_files_recursive(folder):
            dest = f"{candidate_name}/{filepath}"
            with folder.open(filepath, "rb") as f:
                merged.put_object_from_filelike(f, dest)
    return merged


def _list_files_recursive(folder_data, path=None):
    """Return all file paths (relative to folder root) under path."""
    results = []
    for obj in folder_data.list_objects(path):
        obj_path = f"{path}/{obj.name}" if path else obj.name
        if obj.file_type == FileType.DIRECTORY:
            results.extend(_list_files_recursive(folder_data, obj_path))
        else:
            results.append(obj_path)
    return results


def _restore_folder_data(folder_data, dest_path):
    """Write all files in a FolderData into dest_path, preserving tree structure."""
    dest_path = Path(dest_path)
    for filepath in _list_files_recursive(folder_data):
        full_dest = dest_path / filepath
        full_dest.parent.mkdir(parents=True, exist_ok=True)
        with folder_data.open(filepath, "rb") as src:
            full_dest.write_bytes(src.read())


class MuairssUepWorkChain(WorkChain):
    """WorkChain: MuairssCalculation → fan-out UepOptCalculation per candidate → collect results."""

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input("muairss_code", valid_type=AbstractCode, help="pm-muairss executable.")
        spec.input("uep_code", valid_type=AbstractCode, help="pm-uep-opt executable.")
        spec.input("structure", valid_type=SinglefileData, help="Crystal structure file.")
        spec.input("charge_density", valid_type=SinglefileData, help="CASTEP charge density (.den_fmt).")
        spec.input("castep_log", valid_type=SinglefileData, help="CASTEP log file (.castep).")
        spec.input("parameters", valid_type=UepParameters, help="UEP parameters.")

        spec.outline(
            cls.run_muairss,
            cls.inspect_muairss,
            cls.inspect_uep_opt,
            cls.collect_results,
        )

        spec.output("muon_sites", valid_type=FolderData, help="All .uep results merged into one FolderData.")

        spec.exit_code(400, "ERROR_MUAIRSS_FAILED", message="MuairssCalculation failed.")
        spec.exit_code(401, "ERROR_ALL_UEP_FAILED", message="All UepOptCalculations failed.")
        spec.exit_code(402, "ERROR_PARTIAL_UEP_FAIL", message="More than 10% of UepOptCalculations failed.")

    def run_muairss(self):
        inputs = {
            "code": self.inputs.muairss_code,
            "structure": self.inputs.structure,
            "parameters": self.inputs.parameters,
        }
        future = self.submit(MuairssCalculation, **inputs)
        self.report(f"Submitted MuairssCalculation <{future.pk}>")
        return ToContext(muairss_calc=future)

    def inspect_muairss(self):
        calc = self.ctx.muairss_calc
        if not calc.is_finished_ok:
            self.report(f"MuairssCalculation failed with exit code {calc.exit_status}")
            return self.exit_codes.ERROR_MUAIRSS_FAILED

        folder = calc.outputs.candidates_folder
        yaml_paths = [p for p in _list_files_recursive(folder) if p.endswith(".yaml")]
        self.report(f"Found {len(yaml_paths)} candidate YAMLs — fanning out UepOptCalculations.")

        futures = {}
        for yaml_path in yaml_paths:
            with folder.open(yaml_path, "rb") as f:
                yaml_node = SinglefileData(file=f, filename=Path(yaml_path).name)
            yaml_node.store()

            key = f"uep_{Path(yaml_path).stem}"
            future = self.submit(
                UepOptCalculation,
                code=self.inputs.uep_code,
                candidate_yaml=yaml_node,
                charge_density=self.inputs.charge_density,
                castep_log=self.inputs.castep_log,
                parameters=self.inputs.parameters,
            )
            futures[key] = future

        self.ctx.uep_keys = list(futures.keys())
        return ToContext(**futures)

    def inspect_uep_opt(self):
        keys = self.ctx.uep_keys
        failed = [k for k in keys if not self.ctx[k].is_finished_ok]
        self.report(f"{len(keys) - len(failed)}/{len(keys)} UepOptCalculations succeeded.")

        if len(failed) == len(keys):
            return self.exit_codes.ERROR_ALL_UEP_FAILED
        if len(failed) / len(keys) > 0.10:
            return self.exit_codes.ERROR_PARTIAL_UEP_FAIL

    def collect_results(self):
        kwargs = {}
        for key in self.ctx.uep_keys:
            calc = self.ctx[key]
            if not calc.is_finished_ok:
                continue
            candidate_name = key[len("uep_"):]
            kwargs[candidate_name] = calc.outputs.uep_result

        muon_sites = merge_uep_results(**kwargs)
        self.out("muon_sites", muon_sites)
        self.report("Collected muon_sites FolderData.")


@calcfunction
def cluster_muon_sites(structure: SinglefileData, muon_sites: FolderData, parameters: UepParameters) -> dict[str, Data]:
    """Cluster UEP candidate sites using pymuonsuite directly (no scheduler job).

    Returns cluster_report (SinglefileData) and cluster_data (Dict).
    """
    import warnings
    from types import SimpleNamespace

    import yaml
    from ase import io as ase_io
    from pymuonsuite.muairss import load_muairss_collection, muairss_cluster
    from pymuonsuite.io.output import write_cluster_report

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Write structure
        struct_path = tmpdir / structure.filename
        struct_path.write_bytes(structure.get_content('rb'))

        # Restore muon-airss-out tree under a uep/ subdirectory
        import pickle
        out_path = tmpdir / "muon-airss-out"
        uep_path = out_path / "uep"
        _restore_folder_data(muon_sites, uep_path)

        # soprano load_tree (safety_check=2) requires a .collection pickle that
        # lists the subdirectory names; create it from the restored tree.
        candidate_dirs = sorted(d.name for d in uep_path.iterdir() if d.is_dir())
        with open(uep_path / ".collection", "wb") as _f:
            pickle.dump({"dirlist": candidate_dirs, "arrays": {}, "info": {}}, _f, protocol=2)

        # Build params dict
        params = parameters.get_dict()
        params.setdefault("name", "muon")
        params["out_folder"] = str(out_path)
        params["calculator"] = "uep"
        params.setdefault("clustering_method", "hier")
        params.setdefault("clustering_hier_t", 0.3)
        params.setdefault("clustering_kmeans_k", 4)
        params.setdefault("clustering_save_min", False)
        params.setdefault("clustering_save_type", None)
        params.setdefault("clustering_save_folder", None)

        struct = ase_io.read(str(struct_path))
        collection = load_muairss_collection(struct, params, batch_path=str(tmpdir))

        if not collection:
            return {
                "cluster_report": SinglefileData(
                    file=io.BytesIO(b"No results to cluster."), filename="muon_clusters.txt"
                ),
                "cluster_data": Dict(dict={}),
            }

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            clusters = muairss_cluster(struct, collection, params)

        # write_cluster_report opens params["name"] + "_clusters.txt" as a relative path.
        report_stem = str(tmpdir / params["name"])
        params_write = {**params, "name": report_stem}
        args = SimpleNamespace(structures=structure.filename, parameter_file="params.yaml")
        # write_cluster_report expects {structure_name: {calc: result}}
        write_cluster_report(args, params_write, {params["name"]: clusters})

        report_path = tmpdir / f"{params['name']}_clusters.txt"
        cluster_report = SinglefileData(file=str(report_path))

        # Build cluster_data: {calc_name: {cluster_id: {n, E_min}}}
        import numpy as np
        cluster_dict = {}
        for calc_name, (cl, classified, gvecs) in clusters.items():
            cinds = cl[0]  # cl is (cinds, cgroups); cinds is shape (n_structures,)
            cluster_dict[calc_name] = {}
            for cid in set(cinds.tolist()):
                mask = np.where(cinds == cid)[0]
                cluster_dict[calc_name][str(cid)] = {
                    "n": int(len(mask)),
                    "E_min": float(np.min(gvecs[mask, 0])),
                }

    return {
        "cluster_report": cluster_report,
        "cluster_data": Dict(dict=cluster_dict),
    }
