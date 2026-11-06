#!/usr/bin/env python
"""Run the full muon stopping sites workflow on localhost.

Usage:
    ./example_01.py --muairss-code pm-muairss@localhost --uep-code pm-uep-opt@localhost

    # Omit codes to auto-create them from PATH:
    ./example_01.py

    ./example_01.py --help
"""

from os import path

import click
from aiida import cmdline, engine
from aiida.orm import Int, SinglefileData
from aiida.plugins import DataFactory, WorkflowFactory
from aiida_pymuon_suite import helpers
from aiida_pymuon_suite.workflows.muairss_uep import cluster_muon_sites

INPUT_DIR = path.join(path.dirname(path.abspath(__file__)), "input_files")


def run_workflow(muairss_code, uep_code, max_concurrent):
    """Run MuairssUepWorkChain + cluster_muon_sites on the Si test case."""
    if not muairss_code:
        computer = helpers.get_computer()
        muairss_code = helpers.get_code(entry_point="pymuon.muairss", computer=computer)
    if not uep_code:
        computer = helpers.get_computer()
        uep_code = helpers.get_code(entry_point="pymuon.uep_opt", computer=computer)

    UepParameters = DataFactory("pymuon.uep")
    parameters = UepParameters(
        {
            "poisson_r": 0.8,
            "vdw_scale": 0.5,
            "geom_steps": 30,
            "geom_force_tol": 0.05,
            "uep_gw_factor": 5.0,
            "clustering_method": "hier",
            "clustering_hier_t": 0.3,
        }
    )

    structure = SinglefileData(file=path.join(INPUT_DIR, "Si.cell"))
    charge_density = SinglefileData(file=path.join(INPUT_DIR, "Si.den_fmt"))
    castep_log = SinglefileData(file=path.join(INPUT_DIR, "Si.castep"))

    # --- Step 1: run the WorkChain (muairss → fan-out UEP opt → collect) ---
    print("Running MuairssUepWorkChain ...")
    result, node = engine.run_get_node(
        WorkflowFactory("pymuon.muairss_uep"),
        muairss_code=muairss_code,
        uep_code=uep_code,
        structure=structure,
        charge_density=charge_density,
        castep_log=castep_log,
        parameters=parameters,
        max_concurrent=Int(max_concurrent),
    )

    if not node.is_finished_ok:
        print(f"WorkChain FAILED — exit status {node.exit_status}: {node.exit_message}")
        return

    muon_sites = result["muon_sites"]
    print(f"WorkChain finished OK (pk={node.pk})")

    from aiida.repository import FileType

    def list_files(folder, path=None):
        out = []
        for obj in folder.list_objects(path):
            p = f"{path}/{obj.name}" if path else obj.name
            if obj.file_type == FileType.DIRECTORY:
                out.extend(list_files(folder, p))
            else:
                out.append(p)
        return out

    uep_files = [f for f in list_files(muon_sites) if f.endswith(".uep")]
    print(f"  {len(uep_files)} candidate .uep files produced")

    # --- Step 2: cluster the muon sites ---
    print("\nClustering muon sites ...")
    cluster_result = engine.run(
        cluster_muon_sites,
        structure=structure,
        muon_sites=muon_sites,
        parameters=parameters,
    )

    print("\n--- Cluster report ---")
    print(cluster_result["cluster_report"].get_content())

    print("--- Cluster summary ---")
    for calc, clusters in cluster_result["cluster_data"].get_dict().items():
        print(f"Calculator: {calc}")
        for cid, info in sorted(clusters.items(), key=lambda x: x[1]["E_min"]):
            print(f"  Cluster {cid}: {info['n']} structures, E_min = {info['E_min']:.4f} eV")

    # One StructureData per cluster, ready to hand to a CASTEP geometry optimisation.
    print("--- Site structures ---")
    site_structures = cluster_result["site_structures"]
    for key in sorted(site_structures, key=lambda k: int(k.rpartition("_")[2])):
        site = site_structures[key]
        kinds = ", ".join(f"{k.name}({k.symbol})" for k in site.kinds)
        print(f"  {key}: StructureData<{site.pk}>, {len(site.sites)} atoms, kinds: {kinds}")


@click.command()
@cmdline.utils.decorators.with_dbenv()
@click.option(
    "--muairss-code",
    default=None,
    type=cmdline.params.types.CodeParamType(),
    help="pm-muairss code (e.g. pm-muairss@localhost). Created from PATH if omitted.",
)
@click.option(
    "--uep-code",
    default=None,
    type=cmdline.params.types.CodeParamType(),
    help="pm-uep-opt code (e.g. pm-uep-opt@localhost). Created from PATH if omitted.",
)
@click.option(
    "--max-concurrent",
    default=4,
    type=int,
    show_default=True,
    help="Maximum number of UepOptCalculations to run concurrently.",
)
def cli(muairss_code, uep_code, max_concurrent):
    """Run the muon stopping sites workflow on the Si test case."""
    run_workflow(muairss_code, uep_code, max_concurrent)


if __name__ == "__main__":
    cli()
