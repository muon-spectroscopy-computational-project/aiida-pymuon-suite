"""Helper functions for automatically setting up computer & code.
Helper functions for setting up

 1. An AiiDA localhost computer
 2. A "pm-muairss" or "pm-uep-opt" code on localhost

Note: Both executables are provided by pymuon-suite and must be available in PATH.
"""

import shutil
import tempfile

from aiida.common.exceptions import NotExistent
from aiida.orm import Computer, InstalledCode

LOCALHOST_NAME = "localhost-test"

executables = {
    "pymuon.muairss": "pm-muairss",
    "pymuon.uep_opt": "pm-uep-opt",
}


def get_path_to_executable(executable):
    """Get path to local executable.
    :param executable: Name of executable in the $PATH variable
    :type executable: str
    :return: path to executable
    :rtype: str
    """
    path = shutil.which(executable)
    if path is None:
        raise ValueError(f"'{executable}' executable not found in PATH.")
    return path


def get_computer(name=LOCALHOST_NAME, workdir=None):
    """Get AiiDA computer.
    Loads computer 'name' from the database, if exists.
    Sets up local computer 'name', if it isn't found in the DB.

    :param name: Name of computer to load or set up.
    :param workdir: path to work directory
        Used only when creating a new computer.
    :return: The computer node
    :rtype: :py:class:`aiida.orm.computers.Computer`
    """

    try:
        computer = Computer.collection.get(label=name)
    except NotExistent:
        if workdir is None:
            workdir = tempfile.mkdtemp()

        computer = Computer(
            label=name,
            description="localhost computer set up by aiida-pymuon-suite tests",
            hostname=name,
            workdir=workdir,
            transport_type="core.local",
            scheduler_type="core.direct",
        )
        computer.store()
        computer.set_minimum_job_poll_interval(0.0)
        computer.configure()

    return computer


def get_code(entry_point, computer):
    """Get local code.
    Sets up code for given entry point on given computer.

    :param entry_point: Entry point of calculation plugin
    :param computer: (local) AiiDA computer
    :return: The code node
    :rtype: :py:class:`aiida.orm.nodes.data.code.installed.InstalledCode`
    """

    try:
        executable = executables[entry_point]
    except KeyError as exc:
        raise KeyError(
            f"Entry point '{entry_point}' not recognized. Allowed values: {list(executables.keys())}"
        ) from exc

    codes = InstalledCode.collection.find(filters={"label": executable})
    if codes:
        return codes[0]
    path = get_path_to_executable(executable)
    code = InstalledCode(
        label=executable,
        computer=computer,
        filepath_executable=path,
        default_calc_job_plugin=entry_point,
    )
    return code.store()