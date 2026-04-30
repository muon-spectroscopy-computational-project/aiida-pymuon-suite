"""Parser for UepOptCalculation."""

from aiida.common import exceptions
from aiida.engine import ExitCode
from aiida.orm import FolderData
from aiida.parsers.parser import Parser
from aiida.plugins import CalculationFactory


class UepOptParser(Parser):
    """Parser for UepOptCalculation output."""

    def __init__(self, node):
        super().__init__(node)
        if not issubclass(node.process_class, CalculationFactory("pymuon.uep_opt")):
            raise exceptions.ParsingError("Can only parse UepOptCalculation")

    def parse(self, **kwargs):
        files_retrieved = self.retrieved.list_object_names()

        uep_files = [f for f in files_retrieved if f.endswith(".uep")]
        if not uep_files:
            self.logger.error("No .uep file produced by pm-uep-opt.")
            return self.exit_codes.ERROR_NO_UEP_FILE

        result_folder = FolderData()
        for filename in files_retrieved:
            with self.retrieved.open(filename, "rb") as f:
                result_folder.put_object_from_filelike(f, filename)

        self.out("uep_result", result_folder)
        return ExitCode(0)
