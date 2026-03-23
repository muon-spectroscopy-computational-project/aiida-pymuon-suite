#!/usr/bin/env python
"""Run a test calculation on localhost.

Usage: ./example_01.py
"""

from os import path

import click
from aiida import cmdline, engine
from aiida.orm import SinglefileData
from aiida.plugins import CalculationFactory, DataFactory
from aiida_pymuon_suite import helpers

INPUT_DIR = path.join(path.dirname(path.realpath(__file__)), "input_files")


def test_run(pymuon_code):
    """Run a calculation on the localhost computer.

    Uses test helpers to create AiiDA Code on the fly.
    """
    if not pymuon_code:
        # get code
        computer = helpers.get_computer()
        pymuon_code = helpers.get_code(
            entry_point="pymuon.uep", computer=computer
        )

    # Prepare input parameters
    uep_parameters = DataFactory("pymuon.uep")
    parameters = uep_parameters({
        "poisson_r": 0.8,
        "vdw_scale": 0.5,
        "geom_steps": 30,
        "geom_force_tol": 0.05,
        "uep_gw_factor": 5.0,
        "allpos_ext": "xyz",
    })

    structure = SinglefileData(file=path.join(INPUT_DIR, "Si.cell"))
    charge_density = SinglefileData(file=path.join(INPUT_DIR, "Si.den_fmt"))
    castep_log = SinglefileData(file=path.join(INPUT_DIR, "Si.castep"))

    # set up calculation
    inputs = {
        "code": pymuon_code,
        "parameters": parameters,
        "structure": structure,
        "charge_density": charge_density,
        "castep_log": castep_log,
        "metadata": {
            "description": "Test job submission with the aiida-pymuon-suite plugin",
        },
    }

    # Note: in order to submit your calculation to the aiida daemon, do:
    # from aiida.engine import submit
    result = engine.run(CalculationFactory("pymuon.uep"), **inputs)

    uep_result = result["allpos_files"].get_content()
    print(f"Uep result : \n{uep_result}")


@click.command()
@cmdline.utils.decorators.with_dbenv()
@cmdline.params.options.CODE()
def cli(code):
    """Run example.

    Example usage: $ ./example_01.py --code pm-muairss@localhost

    Alternative (creates pm-muairss@localhost-test code): $ ./example_01.py

    Help: $ ./example_01.py --help
    """
    test_run(code)


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
