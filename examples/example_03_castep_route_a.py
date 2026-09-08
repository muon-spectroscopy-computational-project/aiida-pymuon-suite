#!/usr/bin/env python
"""Run CastepMuairssUepWorkChain with CASTEP executed by AiiDA (route A).

The workchain runs a CastepBaseWorkChain on the pristine host first, then
feeds its charge density into the UEP pipeline. `write_formatted_density`
and the `*.den_fmt` retrieve entry are injected automatically — the CASTEP
inputs below need to know nothing about UEP.

Requirements beyond example_02:
  * `pip install -e '.[castep]'` (aiida-castep)
  * a configured CASTEP code (e.g. `castep@my-cluster`)
  * an OTFG pseudopotential family, e.g.:
        from aiida_castep.data.otfg import upload_otfg_family
        upload_otfg_family(["C19"], "C19", "C19 library", stop_if_existing=False)

The CASTEP settings below (PBE, 350 eV, k-spacing 0.1/Å, C19 OTFG) are the
configuration verified end-to-end on STFC SCARF (CASTEP 26.1, 4 MPI procs,
minutes on a devel partition).

Usage:
    ./example_03_castep_route_a.py --castep-code castep@my-cluster \
        --muairss-code pm-muairss@localhost --uep-code pm-uep-opt@localhost
"""

from os import path

import click
from aiida import cmdline, engine
from aiida.orm import Dict, Float, Str, StructureData
from aiida.plugins import DataFactory, WorkflowFactory
from aiida_pymuon_suite import helpers
from ase import io as ase_io

INPUT_DIR = path.join(path.dirname(path.abspath(__file__)), "input_files")


def run_workflow(castep_code, muairss_code, uep_code, pseudos_family, mpi_procs):
    """Run CastepMuairssUepWorkChain (route A) on the Si test case."""
    if not muairss_code:
        computer = helpers.get_computer()
        muairss_code = helpers.get_code(entry_point="pymuon.muairss", computer=computer)
    if not uep_code:
        computer = helpers.get_computer()
        uep_code = helpers.get_code(entry_point="pymuon.uep_opt", computer=computer)

    uep_parameters = DataFactory("pymuon.uep")
    structure = StructureData(ase=ase_io.read(path.join(INPUT_DIR, "Si.cell")))

    castep_inputs = {
        "kpoints_spacing": Float(0.1),
        "pseudos_family": Str(pseudos_family),
        # NB: job resources go in `calc_options`, not `options` — the latter is
        # CastepBaseWorkChain behaviour (e.g. use_castep_bin), not job metadata.
        "calc_options": Dict(
            {
                "resources": {"num_machines": 1, "num_mpiprocs_per_machine": mpi_procs},
                "max_wallclock_seconds": 1800,
            }
        ),
        "calc": {
            "code": castep_code,
            "parameters": Dict(
                {
                    "PARAM": {
                        "task": "singlepoint",
                        "xc_functional": "pbe",
                        "cut_off_energy": 350,
                    },
                    "CELL": {"symmetry_generate": True},
                }
            ),
        },
    }

    print("Running CastepMuairssUepWorkChain (route A: CASTEP run by AiiDA) ...")
    result, node = engine.run_get_node(
        WorkflowFactory("pymuon.castep_muairss_uep"),
        structure=structure,
        castep=castep_inputs,
        muairss_code=muairss_code,
        uep_code=uep_code,
        parameters=uep_parameters({"geom_steps": 30}),
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
    "--castep-code",
    required=True,
    type=cmdline.params.types.CodeParamType(),
    help="CASTEP code on the compute resource (e.g. castep@my-cluster).",
)
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
    "--pseudos-family",
    default="C19",
    show_default=True,
    help="OTFG pseudopotential family label.",
)
@click.option(
    "--mpi-procs",
    default=4,
    type=int,
    show_default=True,
    help="MPI processes for the CASTEP job.",
)
def cli(castep_code, muairss_code, uep_code, pseudos_family, mpi_procs):
    """Run the muon stopping sites workflow with CASTEP executed by AiiDA (route A)."""
    run_workflow(castep_code, muairss_code, uep_code, pseudos_family, mpi_procs)


if __name__ == "__main__":
    cli()
