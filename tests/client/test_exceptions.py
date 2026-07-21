from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from djsonapi_client_py import (
    BadRequest,
    Collection,
    Conflict,
    DjsonApiClientError,
    Forbidden,
    InternalServerError,
    MethodNotAllowed,
    NotFound,
    TooManyRequests,
    Unauthorized,
    UnprocessableEntity,
)

HOST = "http://testserver"


def mock_get(sdk, status=200, payload=None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return patch.object(sdk._session, "get", return_value=resp)


def mock_post(sdk, status=201, payload=None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return patch.object(sdk._session, "post", return_value=resp)


def mock_patch(sdk, status=200, payload=None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return patch.object(sdk._session, "patch", return_value=resp)


def mock_delete(sdk, status=204, payload=None):
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status = status
    resp.json = AsyncMock(return_value=payload or {})
    return patch.object(sdk._session, "delete", return_value=resp)


class TestExceptionClasses:
    def test_base_exception(self):
        exc = DjsonApiClientError(400, "Bad Request", "Something went wrong")
        assert exc.status == 400
        assert exc.title == "Bad Request"
        assert exc.detail == "Something went wrong"
        assert "400" in str(exc)

    def test_bad_request(self):
        assert issubclass(BadRequest, DjsonApiClientError)

    def test_unauthorized(self):
        assert issubclass(Unauthorized, DjsonApiClientError)

    def test_forbidden(self):
        assert issubclass(Forbidden, DjsonApiClientError)

    def test_not_found(self):
        assert issubclass(NotFound, DjsonApiClientError)

    def test_method_not_allowed(self):
        assert issubclass(MethodNotAllowed, DjsonApiClientError)

    def test_conflict(self):
        assert issubclass(Conflict, DjsonApiClientError)

    def test_unprocessable_entity(self):
        assert issubclass(UnprocessableEntity, DjsonApiClientError)

    def test_too_many_requests(self):
        assert issubclass(TooManyRequests, DjsonApiClientError)

    def test_internal_server_error(self):
        assert issubclass(InternalServerError, DjsonApiClientError)


class TestRaiseForStatus:
    def test_no_error_below_400(self, sdk):
        sdk._raise_for_status(200, {})

    def test_bad_request_400(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(400, {"title": "Bad", "detail": "bad input"})
        assert isinstance(exc_info.value.exceptions[0], BadRequest)

    def test_unauthorized_401(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(401, {})
        assert isinstance(exc_info.value.exceptions[0], Unauthorized)

    def test_forbidden_403(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(403, {})
        assert isinstance(exc_info.value.exceptions[0], Forbidden)

    def test_not_found_404(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(404, {})
        assert isinstance(exc_info.value.exceptions[0], NotFound)

    def test_method_not_allowed_405(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(405, {})
        assert isinstance(exc_info.value.exceptions[0], MethodNotAllowed)

    def test_conflict_409(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(409, {})
        assert isinstance(exc_info.value.exceptions[0], Conflict)

    def test_unprocessable_422(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(422, {})
        assert isinstance(exc_info.value.exceptions[0], UnprocessableEntity)

    def test_too_many_429(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(429, {})
        assert isinstance(exc_info.value.exceptions[0], TooManyRequests)

    def test_internal_error_500(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(500, {})
        assert isinstance(exc_info.value.exceptions[0], InternalServerError)

    def test_unknown_status_dynamic_class(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(418, {"title": "Teapot"})
        exc = exc_info.value.exceptions[0]
        assert isinstance(exc, DjsonApiClientError)
        assert exc.status == 418
        assert exc.title == "Teapot"
        assert type(exc).__name__ == "Http418"

    def test_single_error_in_list(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(
                404,
                {
                    "errors": [
                        {"status": "404", "title": "Not Found", "detail": "Article not found"}
                    ]
                },
            )
        exc = exc_info.value.exceptions[0]
        assert isinstance(exc, DjsonApiClientError)
        assert exc.detail == "Article not found"

    def test_multiple_errors_raise_exception_group(self, sdk):
        with pytest.raises(ExceptionGroup) as exc_info:
            sdk._raise_for_status(
                400,
                {
                    "errors": [
                        {"status": "400", "title": "Bad Request", "detail": "Invalid title"},
                        {
                            "status": "422",
                            "title": "Unprocessable",
                            "detail": "Invalid content",
                        },
                    ]
                },
            )
        assert len(exc_info.value.exceptions) == 2
        assert isinstance(exc_info.value.exceptions[0], BadRequest)
        assert isinstance(exc_info.value.exceptions[1], UnprocessableEntity)


class TestHttpIntegration:
    async def _assert_in_group(self, coro, exc_type):
        with pytest.raises(ExceptionGroup) as exc_info:
            await coro
        exc = exc_info.value.exceptions[0]
        assert isinstance(exc, DjsonApiClientError)
        assert isinstance(exc, exc_type)
        return exc

    async def test_get_raises_not_found(self, article_type):
        async with article_type._sdk:
            with mock_get(
                article_type._sdk,
                status=404,
                payload={
                    "errors": [
                        {"status": "404", "title": "Not Found", "detail": "Article not found"}
                    ]
                },
            ):
                exc = await self._assert_in_group(
                    article_type.get("999"), NotFound
                )
                assert exc.detail == "Article not found"

    async def test_create_raises_bad_request(self, article_type):
        async with article_type._sdk:
            with mock_post(
                article_type._sdk,
                status=400,
                payload={
                    "errors": [
                        {
                            "status": "400",
                            "title": "Bad Request",
                            "detail": "title is required",
                        }
                    ]
                },
            ):
                exc = await self._assert_in_group(
                    article_type.create(title=""), BadRequest
                )
                assert exc.detail == "title is required"

    async def test_save_raises_conflict(self, article_type):
        article = article_type(id="1", title="Old")
        async with article_type._sdk:
            with mock_patch(
                article_type._sdk,
                status=409,
                payload={
                    "errors": [
                        {"status": "409", "title": "Conflict", "detail": "Version mismatch"}
                    ]
                },
            ):
                exc = await self._assert_in_group(
                    article.save(title="New"), Conflict
                )
                assert exc.detail == "Version mismatch"

    async def test_delete_raises_not_found(self, article_type):
        article = article_type(id="999")
        async with article_type._sdk:
            with mock_delete(
                article_type._sdk,
                status=404,
                payload={
                    "errors": [
                        {"status": "404", "title": "Not Found", "detail": "Article not found"}
                    ]
                },
            ):
                await self._assert_in_group(article.delete(), NotFound)

    async def test_collection_fetch_raises(self, article_type):
        sdk = article_type._sdk
        col = Collection(sdk, f"{HOST}/articles")
        async with sdk:
            with mock_get(
                sdk,
                status=500,
                payload={
                    "errors": [
                        {
                            "status": "500",
                            "title": "Internal Server Error",
                            "detail": "Something broke",
                        }
                    ]
                },
            ):
                exc = await self._assert_in_group(col, InternalServerError)
                assert exc.detail == "Something broke"
