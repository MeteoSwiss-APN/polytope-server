import os

import pytest
from moto import mock_aws

from polytope_server.common import request, user
from polytope_server.common.request_store import dynamodb_request_store


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def mocked_aws(aws_credentials):
    with mock_aws():
        yield


def test_default_init(mocked_aws):
    store = dynamodb_request_store.DynamoDBRequestStore()
    assert store.get_type() == "dynamodb"


def test_add_request(mocked_aws):
    store = dynamodb_request_store.DynamoDBRequestStore()
    u1 = user.User("some-user", "some-realm")
    r1 = request.Request(user=u1, verb=request.Verb.RETRIEVE, status=request.Status.QUEUED)
    assert r1.user == u1
    store.add_request(r1)
    r2 = store.get_request(r1.id)
    assert r2 is not None
    assert r2.id == r1.id
    assert r2.user == r1.user
    assert r2.verb == r1.verb
    assert r2.status == r1.status


def test_add_request_duplicate(mocked_aws):
    store = dynamodb_request_store.DynamoDBRequestStore()
    req = request.Request()
    store.add_request(req)
    with pytest.raises(ValueError):
        store.add_request(req)


def test_remove_request(mocked_aws):
    store = dynamodb_request_store.DynamoDBRequestStore()
    req = request.Request()
    store.add_request(req)
    assert store.get_request(req.id) is not None
    store.remove_request(req.id)
    assert store.get_request(req.id) is None


@pytest.fixture(scope="function")
def populated(mocked_aws):
    def func():
        u1, u2, u3 = (user.User(f"user{i}", f"realm{i}") for i in (1, 2, 3))
        r1 = request.Request(user=u1, collection="hello", status=request.Status.PROCESSED)
        r2 = request.Request(user=u2, collection="hello", content_length=10)
        r3 = request.Request(user=u3, collection="hello2")
        store = dynamodb_request_store.DynamoDBRequestStore()
        for req in (r1, r2, r3):
            store.add_request(req)
        return store, [r1, r2, r3], [u1, u2, u3]
    return func

def test_get_requests_user(populated):
    store, (r1, *_), (u1, *_) = populated()
    res = store.get_requests(user=u1)
    assert res == [r1]

def test_get_requests_id(populated):
    store, (*_, r3), _ = populated()
    res = store.get_requests(id=r3.id)
    assert res == [r3]

def test_get_requests_scan(populated):
    store, (_, r2, _), _ = populated()
    res = store.get_requests(content_length=10)
    assert res == [r2]
