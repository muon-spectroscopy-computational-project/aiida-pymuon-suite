"""Tests for CastepMuairssUepWorkChain (validator, input patching, route B end-to-end)."""

import os

import pytest
from aiida.engine import run_get_node
from aiida.orm import Dict, SinglefileData, StructureData
from aiida.plugins import DataFactory, WorkflowFactory
from ase import io as ase_io

from aiida_pymuon_suite.workflows.castep_muairss_uep import (
    DENSITY_RETRIEVE_GLOB,
    _with_density_retrieved,
    _with_formatted_density,
    validate_workchain_inputs,
)

from . import TEST_DIR

INPUT_DIR = os.path.join(TEST_DIR, "input_files")


# ---------------------------------------------------------------------------
# Route validator (pure function — accept/reject matrix)
# ---------------------------------------------------------------------------


def test_validator_route_a_only():
    """A populated castep namespace alone is accepted."""
    assert validate_workchain_inputs({"castep": {"calc": {"code": object()}}}, None) is None


def test_validator_route_b_only():
    """Both files without a castep namespace are accepted."""
    inputs = {"charge_density": object(), "castep_log": object()}
    assert validate_workchain_inputs(inputs, None) is None


def test_validator_both_routes():
    """Providing both routes is rejected."""
    inputs = {"castep": {"calc": {}}, "charge_density": object(), "castep_log": object()}
    assert "not both" in validate_workchain_inputs(inputs, None)


def test_validator_neither_route():
    """Providing no charge-density source is rejected."""
    assert "no charge-density source" in validate_workchain_inputs({}, None)


def test_validator_single_file():
    """Providing only one of the two route-B files is rejected."""
    error = validate_workchain_inputs({"charge_density": object()}, None)
    assert "both 'charge_density' and 'castep_log'" in error


# ---------------------------------------------------------------------------
# CASTEP input patching helpers
# ---------------------------------------------------------------------------


def test_with_formatted_density_nested():
    """write_formatted_density is injected into an existing PARAM block."""
    parameters = Dict({"PARAM": {"cut_off_energy": 700}, "CELL": {"symmetry_generate": True}})
    patched = _with_formatted_density(parameters)
    assert patched.get_dict()["PARAM"]["write_formatted_density"] is True
    assert patched.get_dict()["PARAM"]["cut_off_energy"] == 700


def test_with_formatted_density_flat():
    """A flat parameters dict gets the key at the top level (CastepHelper sorts it)."""
    patched = _with_formatted_density(Dict({"cut_off_energy": 700}))
    assert patched.get_dict()["write_formatted_density"] is True


def test_with_formatted_density_already_set():
    """Parameters that already enable the density are returned unchanged."""
    parameters = Dict({"PARAM": {"write_formatted_density": "true"}})
    assert _with_formatted_density(parameters) is parameters


def test_with_density_retrieved():
    """The .den_fmt glob is appended to existing and missing settings alike."""
    assert _with_density_retrieved(None).get_dict()["ADDITIONAL_RETRIEVE_LIST"] == [DENSITY_RETRIEVE_GLOB]

    settings = Dict({"ADDITIONAL_RETRIEVE_LIST": ["*.check"]})
    patched = _with_density_retrieved(settings)
    assert patched.get_dict()["ADDITIONAL_RETRIEVE_LIST"] == ["*.check", DENSITY_RETRIEVE_GLOB]

    already = Dict({"ADDITIONAL_RETRIEVE_LIST": [DENSITY_RETRIEVE_GLOB]})
    assert _with_density_retrieved(already) is already


# ---------------------------------------------------------------------------
# Workchain-level validation and route B end-to-end
# ---------------------------------------------------------------------------


def _base_inputs(muairss_code, uep_opt_code):
    uep_parameters = DataFactory("pymuon.uep")
    atoms = ase_io.read(os.path.join(INPUT_DIR, "Si.cell"))
    return {
        "structure": StructureData(ase=atoms),
        "muairss_code": muairss_code,
        "uep_code": uep_opt_code,
        "parameters": uep_parameters({"geom_steps": 30}),
    }


def test_workchain_rejects_missing_route(muairss_code, uep_opt_code):
    """Instantiation fails with a clear message when no density source is given."""
    workchain = WorkflowFactory("pymuon.castep_muairss_uep")
    with pytest.raises(ValueError, match="no charge-density source"):
        run_get_node(workchain, **_base_inputs(muairss_code, uep_opt_code))


def test_castep_muairss_uep_route_b(muairss_code, uep_opt_code):
    """Route B end-to-end on Si: files in, muon_sites out, .cell conversion on the graph."""
    inputs = _base_inputs(muairss_code, uep_opt_code)
    inputs["charge_density"] = SinglefileData(file=os.path.join(INPUT_DIR, "Si.den_fmt"))
    inputs["castep_log"] = SinglefileData(file=os.path.join(INPUT_DIR, "Si.castep"))

    result, node = run_get_node(WorkflowFactory("pymuon.castep_muairss_uep"), **inputs)

    assert node.is_finished_ok, f"exit status {node.exit_status}: {node.exit_message}"
    assert "muon_sites" in result

    # The structure_to_cell calcfunction and the inner workchain are on the provenance graph
    called_labels = [child.process_label for child in node.called]
    assert "structure_to_cell" in called_labels
    assert "MuairssUepWorkChain" in called_labels
