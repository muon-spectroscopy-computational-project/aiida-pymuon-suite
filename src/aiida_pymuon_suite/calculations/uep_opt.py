"""UepOptCalculation: runs pm-uep-opt for a single candidate muon site."""

import yaml
from aiida.common import datastructures
from aiida.engine import CalcJob
from aiida.orm import FolderData, SinglefileData
from aiida.plugins import DataFactory

UepParameters = DataFactory("pymuon.uep")


class UepOptCalculation(CalcJob):
    """CalcJob wrapping pm-uep-opt for one candidate structure.

    Receives a per-candidate YAML from MuairssCalculation, patches the
    charge-density paths to point to the AiiDA working directory, and runs
    pm-uep-opt.
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)

        spec.inputs["metadata"]["options"]["resources"].default = {
            "num_machines": 1,
            "num_mpiprocs_per_machine": 1,
        }
        spec.inputs["metadata"]["options"]["parser_name"].default = "pymuon.uep_opt"

        spec.input("candidate_yaml", valid_type=SinglefileData, help="Per-candidate .yaml from MuairssCalculation.")
        spec.input("charge_density", valid_type=SinglefileData, help="CASTEP charge density file (.den_fmt).")
        spec.input("castep_log", valid_type=SinglefileData, help="CASTEP log file (.castep).")
        spec.input("parameters", valid_type=UepParameters, help="Used for gw_factor, geom_steps, geom_force_tol.")

        spec.output(
            "uep_result",
            valid_type=FolderData,
            help="Directory containing .uep and .uep.pkl for this candidate.",
        )

        spec.exit_code(301, "ERROR_NO_UEP_FILE", message="pm-uep-opt did not produce a .uep output file.")
        spec.exit_code(
            302,
            "ERROR_EMPTY_UEP_FILE",
            message="pm-uep-opt produced an empty .uep file; the optimisation failed. See pm-uep-opt.stdout.",
        )

    def prepare_for_submission(self, folder):
        # Patch chden_path/chden_seed to point at the AiiDA working directory
        yaml_name = self.inputs.candidate_yaml.filename  # e.g. "struct_001.yaml"
        raw = self.inputs.candidate_yaml.get_content()
        content = yaml.safe_load(raw)
        content["chden_path"] = "./"
        content["chden_seed"] = "input_structure"
        with folder.open(yaml_name, "w") as f:
            yaml.dump(content, f)

        codeinfo = datastructures.CodeInfo()
        codeinfo.cmdline_params = [yaml_name]
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.stdout_name = "pm-uep-opt.stdout"
        codeinfo.stderr_name = "pm-uep-opt.stderr"

        calcinfo = datastructures.CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.local_copy_list = [
            (self.inputs.charge_density.uuid, self.inputs.charge_density.filename, "input_structure.den_fmt"),
            (self.inputs.castep_log.uuid, self.inputs.castep_log.filename, "input_structure.castep"),
        ]
        calcinfo.retrieve_list = ["*.uep", "*.uep.pkl", "*.xyz", "pm-uep-opt.stdout", "pm-uep-opt.stderr"]

        return calcinfo
