===============
Getting started
===============

This page should contain a short guide on what the plugin does and
a short example on how to use the plugin.

Installation
++++++++++++

Use the following commands to install the plugin::

    git clone https://github.com/muon-spectroscopy-computational-project/aiida-pymuon-suite.git
    cd aiida-pymuon-suite
    pip install -e .  # also installs aiida, if missing (but not postgres)
    #pip install -e .[pre-commit,testing] # install extras for more features
    verdi presto  # set up a new profile (add --use-postgres for PostgreSQL)
    verdi plugin list aiida.calculations  # should now show your calculation plugins

Then set up one AiiDA code for each pymuon-suite executable, using the
``pymuon.muairss`` and ``pymuon.uep_opt`` calculation plugins::

    verdi code create core.code.installed --label pm-muairss --computer localhost \
        --filepath-executable "$(which pm-muairss)" --default-calc-job-plugin pymuon.muairss
    verdi code create core.code.installed --label pm-uep-opt --computer localhost \
        --filepath-executable "$(which pm-uep-opt)" --default-calc-job-plugin pymuon.uep_opt

Usage
+++++

Run the full UEP muon-site workflow on the silicon example::

    cd examples
    python example_01.py --muairss-code pm-muairss@localhost --uep-code pm-uep-opt@localhost
    verdi process list -a  # check the status of the processes

The example runs in the foreground, so the daemon does not need to be running.
If you leave out ``--muairss-code`` and ``--uep-code``, it creates the codes
from the executables on your ``PATH``. Run ``python example_01.py --help`` for
all options.

Two more examples start from a CASTEP calculation (see :doc:`castep_integration`):

* ``example_02_castep_route_b.py`` — pass existing ``.den_fmt`` and ``.castep`` files.
* ``example_03_castep_route_a.py`` — let AiiDA run CASTEP first (needs ``aiida-castep``).

The plugin also adds a ``verdi`` command for the ``UepParameters`` nodes in
your database::

    verdi data pymuon.uep list         # list all UepParameters nodes
    verdi data pymuon.uep export <PK>  # print a node's parameters (-o FILE to save them)

Available calculations
++++++++++++++++++++++

.. aiida-calcjob:: MuairssCalculation
    :module: aiida_pymuon_suite.calculations

.. aiida-calcjob:: UepOptCalculation
    :module: aiida_pymuon_suite.calculations
