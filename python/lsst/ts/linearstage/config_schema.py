import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/2020-12/schema#
$id: https://github.com/lsst-ts/ts_LinearStage/blob/master/schema/LinearStage.yaml
# title must end with one or more spaces followed by the schema version, which must begin with "v"
title: LinearStage v4
description: Schema for LinearStage configuration files
type: object
properties:
  linear_stage_config:
    type: array
    items:
        sal_index:
            type: number
        target_position_minimum:
            type: number
        target_position_maximum:
            type: number
        stage_type:
            type: string
            enum:
                - Zaber
                - Igus
        zaber:
            $ref: #/definitions/zaber_controller
        igus:
            $ref: #/definitions/igus_controller
definitions:
  zaber_controller:
    type: object
    properties:
      serial_port:
        type: string
      daisy_chain_address:
        type: number
      steps_per_mm:
        type: number
  igus_controller:
    type: object
    properties:
      socket_address:
        type: string
        format: hostname
      socket_port:
        type: number
      feed_rate:
        type: number
      maximum_stroke:
        type: number
      homing_speed:
        type: number
      homing_acceleration:
       type: number
      homing_timeout:
        type: number
      motion_speed:
        type: number
      motion_acceleration:
        type: number
"""
)
