"""Tests for calculations, parsers, and WorkChain."""

import io
import os

import pytest
from aiida.common.links import LinkType
from aiida.engine import ProcessState, run
from aiida.orm import CalcJobNode, FolderData, SinglefileData
from aiida.plugins import CalculationFactory, DataFactory, ParserFactory

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


# ---------------------------------------------------------------------------
# UepOptParser — empty .uep detection (no pm-uep-opt needed)
# ---------------------------------------------------------------------------


def _parsed_exit_status(uep_opt_code, files):
    """Parse a fake UepOptCalculation whose retrieved folder holds ``files``."""
    node = CalcJobNode(computer=uep_opt_code.computer, process_type="aiida.calculations:pymuon.uep_opt")
    node.set_option("resources", {"num_machines": 1, "num_mpiprocs_per_machine": 1})
    node.set_option("parser_name", "pymuon.uep_opt")
    node.set_process_state(ProcessState.FINISHED)
    node.set_exit_status(0)
    node.store()

    retrieved = FolderData()
    for name, content in files.items():
        retrieved.put_object_from_filelike(io.BytesIO(content), name)
    retrieved.base.links.add_incoming(node, LinkType.CREATE, "retrieved")
    retrieved.store()
    node.seal()

    _results, calcfunction = ParserFactory("pymuon.uep_opt").parse_from_node(node, store_provenance=False)
    return calcfunction.exit_status


def test_uep_opt_parser_rejects_empty_uep(uep_opt_code):
    """A zero-byte .uep means geomopt failed; the parser must not report success."""
    exit_codes = CalculationFactory("pymuon.uep_opt").spec().exit_codes

    status = _parsed_exit_status(
        uep_opt_code,
        {
            "struct_1.uep": b"",
            "pm-uep-opt.stdout": b'Performing UEP optimisation\nError:  The property "energy" is not available.\n',
        },
    )

    assert status == exit_codes.ERROR_EMPTY_UEP_FILE.status


def test_uep_opt_parser_accepts_non_empty_uep(uep_opt_code):
    """A .uep with content parses cleanly and yields the uep_result folder."""
    status = _parsed_exit_status(
        uep_opt_code,
        {
            "struct_1.uep": b"Classical energy: -1363.2 eV\n",
            "struct_1.uep.pkl": b"\x80\x04.",
            "pm-uep-opt.stdout": b"Optimisation complete\n",
        },
    )

    assert status == 0


def test_uep_opt_parser_rejects_missing_uep(uep_opt_code):
    """No .uep file at all is still the pre-existing ERROR_NO_UEP_FILE."""
    exit_codes = CalculationFactory("pymuon.uep_opt").spec().exit_codes

    status = _parsed_exit_status(uep_opt_code, {"pm-uep-opt.stdout": b"boom\n"})

    assert status == exit_codes.ERROR_NO_UEP_FILE.status
