"""
Parsers provided by aiida-pymuon-suite.

Register parsers via the "aiida.parsers" entry point in setup.json.
"""

from aiida.common import exceptions
from aiida.engine import ExitCode
from aiida.orm import SinglefileData
from aiida.parsers.parser import Parser
from aiida.plugins import CalculationFactory

UepCalculation = CalculationFactory("pymuon.uep")


class UepParser(Parser):
    """
    Parser class for parsing output of UEP optimisation calculation.
    """

    def __init__(self, node):
        """
        Initialize Parser instance

        Checks that the ProcessNode being passed was produced by a UepCalculation.

        :param node: ProcessNode of calculation
        :param type node: :class:`aiida.orm.nodes.process.process.ProcessNode`
        """
        super().__init__(node)
        if not issubclass(node.process_class, UepCalculation):
            raise exceptions.ParsingError("Can only parse UepCalculation")

    def parse(self, **kwargs):
        """
        Parse outputs, store results in database.

        :returns: an exit code, if parsing fails (or nothing if parsing succeeds)
        
        """

        files_retrieved = self.retrieved.list_object_names()

        #check output folder was produced
        if "muon-airss-out" not in files_retrieved:
            self.logger.error(f"Output folder 'muon-airss-out' not found in retrieved files. {files_retrieved}")
            return self.exit_codes.ERROR_MISSING_OUTPUT_FILES
        
        #check UEP optimisation results(.uep files)
        uep_files = [f for f in self.retrieved.list.object_names("muon-airss-out") if f.endswith(".uep")]
        if not uep_files:
            self.logger.error("No UEP optimisation output files (.uep) found in 'muon-airss-out' all optimisation failed.")
            return self.exit_codes.ERROR_MISSING_OUTPUT_FILES
        
        # count structure for logging
        struct_dirs = set()
        for f in self.retrieved.list.object_names("muon-airss-out", True):
            parts = f.split("/")
            if len(parts) >= 3:
                struct_dirs.add(parts[1])
        self.logger.info(f"Found {len(uep_files)} UEP optimisation output files (.uep) for {len(struct_dirs)} muonated structures.")
        #output the retrieved folder as upe_results
        self.out("uep_results", self.retrieved)

        #handl opitional allpos file

        allpos_files = [f for f in self.retrieved if f.sstartswith("allpos.")]
        if allpos_files:
            with self.retrieved.open(allpos_files[0], "rb") as handle:
                allpos_node = SinglefileData(file=handle)
            self.out("allpos_files", allpos_node)
        
        return ExitCode(0)