"""Data types provided by plugin

Register data types via the "aiida.data" entry point in setup.json.
"""

# You can directly use or subclass aiida.orm.data.Data
# or any other data type listed under 'verdi data'
from aiida.orm import Dict
from voluptuous import All, Any, Coerce, Optional, Range, Schema
import yaml


cmdline_options = {
    Optional("poisson_r", default=0.8): All(Coerce(float), Range(min=0.0)),
    Optional("vdw_scale", default=0.5): All(Coerce(float), Range(min=0.0)),
    Optional("random_seed"): int,
    Optional("allpos_ext"): Any("cell","cif","xyz"),
    Optional("geom_steps", default=30): All(int, Range(min=1)),
    Optional("geom_force_tol", default=0.05): All(Coerce(float), Range(min=0.0)),
    Optional("uep_gw_factor", default=5.0): All(Coerce(float), Range(min=0.0))
    
}

class UepParameters(Dict):  # pylint: disable=too-many-ancestors
    """
    Command line options for UEP optimisation parameters.

    This class represents a python dictionary used to
    pass command line options to the executable.
    """

    # "voluptuous" schema  to add automatic validation
    schema = Schema(cmdline_options)

    # pylint: disable=redefined-builtin
    def __init__(self, dict=None, **kwargs):
        """
        Constructor for the data class

        Usage: ``UepParameters(dict{'poisson_r': 0.8})``

        :param parameters_dict: dictionary with commandline parameters
        :param type parameters_dict: dict

        """
        dict = self.validate(dict)
        super().__init__(dict=dict, **kwargs)

    def validate(self, parameters_dict):
        """Validate command line options.

        Uses the voluptuous package for validation. Find out about allowed keys using::

            print(UepParameters.schema.schema)

        :param parameters_dict: dictionary with commandline parameters
        :param type parameters_dict: dict
        :returns: validated dictionary
        """
        return UepParameters.schema(parameters_dict)

    # def cmdline_params(self, file1_name, file2_name):
    #     """Synthesize command line parameters.

    #     e.g. [ '--ignore-case', 'filename1', 'filename2']

    #     :param file_name1: Name of first file
    #     :param type file_name1: str
    #     :param file_name2: Name of second file
    #     :param type file_name2: str

    #     """
    #     parameters = []

    #     pm_dict = self.get_dict()
    #     for option, enabled in pm_dict.items():
    #         if enabled:
    #             parameters += ["--" + option]

    #     parameters += [file1_name, file2_name]

    #     return [str(p) for p in parameters]

    def render_yaml(self):
        """ render parameters as yaml for pm-muairss"""
        params = dict(self.get_dict())

        if 'allpos_ext' in params:
            params["allpos_filename"] = f"allpos.{params.pop('allpos_ext')}"
        params["calculator"] = "uep"
        params["charged"] = True
        params["out_folder"] = "muon-airss-out"

        return yaml.dump(params)

    def __str__(self):
        """String representation of node.

        Append values of dictionary to usual representation. E.g.::

            uuid: b416cbee-24e8-47a8-8c11-6d668770158b (pk: 590)
            {'poisson_r': 0.8, 'vdw_scale': 0.5, 'geom_steps': 30, 'geom_force_tol': 0.05, 'uep_gw_factor': 5.0}

        """
        string = super().__str__()
        string += "\n" + str(self.get_dict())
        return string
