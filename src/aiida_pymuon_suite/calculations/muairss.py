"""MuairssCalculation: runs pm-muairss -t w to generate candidate muonated structures."""

from aiida.common import datastructures
from aiida.engine import CalcJob
from aiida.orm import FolderData, SinglefileData
from aiida.plugins import DataFactory

UepParameters = DataFactory("pymuon.uep")


class MuairssCalculation(CalcJob):
    """CalcJob wrapping pm-muairss -t w.

    Generates candidate muonated structures and writes per-candidate YAML files.
    Does not run pm-uep-opt — that is handled by UepOptCalculation.
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.inputs["metadata"]["options"]["resources"].default = {
            "num_machines": 1,
            "num_mpiprocs_per_machine": 1,
        }
        spec.inputs["metadata"]["options"]["parser_name"].default = "pymuon.muairss"

        spec.input("structure", valid_type=SinglefileData, help="Crystal structure file (.cell, .cif, or .xyz).")
        spec.input("parameters", valid_type=UepParameters, help="UEP generation parameters.")

        spec.output(
            "candidates_folder",
            valid_type=FolderData,
            help="muon-airss-out/uep/ tree — one subdirectory per candidate, each with a .yaml.",
        )

        spec.exit_code(300, "ERROR_NO_CANDIDATES", message="pm-muairss generated no candidate structures.")

    def prepare_for_submission(self, folder):
        structure_ext = self.inputs.structure.filename.rsplit(".", 1)[-1]
        internal_name = f"input_structure.{structure_ext}"

        with folder.open("params.yaml", "w") as f:
            f.write(self.inputs.parameters.render_yaml())

        codeinfo = datastructures.CodeInfo()
        codeinfo.cmdline_params = ["-t", "w", internal_name, "params.yaml"]
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.stdout_name = "pm-muairss.stdout"
        codeinfo.stderr_name = "pm-muairss.stderr"

        calcinfo = datastructures.CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.local_copy_list = [
            (self.inputs.structure.uuid, self.inputs.structure.filename, internal_name),
        ]
        calcinfo.retrieve_list = ["muon-airss-out", "pm-muairss.stdout", "pm-muairss.stderr"]

        return calcinfo
