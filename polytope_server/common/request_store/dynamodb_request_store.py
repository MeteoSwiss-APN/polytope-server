#
# Copyright 2022 European Centre for Medium-Range Weather Forecasts (ECMWF)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation nor
# does it submit to any jurisdiction.
#

import datetime as dt
import logging
from functools import partial, reduce
from typing import NamedTuple

import boto3
import botocore
import pydantic
from boto3.dynamodb.conditions import And, Attr, Key

from .. import metric_store
from ..metric import MetricType, RequestStatusChange
from ..request import Request
from . import request_store


logger = logging.getLogger(__name__)


class Config(pydantic.BaseModel):
    endpoint_url: str
    table_name: str


def _iter_items(fn):
    start_key = None
    while True:
        response = fn(ExclusiveStartKey=start_key)
        for item in response["Items"]:
            yield item
        start_key = response.get("LastEvaluatedKey")
        if start_key is None:
            break


class DynamoDBRequestStore(request_store.RequestStore):

    def __init__(self, config=None, metric_store_config=None):
        if config is None:
            config = {}

        endpoint_url = config.get("endpoint_url")
        table_name = config.get("table_name")

        dynamodb = boto3.resource("dynamodb", endpoint_url=endpoint_url)
        self.table = dynamodb.Table(table_name)

        self.metric_store = None
        if metric_store_config is not None:
            self.metric_store = metric_store.create_metric_store(metric_store_config)

    def get_type(self):
        return "dynamodb"

    def add_request(self, request):
        try:
            self.table.put_item(Item=request.serialize(), conditionExpression=Attr("id").notexists())
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError("Request already exists in request store") from e
            raise

        if self.metric_store:
            self.metric_store.add_metric(RequestStatusChange(request_id=request.id, status=request.status))

        logger.info("Request ID {} status set to {}.".format(request.id, request.status))

    def remove_request(self, id):
        self.table.delete_item(Key={"id": id})

    def get_request(self, id):
        self.table.query(
            Key={"id": id},
        )

    def get_requests(self, ascending=None, descending=None, limit=None, status=None, **kwargs):
        filter_expr = reduce(And, Attr(key).eq(value) for key, value in kwargs.items())
        if status is not None:
            key_cond_expr = Key("status").eq(kwargs["status"])
            fn = partial(
                self.table.query,
                KeyConditionExpression=key_cond_expr,
                FilterExpression=filter_expr,
                Limit=limit,
            )
        else:
            fn = partial(self.table.scan, FilterExpression=filter_expr, Limit=limit)
        return [Request(from_dict=item) for item in _iter_items(fn)]

    def update_request(self, request):
        request.last_modified = dt.datetime.utcnow().timestamp()
        self.table.put_item(Item=request.serialize())

    def wipe(self):
        if self.metric_store:
            for request in _iter_items(self.table.scan):
                self.metric_store.remove_metric(type=MetricType.REQUEST_STATUS_CHANGE, request_id=request.id)

        self.table.delete()

    def collect_metric_data(self):
        return {}
