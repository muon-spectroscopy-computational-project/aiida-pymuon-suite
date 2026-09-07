"""Tests for calculations, parsers, and WorkChain."""

import os

import pytest
from aiida.engine import run
from aiida.orm import SinglefileData
from aiida.plugins import CalculationFactory, DataFactory

from . import TEST_DIR

# ---------------------------------------------------------------------------
# UepParameters (pure-Python, no AiiDA profile needed)
# ---------------------------------------------------------------------------


def test_parameter_validation():
    UepParameters = DataFactory("pymuon.uep")

    params = UepParameters({})
    assert params["poisson_r"] == 0.8
    assert params["vdw_scale"] == 0.5
    assert params["geom_steps"] == 30
    assert params["geom_force_tol"] == 0.05
    assert params["uep_gw_factor"] == 5.0
    assert params["mu_symbol"] == "H:mu"
    assert params["clustering_method"] == "hier"
    assert params["clustering_hier_t"] == pytest.approx(0.3)
    assert params["clustering_kmeans_k"] == 4

    params = UepParameters(
        {
            "poisson_r": 1.0,
            "vdw_scale": 0.25,
            "geom_steps": 100,
            "random_seed": 42,
            "allpos_ext": "xyz",
            "clustering_method": "kmeans",
            "clustering_kmeans_k": 3,
        }
    )
    assert params["poisson_r"] == 1.0
    assert params["random_seed"] == 42
    assert params["allpos_ext"] == "xyz"
    assert params["clustering_method"] == "kmeans"
    assert params["clustering_kmeans_k"] == 3


def test_render_yaml():
    UepParameters = DataFactory("pymuon.uep")

    params = UepParameters(
        {
            "poisson_r": 0.7,
            "vdw_scale": 0.8,
            "geom_steps": 25,
            "geom_force_tol": 0.02,
            "uep_gw_factor": 4.0,
            "allpos_ext": "cif",
        }
    )

    yaml_output = params.render_yaml()
    assert "calculator: uep" in yaml_output
    assert "charged: true" in yaml_output
    assert "out_folder: muon-airss-out" in yaml_output
    assert "poisson_r: 0.7" in yaml_output
    assert "allpos_filename: allpos.cif" in yaml_output
    assert "allpos_ext" not in yaml_output


# ---------------------------------------------------------------------------
# MuairssCalculation integration test (requires pm-muairss on PATH)
# ---------------------------------------------------------------------------


def test_muairss_calculation(muairss_code):
    UepParameters = DataFactory("pymuon.uep")
    parameters = UepParameters({"geom_steps": 30})

    structure_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.cell"))

    inputs = {
        "code": muairss_code,
        "parameters": parameters,
        "structure": structure_file,
        "metadata": {"options": {"max_wallclock_seconds": 300}},
    }

    result = run(CalculationFactory("pymuon.muairss"), **inputs)
    assert "candidates_folder" in result
    from aiida.repository import FileType

    folder = result["candidates_folder"]
    all_files = []

    def collect(fd, path=None):
        for obj in fd.list_objects(path):
            p = f"{path}/{obj.name}" if path else obj.name
            if obj.file_type == FileType.DIRECTORY:
                collect(fd, p)
            else:
                all_files.append(p)

    collect(folder)
    yaml_files = [f for f in all_files if f.endswith(".yaml")]
    assert len(yaml_files) > 0, "Expected at least one candidate YAML"


# ---------------------------------------------------------------------------
# UepOptCalculation integration test (requires pm-uep-opt on PATH)
# ---------------------------------------------------------------------------


def test_uep_opt_calculation(muairss_code, uep_opt_code):
    """Run MuairssCalculation first, extract one YAML, then run UepOptCalculation."""
    UepParameters = DataFactory("pymuon.uep")
    parameters = UepParameters({"geom_steps": 30})

    structure_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.cell"))
    charge_density_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.den_fmt"))
    castep_log_file = SinglefileData(file=os.path.join(TEST_DIR, "input_files", "Si.castep"))

    # Step 1: generate candidates
    muairss_result = run(
        CalculationFactory("pymuon.muairss"),
        **{
            "code": muairss_code,
            "parameters": parameters,
            "structure": structure_file,
            "metadata": {"options": {"max_wallclock_seconds": 300}},
        },
    )
    assert "candidates_folder" in muairss_result

    # Extract the first candidate YAML
    from aiida.repository import FileType

    folder = muairss_result["candidates_folder"]
    all_files = []

    def collect(fd, path=None):
        for obj in fd.list_objects(path):
            p = f"{path}/{obj.name}" if path else obj.name
            if obj.file_type == FileType.DIRECTORY:
                collect(fd, p)
            else:
                all_files.append(p)

    collect(folder)
    yaml_files = [f for f in all_files if f.endswith(".yaml")]
    assert yaml_files

    with folder.open(yaml_files[0], "rb") as f:
        yaml_node = SinglefileData(file=f, filename="candidate.yaml")
    yaml_node.store()

    # Step 2: run UEP optimisation for this candidate
    uep_result = run(
        CalculationFactory("pymuon.uep_opt"),
        **{
            "code": uep_opt_code,
            "candidate_yaml": yaml_node,
            "charge_density": charge_density_file,
            "castep_log": castep_log_file,
            "parameters": parameters,
            "metadata": {"options": {"max_wallclock_seconds": 300}},
        },
    )
    assert "uep_result" in uep_result
    folder2 = uep_result["uep_result"]
    result_files = folder2.list_object_names()
    uep_files = [f for f in result_files if f.endswith(".uep")]
    assert len(uep_files) > 0, "Expected at least one .uep file"
