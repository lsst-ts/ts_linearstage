"""Sphinx configuration file for TSSW package"""

from documenteer.sphinxconfig.stackconf import build_package_configs
import lsst.ts.LinearStage


_g = globals()
_g.update(build_package_configs(
    project_name='ts_LinearStage',
    version=lsst.ts.LinearStage.version.__version__
))

intersphinx_mapping["ts_xml"] = ("https://ts-xml.lsst.io", None)
