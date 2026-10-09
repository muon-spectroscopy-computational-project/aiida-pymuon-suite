"""CastepMuairssUepWorkChain and the bridge calcfunctions to aiida-castep.

A CASTEP run on the pristine host (with ``write_formatted_density: true`` and
``*.den_fmt`` in the retrieve list) produces everything MuairssUepWorkChain
needs. This module provides the calcfunctions converting those outputs into
the SinglefileData nodes the workchain expects, and an outer workchain that
either runs CASTEP itself (route A), takes the files directly (route B), or
reuses the retrieved folder of a finished CASTEP calculation (route C).

aiida-castep is an optional dependency (``pip install -e '.[castep]'``);
without it only route A is unavailable — routes B and C still work.
"""

import tempfile
from pathlib import Path

import numpy as np
from aiida.common import AttributeDict, exceptions
from aiida.engine import ToContext, WorkChain, calcfunction, if_
from aiida.orm import CalcJobNode, Dict, FolderData, SinglefileData, StructureData
from aiida.plugins import WorkflowFactory
from ase import Atoms
from ase import io as ase_io

from aiida_pymuon_suite.workflows.muairss_uep import MuairssUepWorkChain, _list_files_recursive

try:
    CastepBaseWorkChain = WorkflowFactory("castep.base")
except exceptions.MissingEntryPointError:
    CastepBaseWorkChain = None

CELL_FILENAME = "aiida.cell"
DENSITY_SUFFIX = ".den_fmt"

#: A CASTEP formatted density begins with this marker. pm-uep-opt rejects anything else
#: with "FMT file has no header" — but only after every UepOptCalculation has been
#: submitted and run, so checking it up front turns a slow, confusing failure into an
#: immediate one. Test fixtures that write a placeholder .den_fmt are the usual culprit.
DENSITY_HEADER = b"BEGIN header"

#: Bytes read from the start of a density when checking the header.
DENSITY_HEADER_PEEK = 4096


def density_has_header(folder, path) -> bool:
    """True when `path` in `folder` looks like a CASTEP formatted density file."""
    try:
        # mode="rb": NodeRepository.open defaults to text, and `bytes in str` raises.
        with folder.base.repository.open(path, mode="rb") as handle:
            return DENSITY_HEADER in handle.read(DENSITY_HEADER_PEEK)
    except Exception:
        return False


def find_valid_density(folder):
    """Return the path of the first usable `.den_fmt` in `folder`, or None.

    A file with the right suffix but no header is treated as absent: it cannot be
    used, and saying so here is far cheaper than discovering it downstream.
    """
    from aiida_pymuon_suite.workflows.muairss_uep import _list_files_recursive

    for path in _list_files_recursive(folder):
        if path.endswith(DENSITY_SUFFIX) and density_has_header(folder, path):
            return path
    return None


CASTEP_LOG_SUFFIX = ".castep"
DENSITY_RETRIEVE_GLOB = "*.den_fmt"


def has_aiida_castep():
    """Return True if aiida-castep is installed (route A available)."""
    return CastepBaseWorkChain is not None


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
    # Write via a real file: ase<=3.22 castep-cell writer needs fd.name, which StringIO lacks
    with tempfile.TemporaryDirectory() as tmpdir:
        cell_path = Path(tmpdir) / CELL_FILENAME
        ase_io.write(str(cell_path), atoms, format="castep-cell")
        return SinglefileData(file=str(cell_path))


def _with_formatted_density(parameters):
    """Return parameters with write_formatted_density enabled (new Dict if patched).

    Handles both shapes CastepBaseWorkChain accepts: PARAM/CELL-nested and flat
    (its CastepHelper sorts flat keys into the right file).
    """
    tree = parameters.get_dict()
    target = tree["PARAM"] if "PARAM" in tree else tree
    if str(target.get("write_formatted_density", "")).lower() in ("true", "t"):
        return parameters
    target["write_formatted_density"] = True
    return Dict(tree)


