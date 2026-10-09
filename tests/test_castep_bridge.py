"""Tests for the CASTEP bridge calcfunctions in workflows/castep_muairss_uep.py."""

import io
import os

import pytest
from aiida.orm import FolderData, StructureData
from aiida_pymuon_suite.workflows.castep_muairss_uep import (
    CELL_FILENAME,
    extract_uep_inputs,
    structure_to_cell,
)
from ase import io as ase_io
from ase.build import bulk

from . import TEST_DIR

INPUT_DIR = os.path.join(TEST_DIR, "input_files")


def _castep_retrieved_folder():
    """Build a FolderData mimicking an aiida-castep retrieved folder."""
    folder = FolderData()
    folder.put_object_from_file(os.path.join(INPUT_DIR, "Si.den_fmt"), "aiida.den_fmt")
    folder.put_object_from_file(os.path.join(INPUT_DIR, "Si.castep"), "aiida.castep")
    # Distractors that must not be picked up by suffix matching
    folder.put_object_from_filelike(io.BytesIO(b"binary checkpoint"), "aiida.castep_bin")
    folder.put_object_from_filelike(io.BytesIO(b""), "_scheduler-stdout.txt")
    return folder


# ---------------------------------------------------------------------------
# extract_uep_inputs
# ---------------------------------------------------------------------------


def test_extract_uep_inputs():
    """Both files are extracted with content intact and filenames preserved."""
    retrieved = _castep_retrieved_folder()

    outputs = extract_uep_inputs(retrieved)

    assert set(outputs) == {"charge_density", "castep_log"}
    assert outputs["charge_density"].filename == "aiida.den_fmt"
    assert outputs["castep_log"].filename == "aiida.castep"

    with open(os.path.join(INPUT_DIR, "Si.den_fmt"), "rb") as f:
        assert outputs["charge_density"].get_content(mode="rb") == f.read()
    with open(os.path.join(INPUT_DIR, "Si.castep"), "rb") as f:
        assert outputs["castep_log"].get_content(mode="rb") == f.read()

    # Provenance: outputs are stored nodes linked to a calcfunction
    assert outputs["charge_density"].is_stored
    assert outputs["castep_log"].is_stored


def test_extract_uep_inputs_missing_density():
    """A retrieved folder without a .den_fmt file raises a clear error."""
    folder = FolderData()
    folder.put_object_from_file(os.path.join(INPUT_DIR, "Si.castep"), "aiida.castep")

    with pytest.raises(ValueError, match="write_formatted_density"):
        extract_uep_inputs(folder)


def test_extract_uep_inputs_missing_log():
    """A retrieved folder without a .castep file raises a clear error."""
    folder = FolderData()
    folder.put_object_from_file(os.path.join(INPUT_DIR, "Si.den_fmt"), "aiida.den_fmt")

    with pytest.raises(ValueError, match=r"No '\.castep' file"):
        extract_uep_inputs(folder)


def test_extract_uep_inputs_ambiguous_density():
    """Two .den_fmt files in the retrieved folder raise rather than guess."""
    folder = _castep_retrieved_folder()
    folder.put_object_from_file(os.path.join(INPUT_DIR, "Si.den_fmt"), "other.den_fmt")

    with pytest.raises(ValueError, match="exactly one"):
        extract_uep_inputs(folder)


# ---------------------------------------------------------------------------
# structure_to_cell
# ---------------------------------------------------------------------------


def test_structure_to_cell():
    """A StructureData round-trips through the generated .cell file."""
    atoms = bulk("Si", "diamond", a=5.43)
    structure = StructureData(ase=atoms)

    cell_file = structure_to_cell(structure)

    assert cell_file.filename == CELL_FILENAME
    content = cell_file.get_content()
    assert "LATTICE_CART" in content.upper()
    # Default masses must not produce a SPECIES_MASS block — an empty one breaks
    # ase's castep-cell reader, which pm-muairss uses to read this file.
    assert "SPECIES_MASS" not in content.upper()

    reread = ase_io.read(io.StringIO(content), format="castep-cell")
    assert reread.get_chemical_symbols() == atoms.get_chemical_symbols()
    assert reread.get_cell().round(6).tolist() == atoms.get_cell().round(6).tolist()
    assert cell_file.is_stored
