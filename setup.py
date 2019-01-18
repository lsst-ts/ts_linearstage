from setuptools import setup

setup(
    name="ts-LinearStage",
    use_scm_version=True,
    packages=['lsst.ts.linearStage'],
    setup_requires=['setuptools-scm'],
    install_requires=["zaber.serial","argh"],
    zip_safe=False
)
