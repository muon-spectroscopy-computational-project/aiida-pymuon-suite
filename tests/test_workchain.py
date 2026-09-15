"""End-to-end tests for MuairssUepWorkChain and cluster_muon_sites calcfunction."""

import io
import os

from aiida.engine import run, run_get_node
from aiida.orm import Dict, FolderData, SinglefileData, StructureData
from aiida.plugins import DataFactory, WorkflowFactory
from aiida.repository import FileType

from . import TEST_DIR


def _list_files_recursive(folder_data, path=None):
    """Return all file paths (relative to folder root) under path in a FolderData."""
    results = []
    for obj in folder_data.list_objects(path):
        obj_path = f"{path}/{obj.name}" if path else obj.name
        if obj.file_type == FileType.DIRECTORY:
            results.extend(_list_files_recursive(folder_data, obj_path))
        else:
            results.append(obj_path)
    return results


# ---------------------------------------------------------------------------
# MuairssUepWorkChain end-to-end (requires pm-muairss + pm-uep-opt + daemon)
# ---------------------------------------------------------------------------


def test_muairss_uep_workchain(muairss_code, uep_opt_code):
    """Run MuairssUepWorkChain on Si; assert muon_sites has .uep files and exit code 0."""
    UepParameters = DataFactory("pymuon.uep")
    parameters = UepParameters({"geom_steps": 30})

    structure_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.cell"))
    charge_density_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.den_fmt"))
    castep_log_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.castep"))

    inputs = {
        "muairss_code": muairss_code,
        "uep_code": uep_opt_code,
        "structure": structure_file,
        "charge_density": charge_density_file,
        "castep_log": castep_log_file,
        "parameters": parameters,
    }

    result, node = run_get_node(WorkflowFactory("pymuon.muairss_uep"), **inputs)

    assert node.is_finished_ok, f"WorkChain finished with exit status {node.exit_status}: {node.exit_message}"
    assert "muon_sites" in result

    muon_sites = result["muon_sites"]
    assert isinstance(muon_sites, FolderData)

    all_files = _list_files_recursive(muon_sites)
    uep_files = [f for f in all_files if f.endswith(".uep")]
    assert len(uep_files) > 0, f"Expected at least one .uep file in muon_sites; got: {all_files}"

    # Each .uep file should sit under a candidate-named subdirectory.
    for uep in uep_files:
        assert "/" in uep, f".uep file not nested under candidate dir: {uep}"


# ---------------------------------------------------------------------------
# cluster_muon_sites calcfunction
# ---------------------------------------------------------------------------


def test_cluster_calcfunction(muairss_code, uep_opt_code):
    """Run the WorkChain to obtain a real muon_sites FolderData, then cluster it."""
    from aiida_pymuon_suite.workflows.muairss_uep import cluster_muon_sites

    UepParameters = DataFactory("pymuon.uep")
    parameters = UepParameters({"geom_steps": 30})

    structure_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.cell"))
    charge_density_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.den_fmt"))
    castep_log_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.castep"))

    wc_result, wc_node = run_get_node(
        WorkflowFactory("pymuon.muairss_uep"),
        **{
            "muairss_code": muairss_code,
            "uep_code": uep_opt_code,
            "structure": structure_file,
            "charge_density": charge_density_file,
            "castep_log": castep_log_file,
            "parameters": parameters,
        },
    )
    assert wc_node.is_finished_ok
    muon_sites = wc_result["muon_sites"]

    # cluster_muon_sites is a calcfunction; inputs must be stored AiiDA nodes.
    structure_file.store()
    cluster_result = run(
        cluster_muon_sites,
        structure=structure_file,
        muon_sites=muon_sites,
        parameters=parameters,
    )

    assert "cluster_report" in cluster_result
    assert "cluster_data" in cluster_result

    report = cluster_result["cluster_report"]
    assert isinstance(report, SinglefileData)
    content = report.get_content()
    assert len(content) > 0, "cluster_report should not be empty"

    cluster_data = cluster_result["cluster_data"]
    assert isinstance(cluster_data, Dict)
    # cluster_data should be a non-empty mapping when there are candidates.
    assert cluster_data.get_dict(), "cluster_data Dict should be non-empty"

    # One StructureData per cluster, keyed to match the "Cluster N" headings in the
    # report, each carrying the muon as its own Kind.
    site_structures = cluster_result["site_structures"]
    assert site_structures, "site_structures should be non-empty when there are candidates"

    n_clusters = sum(len(entries) for entries in cluster_data.get_dict().values())
    assert len(site_structures) == n_clusters, "one structure per cluster"
    assert set(site_structures) == {f"cluster_{i + 1}" for i in range(n_clusters)}

    for key, site in site_structures.items():
        assert isinstance(site, StructureData), key
        muon_kinds = [k for k in site.kinds if k.name != k.symbol]
        assert len(muon_kinds) == 1, f"{key} should have exactly one muon kind"
        assert muon_kinds[0].symbol == "H", f"{key} muon should be an H kind"