def _with_density_retrieved(settings):
    """Return settings with *.den_fmt in ADDITIONAL_RETRIEVE_LIST (new Dict if patched)."""
    tree = settings.get_dict() if settings is not None else {}
    retrieve_list = tree.setdefault("ADDITIONAL_RETRIEVE_LIST", [])
    if DENSITY_RETRIEVE_GLOB in retrieve_list:
        return settings
    retrieve_list.append(DENSITY_RETRIEVE_GLOB)
    return Dict(tree)


def _castep_retrieved_folder(workchain):
    """Return the retrieved FolderData of the last successful CASTEP calculation.

    CastepBaseWorkChain does not expose ``retrieved``, so it is taken from the
    most recent finished-ok CalcJobNode the workchain called.
    """
    calcjobs = sorted(
        (node for node in workchain.called if isinstance(node, CalcJobNode)),
        key=lambda node: node.ctime,
    )
    for calcjob in reversed(calcjobs):
        if calcjob.is_finished_ok and "retrieved" in calcjob.outputs:
            return calcjob.outputs.retrieved
    return None


def validate_workchain_inputs(inputs, _):
    """Ensure exactly one charge-density route is provided (route A, B or C)."""
    has_castep = bool(inputs.get("castep"))
    has_retrieved = "castep_retrieved" in inputs
    n_files = sum(1 for key in ("charge_density", "castep_log") if key in inputs)
    if sum([has_castep, has_retrieved, n_files > 0]) > 1:
        return (
            "provide exactly one charge-density source: the 'castep' namespace (route A), "
            "'charge_density' + 'castep_log' files (route B) or 'castep_retrieved' (route C), not several"
        )
    if has_retrieved and find_valid_density(inputs["castep_retrieved"]) is None:
        return (
            f"'castep_retrieved' has no usable charge density: no file ending "
            f"{DENSITY_SUFFIX} starts with '{DENSITY_HEADER.decode()}'. The CASTEP run "
            f"either did not write a formatted density, or is not a real run."
        )
    if has_castep or has_retrieved or n_files == 2:
        return None
    if n_files == 1:
        return "both 'charge_density' and 'castep_log' are required when providing the files manually"
    message = (
        "no charge-density source: provide 'charge_density' + 'castep_log' (route B) or 'castep_retrieved' (route C)"
    )
    if has_aiida_castep():
        return message + " or the 'castep' namespace (route A)"
    return message + "; route A requires aiida-castep (pip install -e '.[castep]')"


