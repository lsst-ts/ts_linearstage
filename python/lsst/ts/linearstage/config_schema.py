import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_LinearStage/blob/master/schema/LinearStage.yaml
# title must end with one or more spaces followed by the schema version, which must begin with "v"
title: LinearStage v3
description: Schema for LinearStage configuration files
type: object
additionalProperties: false
properties:
    stage_type:
        description: Type of stage being controlled.
        type: string
        enum: [Zaber, Igus]
    target_position_minimum:
        description: >
          Minimum target position in mm
        type: number
    target_position_maximum:
        description: >
          Maximum target position in mm
        type: number
    serial_port:
        description: USB port for the serial interface
        type: string
    daisy_chain_address:
        description: The daisy-chain device address as located in the daisy chain (for Zaber Devices only)
        type: number
    steps_per_mm:
        description: This is approximately the amount of steps in a millimeter (for the Zaber stage only).
        type: number
    socket_address:
        description: The IP address to establish a socket connection (for use with Igus Dryve v1 controllers)
        type: string
        format: hostname
    socket_port:
        description: >
          The network port to establish a socket connection (for use with Igus Dryve v1
          controllers)
        type: number
    feed_rate:
        description: >
          Distance of travel [mm] per single motor rotation (for use with Igus Dryve v1
          controllers)
        type: number
    maximum_stroke:
        description: Maximum travel distance (stroke) from the homed position [mm]
        type: number
    homing_speed:
        description: >
          Speed to use for homing in millimeters per second [mm/s] (for use with Igus Dryve v1
          controllers)
        type: number
    homing_acceleration:
        description: >
          Acceleration to use for homing in millimeters per second squared [mm/s^2] (for use with
          Igus Dryve v1 controllers)
        type: number
    homing_timeout:
        description: >
          Amount of time to wait for homing to complete before timing out.
        type: number
    motion_speed:
        description: >
          Speed to use for standard travel motion in millimeters per second [mm/s] (for use with
          Igus Dryve v1 controllers)
        type: number
    motion_acceleration:
        description: >
          Acceleration to use for standard travel motion in millimeters per second squared [mm/s^2]
          (for use with Igus Dryve v1 controllers)
        type: number
allOf:
  - if:
      properties:
        stage_type:
          const: "Igus"
    then:
      required:
        - socket_address
        - socket_port
        - feed_rate
        - maximum_stroke
        - homing_speed
        - homing_acceleration
        - motion_speed
        - motion_acceleration
  - if:
      properties:
        stage_type:
          const: "Zaber"
    then:
      required:
        - target_position_minimum
        - target_position_maximum
        - serial_port
        - daisy_chain_address
        # DM-38124
        - steps_per_mm

"""
)
