"""CASTEP output parser that understands muon custom species.

aiida-castep's parser builds the output StructureData with

    out_structure.append_atom(symbols=symbol, position=position)

taking `symbol` straight from the CASTEP output. For a muon run that symbol is
``H:mu`` — a CASTEP custom species, not an element — so AiiDA raises
``UnsupportedSpeciesError`` and the whole parse dies, taking the energy and the
relaxed geometry with it even though neither had anything to do with the problem.

This parser reuses aiida-castep's parser wholesale and fixes only that one step,
splitting ``H:mu`` into element ``H`` with Kind name ``mu`` — the mirror image of
``_structure_data_from_atoms``, which builds the input structure the same way.
Keeping the Kind name is also what lets aiida-castep's own ``desort_structure``
succeed: it asserts the parsed kind names equal the input's.
"""

from contextlib import contextmanager

from aiida.orm import StructureData
from aiida.parsers.parser import Parser


def structure_from_custom_species(cell, positions, symbols) -> StructureData:
    """Build a StructureData, splitting ``element:label`` species into Kinds.

    A plain element symbol behaves exactly as before, so this is a drop-in
    replacement for aiida-castep's ``structure_from_input``.
    """
    structure = StructureData(cell=cell)
    for symbol, position in zip(symbols, positions):
        element, _, label = str(symbol).partition(":")
        if label:
            structure.append_atom(symbols=element, position=position, name=label)
        else:
            structure.append_atom(symbols=element, position=position)
    return structure


def _kind_of(species: str) -> str:
    """Kind name a CASTEP species maps to: ``H:mu`` -> ``mu``, ``Si`` -> ``Si``."""
    element, _, label = str(species).partition(":")
    return label or element


def desort_args_from_species(castep_species, structure) -> list:
    """Permutation taking CASTEP's atom order back to `structure`'s order.

    aiida-castep assumes CASTEP re-sorts atoms by atomic number and inverts that
    sort. With a custom species that assumption is wrong — CASTEP put ``H:mu``
    *after* Si rather than where hydrogen would go — and applying the inverse sort
    corrupts both the output structure and the trajectory arrays.

    Deriving the permutation from the species CASTEP actually reported avoids
    guessing. Sites are matched by kind name in order, which is well defined
    because CASTEP preserves the relative order of atoms within a species.
    """
    remaining = {}
    for index, species in enumerate(castep_species):
        remaining.setdefault(_kind_of(species), []).append(index)

    order = []
    for site in structure.sites:
        candidates = remaining.get(site.kind_name)
        if not candidates:
            raise ValueError(
                f"CASTEP returned no atom for kind {site.kind_name!r}; "
                f"got species {list(castep_species)!r}"
            )
        order.append(candidates.pop(0))
    return order


@contextmanager
def _custom_species_aware():
    """Make aiida-castep's parser handle custom species for one `parse()` call.

    Two module-level names in ``aiida_castep.parsers.castep`` need replacing and
    neither has a subclass hook, so they are swapped for the duration of the parse:

    * ``structure_from_input`` — builds the output StructureData; the stock one
      passes ``H:mu`` to AiiDA as an element and raises UnsupportedSpeciesError.
    * ``get_desort_args`` — un-sorts CASTEP's atom order; the stock one assumes a
      sort by atomic number that custom species do not follow.

    ``parse()`` is synchronous, so the swap cannot interleave with another parse in
    the same daemon worker.
    """
    from aiida_castep.parsers import castep as castep_parser_module
    from aiida_castep.parsers import utils as castep_utils_module

    seen_species = {}

    def _record_and_build(cell, positions, symbols):
        seen_species["symbols"] = list(symbols)
        return structure_from_custom_species(cell, positions, symbols)

    def _desort_args(original_structure):
        symbols = seen_species.get("symbols")
        if symbols is None or not any(":" in str(s) for s in symbols):
            # No custom species involved: leave aiida-castep's behaviour alone.
            return original_get_desort_args(original_structure)
        return desort_args_from_species(symbols, original_structure)

    original_build = castep_parser_module.structure_from_input
    original_get_desort_args = castep_utils_module.get_desort_args

    # Both modules need patching: castep.py uses get_desort_args directly for the
    # trajectory arrays, while desort_structure resolves it from utils.py, its own
    # module namespace.
    castep_parser_module.structure_from_input = _record_and_build
    castep_parser_module.get_desort_args = _desort_args
    castep_utils_module.get_desort_args = _desort_args
    try:
        yield
    finally:
        castep_parser_module.structure_from_input = original_build
        castep_parser_module.get_desort_args = original_get_desort_args
        castep_utils_module.get_desort_args = original_get_desort_args


def _castep_parser_class():
    """Return aiida-castep's parser class, or None when it is not installed."""
    try:
        from aiida_castep.parsers.castep import CastepParser
    except ImportError:
        return None
    return CastepParser


_BASE = _castep_parser_class()


if _BASE is None:  # pragma: no cover - exercised only without aiida-castep

    class CastepMuonParser(Parser):
        """Placeholder used when aiida-castep is not installed."""

        def parse(self, **kwargs):
            raise ImportError(
                "pymuon.castep_muon requires aiida-castep: pip install -e '.[castep]'"
            )

else:

    class CastepMuonParser(_BASE):
        """aiida-castep's CastepParser, made aware of muon custom species."""

        def parse(self, **kwargs):
            with _custom_species_aware():
                return super().parse(**kwargs)
