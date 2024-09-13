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
from functools import reduce

import botocore.exceptions
from boto3.dynamodb.conditions import And, Attr, Key

from .. import metric_store
from ..metric import MetricType, RequestStatusChange
from ..request import Request
from . import request_store
from . import boto3_session


logger = logging.getLogger(__name__)


def _iter_items(fn, **params):
    while True: 
        response = fn(**params)
        for item in response["Items"]:
            yield item
        if "LastEvaluatedKey" not in response:
            break
        params["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def _make_query(**kwargs):
    query = {}
    for k, v in kwargs.items():
        if k not in Request.__slots__:
            raise KeyError("Request has no key {}".format(k))

        if v is None:
            continue

        sub_doc_id = getattr(v, "id", None)
        if sub_doc_id is not None:
            query[k + ".id"] = sub_doc_id
            continue

        query[k] = Request.serialize_slot(k, v)

    return query


class DynamoDBRequestStore(request_store.RequestStore):

    def __init__(self, config=None, metric_store_config=None):
        if config is None:
            config = {}

        endpoint_url = config.get("endpoint_url")
        table_name = config.get("table_name", "requests")

        session = boto3_session.build_boto_session()
        dynamodb = session.resource("dynamodb", endpoint_url=endpoint_url)
        self.table = dynamodb.Table(table_name)

        try:
            kwargs = {
                "AttributeDefinitions": [{"AttributeName": "id", "AttributeType": "S"}, {"AttributeName": "status", "AttributeType": "S"}],
                "TableName": table_name,
                "KeySchema": [{"AttributeName": "id", "KeyType": "HASH"}],
                "GlobalSecondaryIndexes": [{
                    "IndexName": "status-index",
                    "KeySchema": [{"AttributeName": "status", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }],
                "BillingMode": "PAY_PER_REQUEST",
            }
            table = dynamodb.create_table(**kwargs)
            table.wait_until_exists()
        except dynamodb.meta.client.exceptions.ResourceInUseException:
            pass
        else:
            self.table = table

        self.metric_store = None
        if metric_store_config is not None:
            self.metric_store = metric_store.create_metric_store(metric_store_config)

    def get_type(self):
        return "dynamodb"

    def add_request(self, request):
        try:
            self.table.put_item(Item=request.serialize(), ConditionExpression=Attr("id").not_exists())
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
        response = self.table.get_item(Key={"id": id})
        if "Item" in response:
            return Request(from_dict=response["Item"])

    def get_requests(self, ascending=None, descending=None, limit=None, status=None, **kwargs):
        if ascending is not None and descending is not None:
            raise ValueError("Cannot sort by ascending and descending at the same time.")
        
        query = _make_query(**kwargs)
        key, value = next(iter(query.items()))
        filter_expr = Attr(key).eq(value)
        if status is not None:
            key_cond_expr = Key("status").eq(query["status"])
            fn = self.table.query
            params = {
                "IndexName": "status-index",
                "KeyConditionExpression": key_cond_expr,
                "FilterExpression": filter_expr,
            }
        else:
            fn = self.table.scan
            params = {"FilterExpression": filter_expr}

        if limit is not None:
            params["Limit"] = limit

        reqs = (Request(from_dict=item) for item in _iter_items(fn, **params))
        if ascending:
            return sorted(reqs, key=lambda req: getattr(req, ascending))
        if descending:
            return sorted(reqs, key=lambda req: getattr(req, descending), reverse=True)
        return list(reqs)

    def update_request(self, request):
        request.last_modified = dt.datetime.utcnow().timestamp()
        self.table.put_item(Item=request.serialize())

    def wipe(self):
        if self.metric_store:
            for request in _iter_items(self.table.scan):
                self.metric_store.remove_metric(type=MetricType.REQUEST_STATUS_CHANGE, request_id=request.id)

        self.table.delete()

    def collect_metric_info(self):
        return {}
