===============
Developer guide
===============

The project uses `hatch <https://hatch.pypa.io>`_ to run the tests, the linter
and the documentation build. Install it once with ``pip install hatch``.

Running the tests
+++++++++++++++++

Run the test suite with::

    hatch test

or, in an environment where the package is already installed::

    pip install -e '.[testing]'
    pytest -v

``hatch test --all`` runs the suite on every Python version in the hatch matrix
(3.9 to 3.12), and ``hatch test --cover`` adds a coverage report.

The tests run real ``pm-muairss`` and ``pm-uep-opt`` jobs on the silicon
fixtures in ``tests/input_files/``, so both executables must be on your
``PATH``; they are installed with ``pymuon-suite``. A full run takes a few
minutes. The test profile uses SQLite and needs no PostgreSQL or RabbitMQ.

Code style
++++++++++

Formatting and linting use `ruff <https://docs.astral.sh/ruff/>`_, configured in
``pyproject.toml`` (line length 120). To fix what can be fixed automatically::

    hatch fmt

To check without changing any files, as CI does::

    hatch fmt --check

Continuous integration
++++++++++++++++++++++

``.github/workflows/ci.yml`` runs on every push to ``main`` and ``dev`` and on
every pull request. It:

#. checks formatting and linting with ``hatch fmt --check``;
#. runs the tests on Python 3.10, 3.11 and 3.12;
#. builds the sdist and wheel, and checks that the wheel installs and registers
   its AiiDA entry points;
#. builds the container image. Running the workflow by hand with ``push_image``
   set also pushes the image to Harbor, which is how test instances get an image
   to deploy.

The documentation is not built in CI.

Building the documentation
++++++++++++++++++++++++++

The pages are in ``docs/source/``. Build them with::

    pip install -e '.[docs]'
    make -C docs html

and open ``docs/build/html/index.html`` in your browser. The build regenerates
the API pages in ``docs/source/apidoc/`` from the code.

``hatch run docs:build`` (or plain ``make -C docs``) runs a strict build that
treats every warning as an error. It does not pass yet, because some
cross-references to AiiDA classes do not resolve.

The documentation is not published online yet.

Making a release
++++++++++++++++

#. Set ``__version__`` in ``src/aiida_pymuon_suite/__init__.py``.
#. Commit, then tag the commit with the same version and push the tag::

       git tag -a v0.1.0 -m 'v0.1.0'
       git push origin v0.1.0

Pushing a ``v*`` tag starts ``.github/workflows/release.yml``. It reruns the
full CI checks, checks that the tag matches ``__version__``, creates a GitHub
release with the sdist and wheel attached, and pushes the container image to
Harbor, tagged with the version. The package is not published to PyPI.
