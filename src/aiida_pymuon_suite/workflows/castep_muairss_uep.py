"""Bridge calcfunctions linking aiida-castep outputs to MuairssUepWorkChain inputs.

A CASTEP run on the pristine host (with ``write_formatted_density: true`` and
``*.den_fmt`` in the retrieve list) produces everything MuairssUepWorkChain
needs. The calcfunctions here convert those outputs into the SinglefileData
nodes the workchain expects, keeping the conversion on the provenance graph.
"""

import io
from pathlib import Path

import numpy as np
from aiida.engine import calcfunction
from aiida.orm import SinglefileData
from ase import Atoms
from ase import io as ase_io

from aiida_pymuon_suite.workflows.muairss_uep import _list_files_recursive

CELL_FILENAME = "aiida.cell"
DENSITY_SUFFIX = ".den_fmt"
CASTEP_LOG_SUFFIX = ".castep"


def _extract_single_file(folder_data, suffix):
    """Return the unique file ending in suffix from a FolderData as SinglefileData."""
    matches = [f for f in _list_files_recursive(folder_data) if f.endswith(suffix)]
    if not matches:
        raise ValueError(
            f"No '{suffix}' file found in the retrieved folder. For charge density files, make sure the "
            "CASTEP calculation sets 'write_formatted_density: true' in PARAM and retrieves '*.den_fmt' "
            "via ADDITIONAL_RETRIEVE_LIST."
        )
    if len(matches) > 1:
        raise ValueError(f"Expected exactly one '{suffix}' file in the retrieved folder, found: {sorted(matches)}")
    with folder_data.open(matches[0], "rb") as handle:
        return SinglefileData(file=handle, filename=Path(matches[0]).name)


@calcfunction
def extract_uep_inputs(retrieved):
    """Extract UEP input files from a CASTEP calculation's retrieved folder.

    Takes the ``retrieved`` FolderData of a CastepCalculation / CastepBaseWorkChain
    and returns ``{"charge_density": <.den_fmt>, "castep_log": <.castep>}`` as
    SinglefileData nodes. Filenames are preserved — UepOptCalculation renames its
    inputs to a common seed internally, so no renaming is needed here.
    """
    return {
        "charge_density": _extract_single_file(retrieved, DENSITY_SUFFIX),
        "castep_log": _extract_single_file(retrieved, CASTEP_LOG_SUFFIX),
    }


@calcfunction
def structure_to_cell(structure):
    """Write a StructureData to a CASTEP .cell file wrapped in SinglefileData.

    MuairssCalculation takes the structure as a file, so both routes of the
    CASTEP-enabled workflow (run CASTEP / provide files manually) can share a
    single StructureData input converted through this calcfunction.
    """
    atoms = structure.get_ase()
    # StructureData.get_ase() always sets an explicit masses array; when all masses are
    # ASE defaults, ase's castep-cell writer emits an *empty* SPECIES_MASS block that
    # crashes ase's reader (and therefore pm-muairss). Drop the array in that case.
    if "masses" in atoms.arrays and np.allclose(
        atoms.arrays["masses"], Atoms(atoms.get_chemical_symbols()).get_masses(), atol=1e-3
    ):
        del atoms.arrays["masses"]
    buffer = io.StringIO()
    ase_io.write(buffer, atoms, format="castep-cell")
    return SinglefileData(file=io.BytesIO(buffer.getvalue().encode("utf-8")), filename=CELL_FILENAME)
