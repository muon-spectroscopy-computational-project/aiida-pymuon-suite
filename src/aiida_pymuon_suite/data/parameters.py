"""UepParameters data node for aiida-pymuon-suite."""

from aiida.orm import Dict
from voluptuous import All, Any, Coerce, Optional, Range, Schema
import yaml


cmdline_options = {
    Optional("poisson_r", default=0.8): All(Coerce(float), Range(min=0.0)),
    Optional("vdw_scale", default=0.5): All(Coerce(float), Range(min=0.0)),
    Optional("random_seed"): int,
    Optional("allpos_ext"): Any("cell", "cif", "xyz"),
    Optional("geom_steps", default=30): All(int, Range(min=1)),
    Optional("geom_force_tol", default=0.05): All(Coerce(float), Range(min=0.0)),
    Optional("uep_gw_factor", default=5.0): All(Coerce(float), Range(min=0.0)),
    Optional("mu_symbol", default="H:mu"): str,
    Optional("supercell", default=1): Any(int, list),
    Optional("clustering_method", default="hier"): Any("hier", "kmeans"),
    Optional("clustering_hier_t", default=0.3): All(Coerce(float), Range(min=0.0)),
    Optional("clustering_kmeans_k", default=4): All(int, Range(min=1)),
    Optional("clustering_save_type", default=None): Any("structures", "input", None),
    Optional("clustering_save_format", default=None): Any(str, None),
}


class UepParameters(Dict):  # pylint: disable=too-many-ancestors
    """AiiDA Dict subclass for UEP optimisation parameters with voluptuous schema validation."""

    schema = Schema(cmdline_options)

    def __init__(self, dict=None, **kwargs):
        dict = self.validate(dict)
        super().__init__(dict=dict, **kwargs)

    def validate(self, parameters_dict):
        """Validate against the voluptuous schema; raises voluptuous.Error on failure."""
        return UepParameters.schema(parameters_dict)

    def render_yaml(self):
        """Return a YAML string suitable for pm-muairss params file."""
        params = dict(self.get_dict())

        if "allpos_ext" in params:
            params["allpos_filename"] = f"allpos.{params.pop('allpos_ext')}"
        params["calculator"] = "uep"
        params["charged"] = True
        params["out_folder"] = "muon-airss-out"

        # Omit None values — pm-muairss schema validators reject explicit null;
        # absent keys get the schema default (also None) without triggering validation.
        params = {k: v for k, v in params.items() if v is not None}

        return yaml.dump(params)

    def __str__(self):
        string = super().__str__()
        string += "\n" + str(self.get_dict())
        return string
