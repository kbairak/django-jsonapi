from __future__ import annotations

__all__ = [
    "BadRequest",
    "Conflict",
    "DjsonApiClientError",
    "Forbidden",
    "InternalServerError",
    "MethodNotAllowed",
    "NotFound",
    "TooManyRequests",
    "Unauthorized",
    "UnprocessableEntity",
]

_MODULE = "djsonapi_client"


class DjsonApiClientError(Exception):
    def __init__(self, status: int, title: str = "", detail: str = ""):
        self.status = status
        self.title = title
        self.detail = detail
        super().__init__(f"[{status}] {title}: {detail}")


class BadRequest(DjsonApiClientError): ...


class Unauthorized(DjsonApiClientError): ...


class Forbidden(DjsonApiClientError): ...


class NotFound(DjsonApiClientError): ...


class MethodNotAllowed(DjsonApiClientError): ...


class Conflict(DjsonApiClientError): ...


class UnprocessableEntity(DjsonApiClientError): ...


class TooManyRequests(DjsonApiClientError): ...


class InternalServerError(DjsonApiClientError): ...


_STANDARD_EXC_NAMES: dict[int, type[DjsonApiClientError]] = {
    400: BadRequest,
    401: Unauthorized,
    403: Forbidden,
    404: NotFound,
    405: MethodNotAllowed,
    409: Conflict,
    422: UnprocessableEntity,
    429: TooManyRequests,
    500: InternalServerError,
}

_EXC_CLASS_CACHE: dict[int, type[DjsonApiClientError]] = {}


def _exc_class_for(status: int) -> type[DjsonApiClientError]:
    cls = _STANDARD_EXC_NAMES.get(status)
    if cls is not None:
        return cls
    if status not in _EXC_CLASS_CACHE:
        _EXC_CLASS_CACHE[status] = type(
            f"Http{status}", (DjsonApiClientError,), {"__module__": _MODULE}
        )
    return _EXC_CLASS_CACHE[status]
