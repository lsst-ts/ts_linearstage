##############
ts-LinearStage
##############

The LinearStage is a CSC for the Vera C. Rubin Observatory.
It provides controls for `Zaber LST stages <https://zaber.com/manuals/LST>`_.

Installation
============

.. code::

    setup -kr .
    scons

.. code::

    pip install .[dev]
    pytest --cov lsst.ts.LinearStage -ra

Requirements
------------
Run the ``develop-env`` docker image.

Usage
=====
The LinearStage is an indexable component.
The index refers to the id of the particular device.

.. code::

    from lsst.ts import salobj
    
    linear_stage = salobj.Remote(name="LinearStage", domain=salobj.Domain(), index=1)
    linear_stage_2 = salobj.Remote(name="LinearStage", domain=salobj.Domain(), index=2)
    
    await linear_stage.start_task
    await linear_stage_2.start_task

.. code::

    await linear_stage.cmd_getHome.set_start(timeout=10)
    await linear_stage.cmd_moveAbsolute.set_start(distance=10, timeout=10)
    await linear_stage.cmd_moveRelative.set_start(distance=10, timeout=10)
    await linear_stage.cmd_stop.set_start(timeout=10)

    await asyncio.gather(*[linear_stage.cmd_moveAbsolute.set_start(distance=10, timeout=10), linear_stage_2.cmd_moveAbsolute.set_start(distance=10, timeout=10)]

.. code::

    position = await linear_stage.tel_position.aget()
    print(position.position)

Support
=======
N/A


Roadmap
=======
N/A

Contributing
============
N/A

License
=======
This project is licensed under the `GPLv3 <https://www.gnu.org/licenses/gpl-3.0.en.html>`_.