"""Unit tests for the muon-aware CASTEP parser helpers.

These cover the two assumptions in aiida-castep that break on custom species,
without needing CASTEP or a retrieved folder.
"""

import pytest
from aiida.orm import StructureData

CELL = [[0.0, 2.715, 2.715], [2.715, 0.0, 2.715], [2.715, 2.715, 0.0]]


def _input_structure():
    """Si with a muon last, exactly as cluster_muon_sites builds it."""
    structure = StructureData(cell=CELL)
    structure.append_atom(position=(0.0, 0.0, 0.0), symbols="Si")
    structure.append_atom(position=(1.3575, 1.3575, 1.3575), symbols="Si")
    structure.append_atom(position=(1.357, 1.357, 4.072), symbols="H", name="mu")
    return structure


def test_custom_species_becomes_its_own_kind():
    from aiida_pymuon_suite.parsers.castep_muon import structure_from_custom_species

    structure = structure_from_custom_species(
        cell=CELL,
        positions=[(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)],
        symbols=["Si", "H:mu"],
    )

    assert [(k.name, k.symbol) for k in structure.kinds] == [("Si", "Si"), ("mu", "H")]


def test_plain_symbols_are_unchanged():
    """Ordinary runs must behave exactly as aiida-castep's own builder does."""
    from aiida_pymuon_suite.parsers.castep_muon import structure_from_custom_species

    structure = structure_from_custom_species(
        cell=CELL, positions=[(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)], symbols=["Si", "H"]
    )

    assert [(k.name, k.symbol) for k in structure.kinds] == [("Si", "Si"), ("H", "H")]


def test_desort_recovers_input_order_when_castep_puts_the_muon_last():
    """CASTEP reports the custom species last, not where hydrogen would sort.

    aiida-castep assumes a sort by atomic number and would return [1, 2, 0],
    scrambling an order that is already correct.
    """
    from aiida_pymuon_suite.parsers.castep_muon import desort_args_from_species

    order = desort_args_from_species(["Si", "Si", "H:mu"], _input_structure())

    assert order == [0, 1, 2]


def test_desort_recovers_input_order_when_castep_reorders():
    from aiida_pymuon_suite.parsers.castep_muon import desort_args_from_species

    order = desort_args_from_species(["H:mu", "Si", "Si"], _input_structure())

    assert order == [1, 2, 0]


def test_desort_preserves_relative_order_within_a_species():
    """The two Si atoms must not be swapped: their positions differ."""
    from aiida_pymuon_suite.parsers.castep_muon import desort_args_from_species

    structure = StructureData(cell=CELL)
    structure.append_atom(position=(0.0, 0.0, 0.0), symbols="Si")
    structure.append_atom(position=(1.0, 1.0, 1.0), symbols="H", name="mu")
    structure.append_atom(position=(2.0, 2.0, 2.0), symbols="Si")

    order = desort_args_from_species(["Si", "Si", "H:mu"], structure)

    assert order == [0, 2, 1]


def test_desort_rejects_species_that_do_not_match_the_input():
    from aiida_pymuon_suite.parsers.castep_muon import desort_args_from_species

    with pytest.raises(ValueError, match="no atom for kind"):
        desort_args_from_species(["Si", "Si", "Si"], _input_structure())
