"""pytest fixtures for simplified testing."""

import pytest

pytest_plugins = ["aiida.tools.pytest_fixtures"]


@pytest.fixture(scope="function", autouse=True)
def clear_database_auto(aiida_profile_clean):  # pylint: disable=unused-argument
    """Automatically clear database in between tests."""


@pytest.fixture(scope="function")
def muairss_code(aiida_computer_local, aiida_code_installed):
    """InstalledCode for pm-muairss (MuairssCalculation)."""
    return aiida_code_installed(
        computer=aiida_computer_local(),
        filepath_executable="pm-muairss",
        default_calc_job_plugin="pymuon.muairss",
    )


@pytest.fixture(scope="function")
def uep_opt_code(aiida_computer_local, aiida_code_installed):
    """InstalledCode for pm-uep-opt (UepOptCalculation)."""
    return aiida_code_installed(
        computer=aiida_computer_local(),
        filepath_executable="pm-uep-opt",
        default_calc_job_plugin="pymuon.uep_opt",
    )
