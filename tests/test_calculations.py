"""Tests for calculations."""

import os

from aiida.engine import run
from aiida.orm import SinglefileData
from aiida.plugins import CalculationFactory, DataFactory

from . import TEST_DIR


def test_process(uep_code):
    """Test running a calculation
    note this does not test that the expected outputs are created of output parsing"""

    # Prepare input parameters
    uep_parameters = DataFactory("pymuon.uep")
    parameters = uep_parameters({
        "poisson_r": 0.8,
        "vdw_scale": 0.5,
        "geom_steps": 30,
        "geom_force_tol": 0.05,
        "uep_gw_factor": 5.0
    })

    structure_file = SinglefileData(
        file=os.path.join(TEST_DIR, "input_files", "Si.cell")
    )
    charge_density_file = SinglefileData(
        file=os.path.join(TEST_DIR, "input_files", "Si.den_fmt")
    )
    castep_log_file = SinglefileData(
        file=os.path.join(TEST_DIR, "input_files", "Si.castep")
    )  


    # set up calculation
    inputs = {
        "code": uep_code,
        "parameters": parameters,
        "structure": structure_file,
        "charge_density": charge_density_file,
        "castep_log": castep_log_file,
        "metadata": {
            "options": {"max_wallclock_seconds": 300},
        },
    }

    result = run(CalculationFactory("pymuon.uep"), **inputs)
    assert "retrieved" in result

def test_parameter_validation():
    uep_parameters = DataFactory("pymuon.uep")

    params = uep_parameters({})
    assert params["poisson_r"] == 0.8
    assert params["vdw_scale"] == 0.5
    assert params["geom_steps"] == 30
    assert params["geom_force_tol"] == 0.05
    assert params["uep_gw_factor"] == 5.0

    params = uep_parameters({
        "poisson_r": 1.0,
        "vdw_scale": 0.25,
        "geom_steps": 100,
        "random_seed": 42,
        "allpos_ext": "xyz"
    })
    assert params["poisson_r"] == 1.0
    assert params["random_seed"] == 42
    assert params["allpos_ext"] == "xyz"

def test_render_yaml():
    uep_parameters = DataFactory("pymuon.uep")

    params = uep_parameters({
        "poisson_r": 0.7,
        "vdw_scale": 0.8,
        "geom_steps": 25,
        "geom_force_tol": 0.02,
        "uep_gw_factor": 4.0,
        "allpos_ext": "cif",
    })

    yaml_output = params.render_yaml()
    assert "calculator: uep" in yaml_output
    assert "charged: true" in yaml_output
    assert "out_folder: muon-airss-out" in yaml_output
    assert "poisson_r: 0.7" in yaml_output
    assert "allpos_filename: allpos.cif" in yaml_output
    assert "allpos_ext" not in yaml_output