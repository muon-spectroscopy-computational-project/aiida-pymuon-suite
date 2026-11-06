"""Parser for MuairssCalculation."""

from pathlib import Path

from aiida.common import exceptions
from aiida.engine import ExitCode
from aiida.orm import FolderData, SinglefileData
from aiida.parsers.parser import Parser
from aiida.plugins import CalculationFactory
from aiida.repository import FileType


def _list_files_recursive(folder_data, path=None):
    """Return all file paths (relative to folder root) under path."""
    results = []
    for obj in folder_data.list_objects(path):
        obj_path = f"{path}/{obj.name}" if path else obj.name
        if obj.file_type == FileType.DIRECTORY:
            results.extend(_list_files_recursive(folder_data, obj_path))
        else:
            results.append(obj_path)
    return results


class MuairssParser(Parser):
    """Parser for MuairssCalculation output."""

    def __init__(self, node):
        super().__init__(node)
        if not issubclass(node.process_class, CalculationFactory("pymuon.muairss")):
            raise exceptions.ParsingError("Can only parse MuairssCalculation")

    def parse(self, **kwargs):
        files_retrieved = self.retrieved.list_object_names()

        if "muon-airss-out" not in files_retrieved:
            self.logger.error("Output folder 'muon-airss-out' not found.")
            return self.exit_codes.ERROR_NO_CANDIDATES

        all_files = _list_files_recursive(self.retrieved, "muon-airss-out")
        yaml_files = [f for f in all_files if f.endswith(".yaml")]

        if not yaml_files:
            self.logger.error("No candidate .yaml files found in muon-airss-out.")
            return self.exit_codes.ERROR_NO_CANDIDATES

        self.logger.info(f"Found {len(yaml_files)} candidate structures.")

        # Expose the uep/ subtree as candidates_folder
        uep_prefix = "muon-airss-out/uep/"
        uep_files = [f for f in all_files if f.startswith(uep_prefix)]

        candidates_folder = FolderData()
        for filepath in uep_files:
            relative = filepath[len(uep_prefix) :]
            with self.retrieved.open(filepath, "rb") as f:
                candidates_folder.put_object_from_filelike(f, relative)

        self.out("candidates_folder", candidates_folder)

        # Expose allpos file if pm-muairss generated one (written to job cwd, not muon-airss-out)
        allpos_matches = [n for n in files_retrieved if Path(n).stem == "allpos"]
        if allpos_matches:
            allpos_name = allpos_matches[0]
            with self.retrieved.open(allpos_name, "rb") as f:
                allpos_node = SinglefileData(file=f, filename=allpos_name)
            self.out("allpos_file", allpos_node)

        return ExitCode(0)
