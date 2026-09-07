[![Build Status][ci-badge]][ci-link]

# aiida-pymuon-suite

Aiida plugin for pymuon-suite

This plugin is the default output of the
[AiiDA plugin cutter](https://github.com/aiidateam/aiida-plugin-cutter),
intended to help developers get started with their AiiDA plugins.

## Repository contents

* [`.github/`](.github/): [Github Actions](https://github.com/features/actions) configuration
  * [`ci.yml`](.github/workflows/ci.yml): lints, runs the test suite on Python 3.10-3.12, builds the distributions and builds the container image on every push and pull request. Can also be run manually from the Actions tab with `push_image` set, to push a test-instance image to Harbor without cutting a release
  * [`release.yml`](.github/workflows/release.yml): on a `v*` tag, re-runs CI, publishes a GitHub release with the sdist and wheel attached, and pushes the container image to Harbor. Can also be re-run manually from the Actions tab against an existing tag, with either half switched off
* [`aiida-pymuon-suite/`](aiida-pymuon-suite/): The main source code of the plugin package
  * [`data/`](aiida-pymuon-suite/data/): A new `DiffParameters` data class, used as input to the `DiffCalculation` `CalcJob` class
  * [`calculations.py`](aiida-pymuon-suite/calculations.py): A new `DiffCalculation` `CalcJob` class
  * [`cli.py`](aiida-pymuon-suite/cli.py): Extensions of the `verdi data` command line interface for the `DiffParameters` class
  * [`helpers.py`](aiida-pymuon-suite/helpers.py): Helpers for setting up an AiiDA code for `diff` automatically
  * [`parsers.py`](aiida-pymuon-suite/parsers.py): A new `Parser` for the `DiffCalculation`
* [`docs/`](docs/): A documentation template ready for publication on [Read the Docs](http://aiida-diff.readthedocs.io/en/latest/)
* [`examples/`](examples/): An example of how to submit a calculation using this plugin
* [`tests/`](tests/): Basic regression tests using the [pytest](https://docs.pytest.org/en/latest/) framework (submitting a calculation, ...). Install `pip install -e .[testing]` and run `pytest`.
* [`.gitignore`](.gitignore): Telling git which files to ignore
* [`.pre-commit-config.yaml`](.pre-commit-config.yaml): Configuration of [pre-commit hooks](https://pre-commit.com/) that sanitize coding style and check for syntax errors. Enable via `pip install -e .[pre-commit] && pre-commit install`
* [`.readthedocs.yml`](.readthedocs.yml): Configuration of documentation build for [Read the Docs](https://readthedocs.org/)
* [`LICENSE`](LICENSE): License for your plugin
* [`README.md`](README.md): This file
* [`conftest.py`](conftest.py): Configuration of fixtures for [pytest](https://docs.pytest.org/en/latest/)
* [`pyproject.toml`](setup.json): Python package metadata for registration on [PyPI](https://pypi.org/) and the [AiiDA plugin registry](https://aiidateam.github.io/aiida-registry/) (including entry points)

See also the following video sequences from the 2019-05 AiiDA tutorial:

 * [run aiida-diff example calculation](https://www.youtube.com/watch?v=2CxiuiA1uVs&t=403s)
 * [aiida-diff CalcJob plugin](https://www.youtube.com/watch?v=2CxiuiA1uVs&t=685s)
 * [aiida-diff Parser plugin](https://www.youtube.com/watch?v=2CxiuiA1uVs&t=936s)
 * [aiida-diff computer/code helpers](https://www.youtube.com/watch?v=2CxiuiA1uVs&t=1238s)
 * [aiida-diff input data (with validation)](https://www.youtube.com/watch?v=2CxiuiA1uVs&t=1353s)
 * [aiida-diff cli](https://www.youtube.com/watch?v=2CxiuiA1uVs&t=1621s)
 * [aiida-diff tests](https://www.youtube.com/watch?v=2CxiuiA1uVs&t=1931s)
 * [Adding your plugin to the registry](https://www.youtube.com/watch?v=760O2lDB-TM&t=112s)
 * [pre-commit hooks](https://www.youtube.com/watch?v=760O2lDB-TM&t=333s)

For more information, see the [developer guide](https://aiida-diff.readthedocs.io/en/latest/developer_guide) of your plugin.


## Features

 * Add input files using `SinglefileData`:
   ```python
   SinglefileData = DataFactory('core.singlefile')
   inputs['file1'] = SinglefileData(file='/path/to/file1')
   inputs['file2'] = SinglefileData(file='/path/to/file2')
   ```

 * Specify command line options via a python dictionary and `DiffParameters`:
   ```python
   d = { 'ignore-case': True }
   DiffParameters = DataFactory('pymuon')
   inputs['parameters'] = DiffParameters(dict=d)
   ```

 * `DiffParameters` dictionaries are validated using [voluptuous](https://github.com/alecthomas/voluptuous).
   Find out about supported options:
   ```python
   DiffParameters = DataFactory('pymuon')
   print(DiffParameters.schema.schema)
   ```

## Installation

```shell
pip install aiida-pymuon-suite
verdi quicksetup  # better to set up a new profile
verdi plugin list aiida.calculations  # should now show your calclulation plugins
```


## Usage

Here goes a complete example of how to submit a test calculation using this plugin.

A quick demo of how to submit a calculation:
```shell
verdi daemon start     # make sure the daemon is running
cd examples
./example_01.py        # run test calculation
verdi process list -a  # check record of calculation
```

The plugin also includes verdi commands to inspect its data types:
```shell
verdi data pymuon list
verdi data pymuon export <PK>
```

## Development

```shell
git clone https://github.com/subindev-d/aiida-pymuon-suite .
cd aiida-pymuon-suite
pip install --upgrade pip
pip install -e .[pre-commit,testing]  # install extra dependencies
pre-commit install  # install pre-commit hooks
pytest -v  # discover and run all tests
```

See the [developer guide](http://aiida-pymuon-suite.readthedocs.io/en/latest/developer_guide/index.html) for more information.

## License

MIT
## Contact

subindev.devadasan@stfc.ac.uk


[ci-badge]: https://github.com/muon-spectroscopy-computational-project/aiida-pymuon-suite/actions/workflows/ci.yml/badge.svg
[ci-link]: https://github.com/muon-spectroscopy-computational-project/aiida-pymuon-suite/actions/workflows/ci.yml
