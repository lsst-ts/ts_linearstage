#########################
LinearStage
#########################

.. image:: https://img.shields.io/badge/SAL-API-gray.svg
    :target: https://ts-xml.lsst.io/sal_interfaces/LinearStage.html
.. image:: https://img.shields.io/badge/GitHub-gray.svg
    :target: https://github.com/lsst-ts/ts_LinearStage
.. image:: https://img.shields.io/badge/Jira-gray.svg
    :target: https://jira.lsstcorp.org/issues/?jql=labels+%3D+ts_LinearStage
.. image:: https://img.shields.io/badge/Jenkins-gray.svg
    :target: https://tssw-ci.lsst.org/job/LSST_Telescope-and-Site/job/ts_LinearStage/

.. TODO: Delete the note when the page becomes populated

.. Warning::

   **This CSC documentation is under development and not ready for active use.**

.. _index:overview:

Overview
========

:ref:`Contact info <ts_xml:index:master-csc-table:LinearStage>`

The LinearStage controls a Zaber single axis linear stage.
Its purpose is to provide motor control for calibration work done in the Calibration Lab.

.. note:: If you are interested in viewing other branches of this repository append a `/v` to the end of the url link. For example `https://ts-linearstage.lsst.io/v/`


.. _index:user-documentation:

User Documentation
==================

.. This template has the user documentation in a subfolder.
.. However, in cases where the user documentation is extremely short (<50 lines), one may move that content here and remove the subfolder.
.. This will require modification of the heading styles and possibly renaming of the labels.
.. If the content becomes too large, then it must be moved back to a subfolder and reformatted appropriately.

User-level documentation, found at the link below, is aimed at personnel looking to perform the standard use-cases/operations with the LinearStage.

.. toctree::
    user-guide/user-guide
    :maxdepth: 2

.. _index:configuration:

Configuring the LinearStage
=========================================
.. For CSCs where configuration is not required, this section can contain a single sentence stating so.
   More introductory information can also be added here (e.g. CSC XYZ requires both a configuration file containing parameters as well as several look-up tables to be operational).

The configuration for the LinearStage is described at the following link.

.. toctree::
    configuration/configuration
    :maxdepth: 1


.. _index:development-documentation:

Development Documentation
=========================

.. This template has the user documentation in a subfolder.
.. However, in cases where the user documentation is extremely short (<50 lines), one may move that content here and remove the subfolder.
.. This will require modification of the heading styles and possibly renaming of the labels.
.. If the content becomes too large, then it must be moved back to a subfolder and reformatted appropriately.

This area of documentation focuses on the classes used, API's, and how to participate to the development of the LinearStage software packages.

.. toctree::
    developer-guide/developer-guide
    :maxdepth: 1

.. _index:version-history:

Version History
===============

.. At the time of writing the Version history/release notes are not yet standardized amongst CSCs.
.. Until then, it is not expected that both a version history and a release_notes be maintained.
.. It is expected that each CSC link to whatever method of tracking is being used for that CSC until standardization occurs.
.. No new work should be required in order to complete this section.

The version history of the LinearStage is found at the following link.

.. toctree::
    version-history
    :maxdepth: 1
