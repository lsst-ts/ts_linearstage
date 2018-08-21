Linear Stage Component
++++++++++++++++++++++

This is the readme for the linear stage python api.

Manual
------
This is the manual_ for the linear stage from Zaber_.

.. _manual: https://www.zaber.com/manuals/A-LST
.. _Zaber: https://www.zaber.com/

Installation
------------
This package should be installed using the eups method.

.. code-block:: bash

    pip install zaber.serial
    # if necessary declare ts_statemachine and salpytools
    eups declare -r . ts_statemachine -t $USER
    eups setup ts_statemachine -t $USER
    eups declare -r . salpytools -t $USER
    eups setup salpytools -t $USER
    ##########################################
    eups declare -r . ts_linearStage -t $USER
    eups setup ts_linearStage -t $USER

Examples for running the linearStage are located in the bin/notebook directory.