class CastepMuairssUepWorkChain(WorkChain):
    """UEP muon stopping-site pipeline starting from a StructureData.

    Wraps MuairssUepWorkChain with three ways of providing the CASTEP charge
    density: route A runs a CastepBaseWorkChain on the pristine host (inputs
    under the ``castep`` namespace; ``write_formatted_density`` and the
    ``*.den_fmt`` retrieve entry are added automatically), route B takes
    ``charge_density`` and ``castep_log`` files directly, as MuairssUepWorkChain
    does today, and route C takes ``castep_retrieved`` — the retrieved folder
    of a finished CASTEP calculation — and extracts the files from it.
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.input("structure", valid_type=StructureData, help="Pristine host crystal structure.")
        spec.input(
            "charge_density",
            valid_type=SinglefileData,
            required=False,
            help="CASTEP charge density (.den_fmt) — route B.",
        )
        spec.input(
            "castep_log",
            valid_type=SinglefileData,
            required=False,
            help="CASTEP log file (.castep) — route B.",
        )
        spec.input(
            "castep_retrieved",
            valid_type=FolderData,
            required=False,
            help="Retrieved folder of a finished CASTEP calculation — route C.",
        )
        if has_aiida_castep():
            spec.expose_inputs(
                CastepBaseWorkChain,
                namespace="castep",
                exclude=("calc.structure",),
                namespace_options={
                    "required": False,
                    "populate_defaults": False,
                    "help": "Inputs for the CastepBaseWorkChain on the pristine host — route A.",
                },
            )
        spec.expose_inputs(MuairssUepWorkChain, exclude=("structure", "charge_density", "castep_log"))
        spec.inputs.validator = validate_workchain_inputs

        spec.expose_outputs(MuairssUepWorkChain)

        spec.outline(
            if_(cls.should_run_castep)(
                cls.run_castep,
                cls.inspect_castep,
            ),
            cls.prepare_uep_inputs,
            cls.run_muairss_uep,
            cls.inspect_muairss_uep,
        )

        spec.exit_code(410, "ERROR_CASTEP_FAILED", message="The CastepBaseWorkChain did not finish successfully.")
        spec.exit_code(
            411,
            "ERROR_UEP_INPUT_EXTRACTION",
            message="Could not extract the .den_fmt/.castep files from the CASTEP outputs.",
        )
        spec.exit_code(412, "ERROR_MUAIRSS_UEP_FAILED", message="The MuairssUepWorkChain sub-process failed.")

    def should_run_castep(self):
        """Route A was chosen if the castep namespace is populated."""
        return bool(self.inputs.get("castep"))

    def run_castep(self):
        """Submit the CastepBaseWorkChain on the pristine host structure."""
        inputs = AttributeDict(self.exposed_inputs(CastepBaseWorkChain, namespace="castep"))
        inputs.calc = AttributeDict(inputs.calc)
        inputs.calc.structure = self.inputs.structure
        inputs.calc.parameters = _with_formatted_density(inputs.calc.parameters)
        inputs.calc.settings = _with_density_retrieved(inputs.calc.get("settings"))
        running = self.submit(CastepBaseWorkChain, **inputs)
        self.report(f"submitted CastepBaseWorkChain<{running.pk}> for the host charge density (route A)")
        return ToContext(castep=running)

    def inspect_castep(self):
        """Check the CASTEP run and extract the UEP input files from it."""
        workchain = self.ctx.castep
        if not workchain.is_finished_ok:
            self.report(f"CastepBaseWorkChain<{workchain.pk}> failed with exit status {workchain.exit_status}")
            return self.exit_codes.ERROR_CASTEP_FAILED
        retrieved = _castep_retrieved_folder(workchain)
        if retrieved is None:
            self.report(f"no retrieved folder found under CastepBaseWorkChain<{workchain.pk}>")
            return self.exit_codes.ERROR_UEP_INPUT_EXTRACTION
        try:
            extracted = extract_uep_inputs(retrieved)
        except ValueError as exc:
            self.report(f"extraction of UEP inputs failed: {exc}")
            return self.exit_codes.ERROR_UEP_INPUT_EXTRACTION
        self.ctx.charge_density = extracted["charge_density"]
        self.ctx.castep_log = extracted["castep_log"]
        return None

    def prepare_uep_inputs(self):
        """Collect the UEP input files (routes B and C) and render the structure to .cell."""
        if "castep_retrieved" in self.inputs:
            try:
                extracted = extract_uep_inputs(self.inputs.castep_retrieved)
            except ValueError as exc:
                self.report(f"extraction of UEP inputs failed: {exc}")
                return self.exit_codes.ERROR_UEP_INPUT_EXTRACTION
            self.ctx.charge_density = extracted["charge_density"]
            self.ctx.castep_log = extracted["castep_log"]
        elif "charge_density" in self.inputs:
            self.ctx.charge_density = self.inputs.charge_density
            self.ctx.castep_log = self.inputs.castep_log
        self.ctx.cell_file = structure_to_cell(self.inputs.structure)
        return None

    def run_muairss_uep(self):
        """Submit the inner MuairssUepWorkChain with the collected files."""
        inputs = AttributeDict(self.exposed_inputs(MuairssUepWorkChain))
        inputs.structure = self.ctx.cell_file
        inputs.charge_density = self.ctx.charge_density
        inputs.castep_log = self.ctx.castep_log
        running = self.submit(MuairssUepWorkChain, **inputs)
        self.report(f"submitted MuairssUepWorkChain<{running.pk}>")
        return ToContext(muairss_uep=running)

    def inspect_muairss_uep(self):
        """Check the inner workchain and forward its outputs."""
        workchain = self.ctx.muairss_uep
        if not workchain.is_finished_ok:
            self.report(f"MuairssUepWorkChain<{workchain.pk}> failed with exit status {workchain.exit_status}")
            return self.exit_codes.ERROR_MUAIRSS_UEP_FAILED
        self.out_many(self.exposed_outputs(workchain, MuairssUepWorkChain))
        return None
