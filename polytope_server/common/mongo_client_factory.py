import typing
import urllib.parse

import pymongo


def create_client(
    host: str,
    port: str,
    username: typing.Optional[str] = None,
    password: typing.Optional[str] = None,
    tls: bool = False,
) -> pymongo.MongoClient:
    endpoint = f"{host}:{port}"

    if username and password:
        encoded_username = urllib.parse.quote_plus(username)
        encoded_password = urllib.parse.quote_plus(password)
        endpoint = f"{encoded_username}:{encoded_password}@{endpoint}"

    return pymongo.MongoClient(endpoint, journal=True, connect=False, tls=tls)
