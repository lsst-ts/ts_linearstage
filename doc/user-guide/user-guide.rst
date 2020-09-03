.. _user-guide:user-guide:user-guide:

#######################
LinearStage User Guide
#######################


The LinearStage is a simple device.
It has one axis of movement.
It has two types of movement, relative and absolute.
Relative starts from the current position of the device and absolute just goes to the set position.
The device is always homed in the enabled state.
Homing just means that the device goes back to the beginning of the track to find a reference position.
The stage uses converted millimeters as the unit of movement.

.. _user-guide:user-guide:interface:

LinearStage Interface
======================

Find the xml location at the top of the :doc:`index page </index>`.


.. _user-guide:user-guide:example-use-case:

Example Use-Case
================

.. code::

    from lsst.ts import salobj

    domain = salobj.Domain()

    linear_stage = salobj.Remote(name="LinearStage", domain=domain, index=1)
    linear_stage_2 = salobj.Remote(name="LinearStage", domain=domain, index=2)

    await linear_stage.start_task
    await linear_stage_2.start_task

.. code::

    await linear_stage.cmd_moveRelative.set_start(position=10)
    await linear_stage.cmd_moveAbsolute.set_start(position=20)
    await linear_stage.cmd_home.set_start(timeout=10)

    await asyncio.gather(*[linear_stage.cmd_moveAbsolute.set_start(distance=10, timeout=10), linear_stage_2.cmd_moveAbsolute.set_start(distance=10, timeout=10)]

.. code::

    position = await linear_stage.tel_position.aget()

.. code::

    await domain.close()

