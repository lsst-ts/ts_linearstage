###############
Version History
###############

.. At the time of writing the Version history/release notes are not yet standardized amongst CSCs.
.. Until then, it is not expected that both a version history and a release_notes be maintained.
.. It is expected that each CSC link to whatever method of tracking is being used for that CSC until standardization occurs.
.. No new work should be required in order to complete this section.
.. Below is an example of a version history format.

.. towncrier release notes start

v1.2.2
======

* Update ts-conda-build to 0.4.

v1.2.1
======
* Fix check index if statement so that it doesn't raise if index is not found first.
* Clean up pyproject.toml and meta.yaml

v1.2.0
======
* Update precommit to black v23, isort 5.12 & check-yaml 4.4.
* Renamed to lowercase linearstage namespace.
* Make everything relative imports.
* Update config_schema to use enums to divide device configurations.
* Use generate_pre_commit_conf and DevelopPipeline.

v1.1.0
======
* Added documentation
* Standardized repo layout
* Prepared CSC for salobj 6
* Added simulator and simulation mode to CSC
* Added black linter
* Upgrade to black 20.8
* Added igus drive support
* Update CSC to use salobj 7
* Use pyproject.toml

Requirements
------------
* ts_xml - v6.2.0
* ts_salobj - v7.x

v1.0.1
------
* Fixed CSC not starting

v1.0.0
------
* Initial release
* basic CSC
