from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from djsonapi_client import DjsonApiSdk

HOST = "http://testserver"


def mock_aiohttp_response(status: int = 200, payload: dict | None = None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return resp


def patch_session(sdk, method: str, status: int = 200, payload: dict | None = None):
    from unittest.mock import patch as _patch

    resp = mock_aiohttp_response(status, payload)
    patcher = _patch.object(sdk._session, method, return_value=resp)
    return patcher


@pytest.fixture
def sdk():
    return DjsonApiSdk(host=HOST)


@pytest.fixture
def article_type(sdk):
    return sdk.articles


@pytest.fixture
def user_type(sdk):
    return sdk.users


@pytest.fixture
def category_type(sdk):
    return sdk.categories


@pytest.fixture
def article_payload() -> dict:
    return {
        "type": "articles",
        "id": "1",
        "attributes": {
            "title": "Hello World",
            "content": "Some content",
            "created_at": "2025-01-15T10:00:00",
        },
        "relationships": {
            "author": {
                "data": {"type": "users", "id": "42"},
                "links": {"related": f"{HOST}/articles/1/author"},
            },
            "categories": {
                "data": [
                    {"type": "categories", "id": "10"},
                    {"type": "categories", "id": "20"},
                ],
                "links": {"related": f"{HOST}/articles/1/categories"},
            },
        },
        "links": {"self": f"{HOST}/articles/1"},
    }


@pytest.fixture
def article_response(article_payload) -> dict:
    return {
        "jsonapi": {"version": "1.0"},
        "data": article_payload,
        "included": [],
    }


@pytest.fixture
def user_payload() -> dict:
    return {
        "type": "users",
        "id": "42",
        "attributes": {"username": "jdoe", "email": "jdoe@example.com"},
        "links": {"self": f"{HOST}/users/42"},
    }


@pytest.fixture
def article_list_response(article_payload) -> dict:
    a2 = dict(article_payload)
    a2["id"] = "2"
    a2["attributes"] = dict(a2["attributes"])
    a2["attributes"]["title"] = "Second Article"
    return {
        "jsonapi": {"version": "1.0"},
        "data": [article_payload, a2],
        "links": {
            "first": f"{HOST}/articles?page=1",
            "self": f"{HOST}/articles?page=1",
            "next": f"{HOST}/articles?page=2",
            "last": f"{HOST}/articles?page=5",
        },
        "meta": {"total": 10},
    }
