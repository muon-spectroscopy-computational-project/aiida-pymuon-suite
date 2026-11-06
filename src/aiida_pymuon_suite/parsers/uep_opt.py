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

        # pm-uep-opt opens the .uep file before running the optimisation and
        # exits without writing to it when geomopt raises, leaving a zero-byte
        # file and no .uep.pkl. Existence alone is therefore not success.
        if all(self._is_empty(filename) for filename in uep_files):
            self.logger.error(f"pm-uep-opt produced an empty .uep file. {self._failure_reason()}")
            return self.exit_codes.ERROR_EMPTY_UEP_FILE

        result_folder = FolderData()
        for filename in files_retrieved:
            with self.retrieved.open(filename, "rb") as f:
                result_folder.put_object_from_filelike(f, filename)

        self.out("uep_result", result_folder)
        return ExitCode(0)

    def _is_empty(self, filename):
        """Return True if a retrieved file holds no bytes."""
        with self.retrieved.open(filename, "rb") as handle:
            return not handle.read(1)

    def _failure_reason(self):
        """Return the error line pm-uep-opt printed, for the log message."""
        try:
            stdout = self.retrieved.get_object_content("pm-uep-opt.stdout")
        except (OSError, FileNotFoundError):
            return "No pm-uep-opt.stdout was retrieved."
        for line in stdout.splitlines():
            if line.startswith("Error:"):
                return line.strip()
        return "pm-uep-opt.stdout reported no error line."
