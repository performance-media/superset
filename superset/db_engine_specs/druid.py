# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING

from superset import is_feature_enabled
from superset.db_engine_specs.base import BaseEngineSpec
from superset.exceptions import SupersetException
from superset.utils import core as utils

if TYPE_CHECKING:
    from superset.connectors.sqla.models import TableColumn
    from superset.models.core import Database

logger = logging.getLogger()


class DruidEngineSpec(BaseEngineSpec):  # pylint: disable=abstract-method
    """Engine spec for Druid.io"""

    engine = "druid"
    engine_name = "Apache Druid"
    allows_joins = is_feature_enabled("DRUID_JOINS")
    allows_subqueries = True

    _time_grain_expressions = {
        None: "{col}",
        "PT1S": "FLOOR({col} TO SECOND)",
        "PT5S": "TIME_FLOOR({col}, 'PT5S')",
        "PT30S": "TIME_FLOOR({col}, 'PT30S')",
        "PT1M": "FLOOR({col} TO MINUTE)",
        "PT5M": "TIME_FLOOR({col}, 'PT5M')",
        "PT10M": "TIME_FLOOR({col}, 'PT10M')",
        "PT15M": "TIME_FLOOR({col}, 'PT15M')",
        "PT0.5H": "TIME_FLOOR({col}, 'PT30M')",
        "PT1H": "FLOOR({col} TO HOUR)",
        "PT6H": "TIME_FLOOR({col}, 'PT6H')",
        "P1D": "FLOOR({col} TO DAY)",
        "P1W": "FLOOR({col} TO WEEK)",
        "P1M": "FLOOR({col} TO MONTH)",
        "P0.25Y": "FLOOR({col} TO QUARTER)",
        "P1Y": "FLOOR({col} TO YEAR)",
        "P1W/1970-01-03T00:00:00Z": (
            "TIMESTAMPADD(DAY, 5, FLOOR(TIMESTAMPADD(DAY, 1, {col}) TO WEEK))"
        ),
        "1969-12-28T00:00:00Z/P1W": (
            "TIMESTAMPADD(DAY, -1, FLOOR(TIMESTAMPADD(DAY, 1, {col}) TO WEEK))"
        ),
    }

    @classmethod
    def alter_new_orm_column(cls, orm_col: "TableColumn") -> None:
        if orm_col.column_name == "__time":
            orm_col.is_dttm = True

    @staticmethod
    def get_extra_params(database: "Database") -> Dict[str, Any]:
        """
        For Druid, the path to a SSL certificate is placed in `connect_args`.

        :param database: database instance from which to extract extras
        :raises CertificateException: If certificate is not valid/unparseable
        :raises SupersetException: If database extra json payload is unparseable
        """
        try:
            extra = json.loads(database.extra or "{}")
        except json.JSONDecodeError as ex:
            raise SupersetException("Unable to parse database extras") from ex

        if database.server_cert:
            engine_params = extra.get("engine_params", {})
            connect_args = engine_params.get("connect_args", {})
            connect_args["scheme"] = "https"
            path = utils.create_ssl_cert_file(database.server_cert)
            connect_args["ssl_verify_cert"] = path
            engine_params["connect_args"] = connect_args
            extra["engine_params"] = engine_params
        return extra

    @classmethod
    def convert_dttm(cls, target_type: str, dttm: datetime) -> Optional[str]:
        tt = target_type.upper()
        if tt == utils.TemporalType.DATE:
            return f"CAST(TIME_PARSE('{dttm.date().isoformat()}') AS DATE)"
        if tt in (utils.TemporalType.DATETIME, utils.TemporalType.TIMESTAMP):
            return f"""TIME_PARSE('{dttm.isoformat(timespec="seconds")}')"""
        return None

    @classmethod
    def epoch_to_dttm(cls) -> str:
        """
        Convert from number of seconds since the epoch to a timestamp.
        """
        return "MILLIS_TO_TIMESTAMP({col} * 1000)"

    @classmethod
    def epoch_ms_to_dttm(cls) -> str:
        """
        Convert from number of milliseconds since the epoch to a timestamp.
        """
        return "MILLIS_TO_TIMESTAMP({col})"