def test_cluster_calcfunction_kmeans(muairss_code, uep_opt_code):
    """Re-cluster the same muon_sites with kmeans to exercise the alternative branch."""
    from aiida_pymuon_suite.workflows.muairss_uep import cluster_muon_sites

    UepParameters = DataFactory("pymuon.uep")
    base_params = UepParameters({"geom_steps": 30})

    structure_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.cell"))
    charge_density_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.den_fmt"))
    castep_log_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.castep"))

    wc_result, wc_node = run_get_node(
        WorkflowFactory("pymuon.muairss_uep"),
        **{
            "muairss_code": muairss_code,
            "uep_code": uep_opt_code,
            "structure": structure_file,
            "charge_density": charge_density_file,
            "castep_log": castep_log_file,
            "parameters": base_params,
        },
    )
    assert wc_node.is_finished_ok
    muon_sites = wc_result["muon_sites"]

    kmeans_params = UepParameters(
        {
            "geom_steps": 30,
            "clustering_method": "kmeans",
            "clustering_kmeans_k": 2,
        }
    )

    structure_file.store()
    result = run(
        cluster_muon_sites,
        structure=structure_file,
        muon_sites=muon_sites,
        parameters=kmeans_params,
    )

    assert isinstance(result["cluster_report"], SinglefileData)
    assert result["cluster_report"].get_content()
    assert isinstance(result["cluster_data"], Dict)
    assert result["site_structures"], "kmeans clustering should also yield site structures"
    assert all(isinstance(s, StructureData) for s in result["site_structures"].values())


# ---------------------------------------------------------------------------
# Cluster structure collection (no codes / profile needed)
# ---------------------------------------------------------------------------


def test_find_cluster_structures(tmp_path):
    """The saved minimum-energy structures are found in both possible layouts."""
    from aiida_pymuon_suite.workflows.muairss_uep import _find_cluster_structures

    # Where they actually land: params["name"] is an absolute path, so the seedname is
    # absolute and os.path.join drops the clustering save folder.
    (tmp_path / "muon_uep_min_cluster_1.cell").write_text("cluster 1")
    (tmp_path / "muon_uep_min_cluster_2.cell").write_text("cluster 2")
    # Where they would land if that were fixed upstream.
    (tmp_path / "muon_clusters" / "uep").mkdir(parents=True)
    (tmp_path / "muon_clusters" / "uep" / "muon_uep_min_cluster_3.cell").write_text("cluster 3")
    # Everything else in the temp dir must be ignored.
    (tmp_path / "muon_clusters.txt").write_text("the report")
    (tmp_path / "muon_muon_uep_clusters.dat").write_text("raw cluster data")
    (tmp_path / "Si.cell").write_text("the input structure")
    candidate = tmp_path / "muon-airss-out" / "uep" / "struct_1"
    candidate.mkdir(parents=True)
    (candidate / "struct_1.cell").write_text("a candidate, not a cluster")

    found = sorted(p.name for p in _find_cluster_structures(tmp_path, "muon"))
    assert found == [
        "muon_uep_min_cluster_1.cell",
        "muon_uep_min_cluster_2.cell",
        "muon_uep_min_cluster_3.cell",
    ]


