"""End-to-end tests for MuairssUepWorkChain and cluster_muon_sites calcfunction."""

import os

from aiida.engine import run, run_get_node
from aiida.orm import Dict, FolderData, SinglefileData
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

    assert node.is_finished_ok, (
        f"WorkChain finished with exit status {node.exit_status}: {node.exit_message}"
    )
    assert "muon_sites" in result

    muon_sites = result["muon_sites"]
    assert isinstance(muon_sites, FolderData)

    all_files = _list_files_recursive(muon_sites)
    uep_files = [f for f in all_files if f.endswith(".uep")]
    assert len(uep_files) > 0, (
        f"Expected at least one .uep file in muon_sites; got: {all_files}"
    )

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

    wc_result, wc_node = run_get_node(WorkflowFactory("pymuon.muairss_uep"), **{
        "muairss_code": muairss_code,
        "uep_code": uep_opt_code,
        "structure": structure_file,
        "charge_density": charge_density_file,
        "castep_log": castep_log_file,
        "parameters": parameters,
    })
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


def test_cluster_calcfunction_kmeans(muairss_code, uep_opt_code):
    """Re-cluster the same muon_sites with kmeans to exercise the alternative branch."""
    from aiida_pymuon_suite.workflows.muairss_uep import cluster_muon_sites

    UepParameters = DataFactory("pymuon.uep")
    base_params = UepParameters({"geom_steps": 30})

    structure_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.cell"))
    charge_density_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.den_fmt"))
    castep_log_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.castep"))

    wc_result, wc_node = run_get_node(WorkflowFactory("pymuon.muairss_uep"), **{
        "muairss_code": muairss_code,
        "uep_code": uep_opt_code,
        "structure": structure_file,
        "charge_density": charge_density_file,
        "castep_log": castep_log_file,
        "parameters": base_params,
    })
    assert wc_node.is_finished_ok
    muon_sites = wc_result["muon_sites"]

    kmeans_params = UepParameters({
        "geom_steps": 30,
        "clustering_method": "kmeans",
        "clustering_kmeans_k": 2,
    })

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
