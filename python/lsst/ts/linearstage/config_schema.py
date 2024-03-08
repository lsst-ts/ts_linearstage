# This file is part of ts_linearstage.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_LinearStage/blob/master/schema/LinearStage.yaml
# title must end with one or more spaces followed by the schema version, which must begin with "v"
title: LinearStage v5
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
                - ZaberV2
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
