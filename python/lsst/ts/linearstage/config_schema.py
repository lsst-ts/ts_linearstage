import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_LinearStage/blob/master/schema/LinearStage.yaml
# title must end with one or more spaces followed by the schema version, which must begin with "v"
title: LinearStage v4
description: Schema for LinearStage configuration files
type: object
properties:
  instances:
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
        stage_config:
            type: object
    required:
        - sal_index
        - target_position_minimum
        - target_position_maximum
        - stage_type
        - stage_config
    additionalProperties: false
required:
    - instances
additionalProperties: false
"""
)
