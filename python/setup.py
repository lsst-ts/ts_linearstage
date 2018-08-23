from setuptools import find_packages, setup
version = {}
with open("lsst/ts/linearStage/version.py") as fp:
    exec(fp.read(), version)
# later on we use: version['__version__']

setup(
    name="ts_linearStage",
    version=version['__version__'],
    packages=['lsst.ts.linearStage'],
    install_requires=["zaber.serial"],
    zip_safe=False
)
