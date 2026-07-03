#!/usr/bin/env python
"""Run CastepMuairssUepWorkChain with manually provided CASTEP files (route B).

Same physics as example_01, but through the CASTEP-aware outer workchain: the
structure is a proper StructureData node and the .cell file for pm-muairss is
generated on the provenance graph by the structure_to_cell calcfunction.

Usage:
    ./example_02_castep_route_b.py --muairss-code pm-muairss@localhost --uep-code pm-uep-opt@localhost

    # Omit codes to auto-create them from PATH:
    ./example_02_castep_route_b.py
"""

from os import path

import click
from aiida import cmdline, engine
from aiida.orm import Int, SinglefileData, StructureData
from aiida.plugins import DataFactory, WorkflowFactory
from ase import io as ase_io

from aiida_pymuon_suite import helpers

INPUT_DIR = path.join(path.dirname(path.abspath(__file__)), "input_files")


def run_workflow(muairss_code, uep_code, max_concurrent):
    """Run CastepMuairssUepWorkChain (route B) on the Si test case."""
    if not muairss_code:
        computer = helpers.get_computer()
        muairss_code = helpers.get_code(entry_point="pymuon.muairss", computer=computer)
    if not uep_code:
        computer = helpers.get_computer()
        uep_code = helpers.get_code(entry_point="pymuon.uep_opt", computer=computer)

    uep_parameters = DataFactory("pymuon.uep")
    parameters = uep_parameters({"geom_steps": 30})

    structure = StructureData(ase=ase_io.read(path.join(INPUT_DIR, "Si.cell")))

    print("Running CastepMuairssUepWorkChain (route B: files provided manually) ...")
    result, node = engine.run_get_node(
        WorkflowFactory("pymuon.castep_muairss_uep"),
        structure=structure,
        charge_density=SinglefileData(file=path.join(INPUT_DIR, "Si.den_fmt")),
        castep_log=SinglefileData(file=path.join(INPUT_DIR, "Si.castep")),
        muairss_code=muairss_code,
        uep_code=uep_code,
        parameters=parameters,
        max_concurrent=Int(max_concurrent),
    )

    if not node.is_finished_ok:
        print(f"WorkChain FAILED — exit status {node.exit_status}: {node.exit_message}")
        return

    print(f"WorkChain finished OK (pk={node.pk})")
    print("Sub-processes:")
    for child in node.called:
        print(f"  {child.process_label}<{child.pk}> exit={child.exit_status}")
    print(f"muon_sites output: FolderData<{result['muon_sites'].pk}>")


@click.command()
@cmdline.utils.decorators.with_dbenv()
@click.option(
    "--muairss-code",
    default=None,
    type=cmdline.params.types.CodeParamType(),
    help="pm-muairss code (e.g. pm-muairss@localhost). Created from PATH if omitted.",
)
@click.option(
    "--uep-code",
    default=None,
    type=cmdline.params.types.CodeParamType(),
    help="pm-uep-opt code (e.g. pm-uep-opt@localhost). Created from PATH if omitted.",
)
@click.option(
    "--max-concurrent",
    default=4,
    type=int,
    show_default=True,
    help="Maximum number of UepOptCalculations to run concurrently.",
)
def cli(muairss_code, uep_code, max_concurrent):
    """Run the CASTEP-aware muon stopping sites workflow with manual files (route B)."""
    run_workflow(muairss_code, uep_code, max_concurrent)


if __name__ == "__main__":
    cli()
