"""
Calculations provided by aiida-pymuon-suite.

Register calculations via the "aiida.calculations" entry point in setup.json.
"""

from aiida.common import datastructures
from aiida.engine import CalcJob
from aiida.orm import FolderData, SinglefileData
from aiida.plugins import DataFactory

UepParameters = DataFactory("pymuon.uep")


class UepCalculation(CalcJob):
    """
    AiiDA calculation plugin wrapping the pymuon-suite UEP optimisation pipeline.

    Runs pm-muairss to generate muonated structures, and run pm-uep-opt on each generated structure.
    Requires: CASTEP charge density file, log file and crystal structure file.
    """

    @classmethod
    def define(cls, spec):
        """Define inputs and outputs of the calculation."""
        super().define(spec)

        # set default values for AiiDA options
        spec.inputs["metadata"]["options"]["resources"].default = {
            "num_machines": 1,
            "num_mpiprocs_per_machine": 1,
        }
        spec.inputs["metadata"]["options"]["parser_name"].default = "pymuon.uep"

        # new ports
        spec.input(
            "parameters",
            valid_type=UepParameters,
            help="UEP generation and optimisation parameters.",
        )
        spec.input("structure", valid_type=SinglefileData, help="Crystal structure file (CELL CIF or extended XYZ).")
        spec.input("charge_density", valid_type=SinglefileData, help="CASTEP charge density file. (.den_fmt)")
        spec.input("castep_log", valid_type=SinglefileData, help="CASTEP log file. (.castep)")
        spec.output(
            "allpos_files",
            valid_type=SinglefileData,
            required=False,
            help="file containing all the generated muonated structures. (allpos format)",
        )
        spec.output(
            "muon_airss_out",
            valid_type=FolderData,
            help="Directory containing UEP optimisation results (.uep files).",
        )

        spec.exit_code(
            300,
            "ERROR_MISSING_OUTPUT_FILES",
            message="Calculation did not produce all expected output files.",
        )

        spec.exit_code(
            310,
            "ERROR_ALL_OPTIMIZATIONS_FAILED",
            message="All UEP optimizations failed.",
        )
    def prepare_for_submission(self, folder):
        """
        Create input files.

        :param folder: an `aiida.common.folders.Folder` where the plugin should temporarily place all files
            needed by the calculation.
        :return: `aiida.common.datastructures.CalcInfo` instance
        """

        # Determine the structure file name
        structure_ext = self.inputs.structure.filename.rsplit(".", 1)[-1]
        internal_structure_name = f"input_structure.{structure_ext}"

        # Write params.yaml
        params_content = self.inputs.parameters.render_yaml()
        with folder.open("params.yaml", "w") as params_file:
            params_file.write(params_content)


        # Set up the main command: pm-muairss -t -w <structure> params.yaml
        codeinfo = datastructures.CodeInfo()
        codeinfo.cmdline_params = ["-t", "w", internal_structure_name, "params.yaml"]
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.stdout_name = "pm-muairss.stdout"
        codeinfo.stderr_name = "pm-muairss.stderr"

        # Prepare a `CalcInfo` to be returned to the engine
        calcinfo = datastructures.CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.local_copy_list = [
            (
                self.inputs.structure.uuid,
                self.inputs.structure.filename,
                internal_structure_name,
            ),
            (
                self.inputs.charge_density.uuid,
                self.inputs.charge_density.filename,
                "input_structure.den_fmt",
            ),
            (
                self.inputs.castep_log.uuid,
                self.inputs.castep_log.filename,
                "input_structure.castep",
            ),
        ]

        calcinfo.append_text = self._get_append_text()
        #post muairss step: run pm-uep-opt on each generated muonated structure
        calcinfo.retrieve_list = [
            "muon-airss-out",
            "params.yaml",
            "pm-muairss.stdout",
            "pm-muairss.stderr",
            "uep_opt.log",
        ]

        params_dict = self.inputs.parameters.get_dict()
        if "allpos_ext" in params_dict:
            ext = params_dict["allpos_ext"]
            calcinfo.retrieve_list.append(f"allpos.{ext}")

        return calcinfo
    
    @staticmethod
    def _get_append_text():
        """
        generated bash script after pm-muairss to 
        Patches generated yaml file to fix charge density paths
        Run pm-uem-opt on each generated muonated structure
        """
        return r"""

OUT_FOLDER="muon-airss-out"

find "$OUT_FOLDER" -type f -name "*.yaml" -exec sed -i 's#^chden_path: .*#chden_path: ./#g' {} +
find "$OUT_FOLDER" -type f -name "*.yaml" -exec sed -i 's#^chden_seed: .*#chden_seed: input_structure#g' {} +


pids=()
for yaml_file in "$OUT_FOLDER"/*/*/*.yaml; do
    pm-uep-opt "$yaml_file" &
    pids+=($!)
done

failed=0
totals=${#pids[@]}
for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
        failed=$((failed + 1))
    fi
done

if [ $failed -eq $totals ] && [ "$totals" -gt 0 ]; then
    echo "ERROR: All optimisation failed ($failed/$totals)" >&2
    exit 1
elif [ $failed -gt 0 ]; then
    echo "WARNING: $failed/$totals optimisation(s) failed" >&2
fi

echo "UEP optimisations completed." > uep_opt.log
"""



