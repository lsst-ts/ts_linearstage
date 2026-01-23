v2.3.1 (2026-01-22)
===================

Other Changes and Additions
---------------------------

- Added python version to build string for conda package. (`OSW-1484 <https://rubinobs.atlassian.net//browse/OSW-1484>`_)
- Added more logging information. (`OSW-1530 <https://rubinobs.atlassian.net//browse/OSW-1530>`_)


v2.3.0 (2025-07-14)
===================

New Features
------------

- Added angle device support. (`DM-50241 <https://rubinobs.atlassian.net//browse/DM-50241>`_)
- Added retry loop to ZaberV2. (`DM-50241 <https://rubinobs.atlassian.net//browse/DM-50241>`_)
- Added getting home information from stage when connecting so that no unnecessary homes are performed. (`DM-50639 <https://rubinobs.atlassian.net//browse/DM-50639>`_)


Bug Fixes
---------

- Added missing stop method to Zaber stage. (`DM-50639 <https://rubinobs.atlassian.net//browse/DM-50639>`_)


Performance Enhancement
-----------------------

- Improved simulation mode to better match hardware. (`OSW-495 <https://rubinobs.atlassian.net//browse/OSW-495>`_)


API Removal or Deprecation
--------------------------

- Deprecated ZaberV1 code. (`DM-50639 <https://rubinobs.atlassian.net//browse/DM-50639>`_)


Other Changes and Additions
---------------------------

- Added type hints to support mypy. (`DM-50639 <https://rubinobs.atlassian.net//browse/DM-50639>`_)


v2.2.0 (2025-03-24)
===================

New Features
------------

- Added axis parameter support to telemetry topic and commands. (`DM-48609 <https://rubinobs.atlassian.net//browse/DM-48609>`_)


v2.1.0 (2024-11-20)
==================

New Features
-----------
- Added `stage_name` to the configuration of zaber_lst (ZaberV2) `stage_config`


v2.0.0 (2024-07-17)
===================

New Features
------------

- Added ZaberV2 stage class that uses tcpip connection. (`DM-42420 <https://rubinobs.atlassian.net//browse/DM-42420>`_)


Bug Fixes
---------

- Add XML 22 compatibility for ErrorCode enum being moved to ts_xml. (`DM-45062 <https://rubinobs.atlassian.net//browse/DM-45062>`_)
- Add ts-simactuators to conda recipe. (`DM-45242 <https://rubinobs.atlassian.net//browse/DM-45242>`_)


Documentation
-------------

- Added missing docstrings and updated out-of-date docstrings (`DM-42420 <https://rubinobs.atlassian.net//browse/DM-42420>`_)
- Added towncrier. (`DM-42420 <https://rubinobs.atlassian.net//browse/DM-42420>`_)

