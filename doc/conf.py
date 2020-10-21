"""Sphinx configuration file for TSSW package"""

from documenteer.sphinxconfig.stackconf import build_package_configs
import lsst.ts.LinearStage


_g = globals()
_g.update(
    build_package_configs(
        project_name="ts_LinearStage", version=lsst.ts.LinearStage.version.__version__
    )
)

intersphinx_mapping["ts_xml"] = ("https://ts-xml.lsst.io", None)
intersphinx_mapping["ts_salobj"] = ("https://ts-salobj.lsst.io", None)
intersphinx_mapping["ts_idl"] = ("https://ts-idl.lsst.io", None)
intersphinx_mapping["zaber_serial"] = (
    "https://www.zaber.com/support/docs/api/core-python/0.9.1",
    None,
)
intersphinx_mapping["pyserial"] = ("https://pyserial.readthedocs.io/en/latest", None)
