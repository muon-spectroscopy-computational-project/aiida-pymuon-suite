==================
CASTEP integration
==================

The UEP method needs three artefacts of a CASTEP calculation on the pristine
host crystal: the structure, the formatted charge density (``.den_fmt``) and
the CASTEP log (``.castep``). ``CastepMuairssUepWorkChain`` (entry point
``pymuon.castep_muairss_uep``) wraps :class:`MuairssUepWorkChain` and offers
two ways — *routes* — of providing them. Exactly one route must be used per
run; a validator rejects anything else.

Route B — provide the files manually
------------------------------------

Pass the files as ``SinglefileData`` alongside a ``StructureData``::

    from aiida.engine import run_get_node
    from aiida.orm import SinglefileData, StructureData
    from aiida.plugins import DataFactory, WorkflowFactory

    UepParameters = DataFactory("pymuon.uep")

    result, node = run_get_node(
        WorkflowFactory("pymuon.castep_muairss_uep"),
        structure=structure,                              # StructureData
        charge_density=SinglefileData(file="Si.den_fmt"),
        castep_log=SinglefileData(file="Si.castep"),
        muairss_code=muairss_code,
        uep_code=uep_code,
        parameters=UepParameters({"geom_steps": 30}),
    )

The ``.cell`` file for ``pm-muairss`` is generated from the ``StructureData``
by the ``structure_to_cell`` calcfunction, so the conversion is part of the
provenance graph. If you prefer to pass the ``.cell`` file directly, use the
inner ``MuairssUepWorkChain`` (``pymuon.muairss_uep``) — it is unchanged.

Route A — let AiiDA run CASTEP
------------------------------

With the optional `aiida-castep <https://github.com/zhubonan/aiida-castep>`_
dependency installed (``pip install -e '.[castep]'``), the
workchain can run the host calculation itself. Provide the
``CastepBaseWorkChain`` inputs under the ``castep`` namespace::

    from aiida.orm import Dict, Float, Str

    castep_inputs = {
        "kpoints_spacing": Float(0.1),
        "pseudos_family": Str("C19"),
        "calc_options": Dict({
            "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 4},
            "max_wallclock_seconds": 1800,
        }),
        "calc": {
            "code": castep_code,
            "parameters": Dict({
                "PARAM": {"task": "singlepoint", "xc_functional": "pbe", "cut_off_energy": 350},
                "CELL": {"symmetry_generate": True},
            }),
        },
    }

    result, node = run_get_node(
        WorkflowFactory("pymuon.castep_muairss_uep"),
        structure=structure,
        castep=castep_inputs,
        muairss_code=muairss_code,
        uep_code=uep_code,
        parameters=UepParameters({"geom_steps": 30}),
    )

Two details are handled for you:

* ``write_formatted_density: true`` is injected into the PARAM block, and
* ``*.den_fmt`` is added to the calculation's ``ADDITIONAL_RETRIEVE_LIST``,

so the CASTEP inputs need to know nothing about UEP. The extracted
``.den_fmt``/``.castep`` files appear on the provenance graph through the
``extract_uep_inputs`` calcfunction.

.. note::
   Job resources for the CASTEP run go in the ``calc_options`` ``Dict``
   input of ``CastepBaseWorkChain`` — *not* ``options``, which controls
   workchain behaviour such as ``use_castep_bin``.

Exit codes
----------

===== ============================= ==============================================
Code  Label                         Meaning
===== ============================= ==============================================
410   ``ERROR_CASTEP_FAILED``       The CastepBaseWorkChain did not finish OK.
411   ``ERROR_UEP_INPUT_EXTRACTION`` No usable ``.den_fmt``/``.castep`` retrieved.
412   ``ERROR_MUAIRSS_UEP_FAILED``  The inner MuairssUepWorkChain failed.
===== ============================= ==============================================

See ``examples/example_02_castep_route_b.py`` and
``examples/example_03_castep_route_a.py`` for complete runnable scripts; the
route A settings shipped there were verified end-to-end on STFC SCARF
(CASTEP 26.1, Si, minutes on a devel partition).