def test_find_cluster_structures_none_saved(tmp_path):
    """No structures saved (clustering_save_type unset) yields an empty list."""
    from aiida_pymuon_suite.workflows.muairss_uep import _find_cluster_structures

    (tmp_path / "muon_clusters.txt").write_text("the report")
    assert _find_cluster_structures(tmp_path, "muon") == []


# ---------------------------------------------------------------------------
# ASE -> StructureData conversion (needs a profile, no codes)
# ---------------------------------------------------------------------------


def _muonated_atoms():
    """Si cell with a muon last, labelled the way pymuonsuite labels it."""
    import numpy as np
    from ase import Atoms

    atoms = Atoms(
        symbols=["Si", "Si", "H"],
        positions=[(0.0, 0.0, 0.0), (1.3575, 1.3575, 1.3575), (2.715, 2.715, 2.715)],
        cell=[(0.0, 2.715, 2.715), (2.715, 0.0, 2.715), (2.715, 2.715, 0.0)],
        pbc=True,
    )
    atoms.set_array("castep_custom_species", np.array(["Si", "Si", "H:mu"]))
    return atoms


def test_structure_data_gives_the_muon_its_own_kind():
    """H:mu must become a Kind named 'mu', or CASTEP sees ordinary hydrogen."""
    from aiida_pymuon_suite.workflows.muairss_uep import _structure_data_from_atoms

    structure = _structure_data_from_atoms(_muonated_atoms())

    assert [(k.name, k.symbol) for k in structure.kinds] == [("Si", "Si"), ("mu", "H")]
    assert structure.sites[-1].kind_name == "mu"
    assert structure.pbc == (True, True, True)


def test_structure_data_without_custom_species_falls_back_to_symbols():
    """A plain Atoms (no muon label) converts with kind names equal to symbols."""
    from aiida_pymuon_suite.workflows.muairss_uep import _structure_data_from_atoms

    atoms = _muonated_atoms()
    del atoms.arrays["castep_custom_species"]

    structure = _structure_data_from_atoms(atoms)

    assert [(k.name, k.symbol) for k in structure.kinds] == [("Si", "Si"), ("H", "H")]


# ---------------------------------------------------------------------------
# Charge-density validation
# ---------------------------------------------------------------------------


def _folder_with_density(content: bytes):
    """FolderData holding a single .den_fmt with the given content."""
    folder = FolderData()
    folder.put_object_from_filelike(io.BytesIO(content), "aiida.den_fmt")
    return folder


def test_density_with_a_castep_header_is_accepted():
    from aiida_pymuon_suite.workflows.castep_muairss_uep import find_valid_density

    folder = _folder_with_density(b"     BEGIN header\n   Real Lattice(A)\n 0.0 2.7 2.7\n")

    assert find_valid_density(folder) == "aiida.den_fmt"


def test_density_without_a_header_is_rejected():
    """A placeholder .den_fmt must not pass as a charge density.

    pm-uep-opt only reports "FMT file has no header" after every UepOptCalculation
    has been submitted and run, so the whole workflow fails slowly and obscurely.
    """
    from aiida_pymuon_suite.workflows.castep_muairss_uep import find_valid_density

    assert find_valid_density(_folder_with_density(b"density")) is None


def test_folder_without_a_density_is_rejected():
    from aiida_pymuon_suite.workflows.castep_muairss_uep import find_valid_density

    folder = FolderData()
    folder.put_object_from_filelike(io.BytesIO(b"whatever"), "aiida.castep")

    assert find_valid_density(folder) is None
