import asyncio
import functools
import inspect
import json as json_module
import types
import uuid as uuid_type
from collections.abc import Callable
from typing import Any, Union, get_args, get_origin
from urllib.parse import urlencode

import jsonschema
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import NoReverseMatch, path, reverse

from .exceptions import (
    DjsonApiException,
    DjsonApiExceptionSingle,
    InternalServerError,
    _class_name_to_code,
    _class_name_to_title,
)
from .resource import Resource
from .response import Response

_PYTHON_TO_DJANGO_PATH = {
    uuid_type.UUID: "uuid",
    int: "int",
    str: "str",
}

_PYTHON_TO_OPENAPI = {
    uuid_type.UUID: "string",
    int: "integer",
    str: "string",
    float: "number",
    bool: "boolean",
}


_MUTABLE_DEFAULT = object()

_VALID_PREFIXES = ["filter__", "page", "sort", "include__", "fields__", "extra__"]


def _is_nullable(tp: type) -> bool:
    origin = get_origin(tp)
    if origin is types.UnionType or origin is Union:
        return type(None) in get_args(tp)
    return False


def _bracket_name(prefix: str, suffix: str) -> str:
    parts = suffix.split("__")
    return prefix + "[" + "][".join(parts) + "]"


def _query_param_name(name: str) -> str:
    if name.startswith("filter__"):
        return _bracket_name("filter", name[len("filter__") :])
    if name.startswith("page"):
        if "__" in name:
            _, suffix = name.split("__", 1)
            return f"page[{suffix}]"
        return "page"
    if name == "sort":
        return "sort"
    if name.startswith("include__"):
        return "include"
    if name.startswith("fields__"):
        return f"fields[{name[len('fields__') :]}]"
    if name.startswith("extra__"):
        return name[len("extra__") :]
    raise ValueError(f"Unknown query parameter: {name}")


def _validate_and_convert(raw: str, tp: type, query_name: str) -> Any:
    origin = get_origin(tp)
    if origin is list:
        args = get_args(tp)
        item_tp = args[0] if args else str
        if not raw.strip():
            return []
        return [
            _validate_and_convert(item.strip(), item_tp, query_name) for item in raw.split(",")
        ]
    if tp is int:
        return int(raw)
    if tp is float:
        return float(raw)
    if tp is bool:
        if raw.lower() in ("true", "1"):
            return True
        if raw.lower() in ("false", "0"):
            return False
        raise ValueError(f"Invalid boolean value for '{query_name}': '{raw}'")
    return raw


def _extract_fields(query_params: dict) -> dict | None:
    fields = {}
    for k, v in query_params.items():
        if k.startswith("fields__"):
            type_name = k.split("__", 1)[1]
            fields[type_name] = v
    return fields if fields else None


def _extract_query_params(
    handler: Callable, request: HttpRequest, exclude: frozenset = frozenset()
) -> dict:
    sig = inspect.signature(handler)
    result: dict = {}

    include_suffixes = []
    for name in sig.parameters:
        if name == "request" or name in exclude:
            continue
        if name.startswith("include__"):
            include_suffixes.append(name[len("include__") :])

    if include_suffixes:
        raw_include = request.GET.get("include", "")
        assert isinstance(raw_include, str)
        included_set = set(raw_include.split(",")) if raw_include.strip() else set()
        for suffix in include_suffixes:
            param = sig.parameters[f"include__{suffix}"]
            default = param.default if param.default != inspect.Parameter.empty else False
            result[f"include__{suffix}"] = suffix in included_set

    for name, param in sig.parameters.items():
        if name == "request" or name in exclude or name in result:
            continue
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
        if isinstance(annotation, type) and issubclass(annotation, Resource):
            continue

        default = param.default if param.default != inspect.Parameter.empty else _MUTABLE_DEFAULT
        query_name = _query_param_name(name)

        raw = request.GET.get(query_name)
        if raw is None:
            if default is _MUTABLE_DEFAULT:
                raise ValueError(f"Missing required query parameter: {query_name}")
            result[name] = default
        else:
            assert isinstance(raw, str)
            result[name] = _validate_and_convert(raw, annotation, query_name)

    return result


def _type_to_openapi_schema(tp: type) -> dict:
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is list:
        item_tp = args[0] if args else str
        return {"type": "array", "items": _type_to_openapi_schema(item_tp)}
    openapi_type = _PYTHON_TO_OPENAPI.get(tp, "string")
    result: dict = {"type": openapi_type}
    if tp is uuid_type.UUID:
        result["format"] = "uuid"
    return result


def _handler_query_params(handler: Callable) -> list[dict]:
    sig = inspect.signature(handler)
    params = []

    include_suffixes = []
    for name in sig.parameters:
        if name.startswith("include__"):
            include_suffixes.append(name[len("include__") :])
    if include_suffixes:
        description = f"Allowed values: {', '.join(sorted(include_suffixes))}"
        params.append(
            {
                "name": "include",
                "in": "query",
                "required": False,
                "schema": {"type": "string"},
                "description": description,
            }
        )

    for name, param in sig.parameters.items():
        if name == "request":
            continue
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
        if isinstance(annotation, type) and issubclass(annotation, Resource):
            continue
        if name.startswith("include__"):
            continue
        if not any(name.startswith(p) for p in _VALID_PREFIXES):
            continue

        has_default = param.default is not inspect.Parameter.empty
        query_name = _query_param_name(name)
        param_obj = {
            "name": query_name,
            "in": "query",
            "required": not has_default,
            "schema": _type_to_openapi_schema(annotation),
        }
        if has_default and param.default is not None:
            default = param.default
            if isinstance(default, (str, int, float, bool)):
                param_obj["schema"]["default"] = default
        params.append(param_obj)
    return params


def _add_query_params_to_op(handler: Callable, op: dict) -> None:
    query_params = _handler_query_params(inspect.unwrap(handler))
    if query_params:
        op.setdefault("parameters", []).extend(query_params)


def _build_relationship_schema(rel_id_type: type, is_plural: bool) -> dict:
    if _is_nullable(rel_id_type):
        non_null_args = [a for a in get_args(rel_id_type) if a is not type(None)]
        effective_id_type = non_null_args[0] if non_null_args else str
    else:
        effective_id_type = rel_id_type
    id_schema = _type_to_openapi_schema(effective_id_type)
    item_schema: dict = {
        "type": "object",
        "properties": {
            "id": id_schema,
            "type": {"type": "string"},
        },
        "required": ["id", "type"],
    }
    if is_plural:
        data_schema: dict = {
            "type": "array",
            "items": item_schema,
        }
    else:
        nullable = _is_nullable(rel_id_type)
        if nullable:
            data_schema = {"oneOf": [{"type": "null"}, item_schema]}
        else:
            data_schema = item_schema
    return {
        "type": "object",
        "properties": {"data": data_schema},
        "required": ["data"],
    }


def _unwrap_response(raw):
    if isinstance(raw, Response):
        return raw.data, list(raw.included) if raw.included else None, raw.links
    return raw, None, None


def _build_links(request, link_defs):
    if not link_defs:
        return {}
    base = dict(request.GET.items())
    result = {}
    for rel, params in link_defs.items():
        merged = {**base, **params}
        qs = urlencode(merged, doseq=True)
        result[rel] = f"{request.path}?{qs}" if qs else request.path
    return result


def _validate_handler_params(handler: Callable, exclude: frozenset = frozenset()) -> None:
    sig = inspect.signature(handler)
    for name, param in sig.parameters.items():
        if name == "request" or name in exclude:
            continue
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
        if isinstance(annotation, type) and issubclass(annotation, Resource):
            continue
        if not any(name.startswith(p) for p in _VALID_PREFIXES):
            raise ImproperlyConfigured(
                f"Invalid parameter '{name}' in handler '{handler.__name__}'. "
                f"Must start with one of: {', '.join(_VALID_PREFIXES)}"
            )


class DjsonApi:
    def __init__(self):
        self._registry = []

    def get_one(
        self, type_name: str, errors: list[type[DjsonApiExceptionSingle]] | None = None
    ) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            url_name = f"get_one__{type_name}"
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            pk_param = [p for p in params if p.name != "request"][0]
            pk_name = pk_param.name
            _validate_handler_params(handler, exclude=frozenset([pk_name]))
            pk_type = (
                pk_param.annotation if pk_param.annotation != inspect.Parameter.empty else str
            )
            return_type = sig.return_annotation
            resource_class = (
                return_type
                if (
                    return_type is not inspect.Parameter.empty
                    and isinstance(return_type, type)
                    and issubclass(return_type, Resource)
                )
                else None
            )
            is_async = asyncio.iscoroutinefunction(handler)

            if is_async:

                async def async_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(
                            handler, request, exclude=frozenset(kwargs.keys())
                        )
                    except ValueError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    try:
                        result = await handler(request, **query_params, **kwargs)
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )
                    raw, included, resp_links = _unwrap_response(result)
                    extra_links = _build_links(request, resp_links)
                    return _one_response(
                        raw,
                        url_name,
                        kwargs,
                        self._type_to_endpoint(),
                        rel_to_endpoint=self._rel_to_endpoint(),
                        rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint(),
                        fields=_extract_fields(query_params),
                        included=included,
                        extra_links=extra_links,
                    )

                wrapper = functools.update_wrapper(
                    async_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )
            else:

                def sync_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(
                            handler, request, exclude=frozenset(kwargs.keys())
                        )
                    except ValueError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    try:
                        result = handler(request, **query_params, **kwargs)
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )
                    raw, included, resp_links = _unwrap_response(result)
                    extra_links = _build_links(request, resp_links)
                    return _one_response(
                        raw,
                        url_name,
                        kwargs,
                        self._type_to_endpoint(),
                        rel_to_endpoint=self._rel_to_endpoint(),
                        rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint(),
                        fields=_extract_fields(query_params),
                        included=included,
                        extra_links=extra_links,
                    )

                wrapper = functools.update_wrapper(
                    sync_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )

            self._registry.append(
                {
                    "type_name": type_name,
                    "method": "get_one",
                    "handler": wrapper,
                    "pk_name": pk_name,
                    "pk_type": pk_type,
                    "resource_class": resource_class,
                    "errors": errors or [],
                }
            )
            return wrapper

        return decorator

    def get_many(
        self, type_name: str, errors: list[type[DjsonApiExceptionSingle]] | None = None
    ) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            _validate_handler_params(handler)
            url_name = f"get_many__{type_name}"
            sig = inspect.signature(handler)
            return_type = sig.return_annotation
            origin = get_origin(return_type)
            args = get_args(return_type)
            resource_class = None
            if origin is list and args:
                rc = args[0]
                if isinstance(rc, type) and issubclass(rc, Resource):
                    resource_class = rc
            is_async = asyncio.iscoroutinefunction(handler)

            if is_async:

                async def async_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(
                            handler, request, exclude=frozenset(kwargs.keys())
                        )
                    except ValueError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    try:
                        result = await handler(request, **query_params)
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )
                    raw, included, resp_links = _unwrap_response(result)
                    extra_links = _build_links(request, resp_links)
                    return _many_response(
                        raw,
                        url_name,
                        self._type_to_endpoint(),
                        rel_to_endpoint=self._rel_to_endpoint(),
                        rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint(),
                        fields=_extract_fields(query_params),
                        included=included,
                        extra_links=extra_links,
                    )

                wrapper = functools.update_wrapper(
                    async_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )
            else:

                def sync_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(
                            handler, request, exclude=frozenset(kwargs.keys())
                        )
                    except ValueError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    try:
                        result = handler(request, **query_params)
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )
                    raw, included, resp_links = _unwrap_response(result)
                    extra_links = _build_links(request, resp_links)
                    return _many_response(
                        raw,
                        url_name,
                        self._type_to_endpoint(),
                        rel_to_endpoint=self._rel_to_endpoint(),
                        rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint(),
                        fields=_extract_fields(query_params),
                        included=included,
                        extra_links=extra_links,
                    )

                wrapper = functools.update_wrapper(
                    sync_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )

            self._registry.append(
                {
                    "type_name": type_name,
                    "method": "get_many",
                    "handler": wrapper,
                    "resource_class": resource_class,
                    "errors": errors or [],
                }
            )
            return wrapper

        return decorator

    def create_one(
        self, type_name: str, errors: list[type[DjsonApiExceptionSingle]] | None = None
    ) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            _validate_handler_params(handler)
            url_name = f"create_one__{type_name}"
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            resource_class = None
            for p in params:
                if p.name != "request":
                    anno = p.annotation
                    if isinstance(anno, type) and issubclass(anno, Resource):
                        resource_class = anno
                        break
            is_async = asyncio.iscoroutinefunction(handler)

            if is_async:

                async def async_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(
                            handler, request, exclude=frozenset(kwargs.keys())
                        )
                    except ValueError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    try:
                        body = json_module.loads(request.body)
                        data = body.get("data", {})
                        assert resource_class is not None
                        jsonschema.validate(data, resource_class.jsonschema_create())
                        payload = resource_class._from_jsonapi_payload(body)
                        result = await handler(request, payload=payload, **query_params)
                        raw, included, resp_links = _unwrap_response(result)
                        extra_links = _build_links(request, resp_links)
                        return _create_response(
                            raw, type_name, self._type_to_endpoint(), rel_to_endpoint=self._rel_to_endpoint(), rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint(), included=included, extra_links=extra_links
                        )
                    except json_module.JSONDecodeError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    except jsonschema.ValidationError as exc:
                        return JsonResponse(
                            {"errors": [_validation_error_to_error_obj(exc)]},
                            status=400,
                            content_type="application/vnd.api+json",
                        )
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )

                wrapper = functools.update_wrapper(
                    async_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )
            else:

                def sync_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(
                            handler, request, exclude=frozenset(kwargs.keys())
                        )
                    except ValueError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    try:
                        body = json_module.loads(request.body)
                        data = body.get("data", {})
                        assert resource_class is not None
                        jsonschema.validate(data, resource_class.jsonschema_create())
                        payload = resource_class._from_jsonapi_payload(body)
                        result = handler(request, payload=payload, **query_params)
                        raw, included, resp_links = _unwrap_response(result)
                        extra_links = _build_links(request, resp_links)
                        return _create_response(
                            raw, type_name, self._type_to_endpoint(), rel_to_endpoint=self._rel_to_endpoint(), rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint(), included=included, extra_links=extra_links
                        )
                    except json_module.JSONDecodeError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    except jsonschema.ValidationError as exc:
                        return JsonResponse(
                            {"errors": [_validation_error_to_error_obj(exc)]},
                            status=400,
                            content_type="application/vnd.api+json",
                        )
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )

                wrapper = functools.update_wrapper(
                    sync_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )

            self._registry.append(
                {
                    "type_name": type_name,
                    "method": "create_one",
                    "handler": wrapper,
                    "resource_class": resource_class,
                    "errors": errors or [],
                }
            )
            return wrapper

        return decorator

    def edit_one(
        self, type_name: str, errors: list[type[DjsonApiExceptionSingle]] | None = None
    ) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            url_name = f"edit_one__{type_name}"
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            pk_param = [p for p in params if p.name != "request"][0]
            pk_name = pk_param.name
            pk_type = pk_param.annotation if pk_param.annotation != inspect.Parameter.empty else str
            resource_class = None
            for p in params:
                if p.name != "request" and p.annotation is not inspect.Parameter.empty:
                    if isinstance(p.annotation, type) and issubclass(p.annotation, Resource):
                        resource_class = p.annotation
                        break
            _validate_handler_params(handler, exclude=frozenset([pk_name]))
            is_async = asyncio.iscoroutinefunction(handler)

            if is_async:

                async def async_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(
                            handler, request, exclude=frozenset(kwargs.keys())
                        )
                    except ValueError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    try:
                        body = json_module.loads(request.body)
                        data = body.get("data", {})
                        assert resource_class is not None
                        jsonschema.validate(data, resource_class.jsonschema_edit())
                        payload = resource_class._from_jsonapi_payload(body, fields=resource_class._edit_fields)
                        result = await handler(request, payload=payload, **query_params, **kwargs)
                        raw, included, resp_links = _unwrap_response(result)
                        extra_links = _build_links(request, resp_links)
                        return _one_response(
                            raw,
                            url_name,
                            kwargs,
                            self._type_to_endpoint(),
                            rel_to_endpoint=self._rel_to_endpoint(),
                            rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint(),
                            fields=_extract_fields(query_params),
                            included=included,
                            extra_links=extra_links,
                        )
                    except json_module.JSONDecodeError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    except jsonschema.ValidationError as exc:
                        return JsonResponse(
                            {"errors": [_validation_error_to_error_obj(exc)]},
                            status=400,
                            content_type="application/vnd.api+json",
                        )
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )

                wrapper = functools.update_wrapper(
                    async_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )
            else:

                def sync_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(
                            handler, request, exclude=frozenset(kwargs.keys())
                        )
                    except ValueError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    try:
                        body = json_module.loads(request.body)
                        data = body.get("data", {})
                        assert resource_class is not None
                        jsonschema.validate(data, resource_class.jsonschema_edit())
                        payload = resource_class._from_jsonapi_payload(body, fields=resource_class._edit_fields)
                        result = handler(request, payload=payload, **query_params, **kwargs)
                        raw, included, resp_links = _unwrap_response(result)
                        extra_links = _build_links(request, resp_links)
                        return _one_response(
                            raw,
                            url_name,
                            kwargs,
                            self._type_to_endpoint(),
                            rel_to_endpoint=self._rel_to_endpoint(),
                            rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint(),
                            fields=_extract_fields(query_params),
                            included=included,
                            extra_links=extra_links,
                        )
                    except json_module.JSONDecodeError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    except jsonschema.ValidationError as exc:
                        return JsonResponse(
                            {"errors": [_validation_error_to_error_obj(exc)]},
                            status=400,
                            content_type="application/vnd.api+json",
                        )
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )

                wrapper = functools.update_wrapper(
                    sync_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )

            self._registry.append(
                {
                    "type_name": type_name,
                    "method": "edit_one",
                    "handler": wrapper,
                    "pk_name": pk_name,
                    "pk_type": pk_type,
                    "resource_class": resource_class,
                    "errors": errors or [],
                }
            )
            return wrapper

        return decorator

    def delete_one(
        self, type_name: str, errors: list[type[DjsonApiExceptionSingle]] | None = None
    ) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            url_name = f"delete_one__{type_name}"
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            pk_param = [p for p in params if p.name != "request"][0]
            pk_name = pk_param.name
            pk_type = pk_param.annotation if pk_param.annotation != inspect.Parameter.empty else str
            is_async = asyncio.iscoroutinefunction(handler)

            if is_async:

                async def async_wrapper(request, **kwargs) -> HttpResponse:
                    try:
                        await handler(request, **kwargs)
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )
                    return HttpResponse(status=204)

                wrapper = functools.update_wrapper(
                    async_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )
            else:

                def sync_wrapper(request, **kwargs) -> HttpResponse:
                    try:
                        handler(request, **kwargs)
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )
                    return HttpResponse(status=204)

                wrapper = functools.update_wrapper(
                    sync_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )

            self._registry.append(
                {
                    "type_name": type_name,
                    "method": "delete_one",
                    "handler": wrapper,
                    "pk_name": pk_name,
                    "pk_type": pk_type,
                    "errors": errors or [],
                }
            )
            return wrapper

        return decorator

    def _make_relationship_mgmt_wrapper(
        self, handler, type_name, rel_name, pk_param, rel_id_param, is_plural, method_name,
        errors=None,
    ):
        pk_name = pk_param.name
        pk_type = pk_param.annotation if pk_param.annotation != inspect.Parameter.empty else str
        rel_id_name = rel_id_param.name
        rel_id_type = rel_id_param.annotation if rel_id_param.annotation != inspect.Parameter.empty else str
        url_name = f"{method_name}__{type_name}__{rel_name}"
        schema = _build_relationship_schema(rel_id_type, is_plural)
        is_async = asyncio.iscoroutinefunction(handler)

        if is_async:

            async def async_wrapper(request, **kwargs) -> HttpResponse:
                try:
                    body = json_module.loads(request.body)
                except json_module.JSONDecodeError as exc:
                    return JsonResponse(
                        {
                            "errors": [
                                {"status": "400", "title": "Bad request", "detail": str(exc)}
                            ]
                        },
                        status=400,
                    )
                try:
                    jsonschema.validate(body, schema)
                except jsonschema.ValidationError as exc:
                    return JsonResponse(
                        {"errors": [_validation_error_to_error_obj(exc)]},
                        status=400,
                        content_type="application/vnd.api+json",
                    )
                try:
                    data = body.get("data")
                    if data is None:
                        rel_id_value = None
                    elif is_plural:
                        rel_id_value = [_convert_rel_id(item["id"], rel_id_type) for item in data]
                    else:
                        rel_id_value = _convert_rel_id(data["id"], rel_id_type)
                    await handler(request, **kwargs, **{rel_id_name: rel_id_value})
                except DjsonApiException as exc:
                    return JsonResponse(
                        {"errors": exc.render()},
                        status=exc.status,
                        content_type="application/vnd.api+json",
                    )
                except Exception as exc:
                    ise = InternalServerError(str(exc))
                    return JsonResponse(
                        {"errors": ise.render()},
                        status=ise.status,
                        content_type="application/vnd.api+json",
                    )
                return HttpResponse(status=204)

            wrapper = functools.update_wrapper(
                async_wrapper,
                handler,
                assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                updated=(),
            )
        else:

            def sync_wrapper(request, **kwargs) -> HttpResponse:
                try:
                    body = json_module.loads(request.body)
                except json_module.JSONDecodeError as exc:
                    return JsonResponse(
                        {
                            "errors": [
                                {"status": "400", "title": "Bad request", "detail": str(exc)}
                            ]
                        },
                        status=400,
                    )
                try:
                    jsonschema.validate(body, schema)
                except jsonschema.ValidationError as exc:
                    return JsonResponse(
                        {"errors": [_validation_error_to_error_obj(exc)]},
                        status=400,
                        content_type="application/vnd.api+json",
                    )
                try:
                    data = body.get("data")
                    if data is None:
                        rel_id_value = None
                    elif is_plural:
                        rel_id_value = [_convert_rel_id(item["id"], rel_id_type) for item in data]
                    else:
                        rel_id_value = _convert_rel_id(data["id"], rel_id_type)
                    handler(request, **kwargs, **{rel_id_name: rel_id_value})
                except DjsonApiException as exc:
                    return JsonResponse(
                        {"errors": exc.render()},
                        status=exc.status,
                        content_type="application/vnd.api+json",
                    )
                except Exception as exc:
                    ise = InternalServerError(str(exc))
                    return JsonResponse(
                        {"errors": ise.render()},
                        status=ise.status,
                        content_type="application/vnd.api+json",
                    )
                return HttpResponse(status=204)

            wrapper = functools.update_wrapper(
                sync_wrapper,
                handler,
                assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                updated=(),
            )

        self._registry.append(
            {
                "type_name": type_name,
                "method": method_name,
                "rel_name": rel_name,
                "handler": wrapper,
                "pk_name": pk_name,
                "pk_type": pk_type,
                "errors": errors or [],
            }
        )
        return wrapper

    def edit_relationship(
        self, type_name: str, rel_name: str, errors: list[type[DjsonApiExceptionSingle]] | None = None
    ) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            non_request = [p for p in params if p.name != "request"]
            pk_param = non_request[0]
            rel_id_param = non_request[1]
            return self._make_relationship_mgmt_wrapper(
                handler, type_name, rel_name, pk_param, rel_id_param,
                is_plural=False, method_name="edit_relationship",
                errors=errors,
            )
        return decorator

    def reset_relationship(
        self, type_name: str, rel_name: str, errors: list[type[DjsonApiExceptionSingle]] | None = None
    ) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            non_request = [p for p in params if p.name != "request"]
            pk_param = non_request[0]
            rel_id_param = non_request[1]
            return self._make_relationship_mgmt_wrapper(
                handler, type_name, rel_name, pk_param, rel_id_param,
                is_plural=True, method_name="reset_relationship",
                errors=errors,
            )
        return decorator

    def add_to_relationship(
        self, type_name: str, rel_name: str, errors: list[type[DjsonApiExceptionSingle]] | None = None
    ) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            non_request = [p for p in params if p.name != "request"]
            pk_param = non_request[0]
            rel_id_param = non_request[1]
            return self._make_relationship_mgmt_wrapper(
                handler, type_name, rel_name, pk_param, rel_id_param,
                is_plural=True, method_name="add_to_relationship",
                errors=errors,
            )
        return decorator

    def remove_from_relationship(
        self, type_name: str, rel_name: str, errors: list[type[DjsonApiExceptionSingle]] | None = None
    ) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            non_request = [p for p in params if p.name != "request"]
            pk_param = non_request[0]
            rel_id_param = non_request[1]
            return self._make_relationship_mgmt_wrapper(
                handler, type_name, rel_name, pk_param, rel_id_param,
                is_plural=True, method_name="remove_from_relationship",
                errors=errors,
            )
        return decorator

    def get_relationship(
        self, type_name: str, rel_name: str, errors: list[type[DjsonApiExceptionSingle]] | None = None
    ) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            url_name = f"get_relationship__{type_name}__{rel_name}"
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            pk_param = [p for p in params if p.name != "request"][0]
            pk_name = pk_param.name
            pk_type = pk_param.annotation if pk_param.annotation != inspect.Parameter.empty else str
            _validate_handler_params(handler, exclude=frozenset([pk_name]))
            return_type = sig.return_annotation
            origin = get_origin(return_type)
            resource_class = None
            is_plural = False
            if origin is list:
                is_plural = True
                args = get_args(return_type)
                if args:
                    rc = args[0]
                    if isinstance(rc, type) and issubclass(rc, Resource):
                        resource_class = rc
            elif (
                return_type is not inspect.Parameter.empty
                and isinstance(return_type, type)
                and issubclass(return_type, Resource)
            ):
                resource_class = return_type
            is_async = asyncio.iscoroutinefunction(handler)

            if is_async:

                async def async_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(
                            handler, request, exclude=frozenset(kwargs.keys())
                        )
                    except ValueError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    try:
                        result = await handler(request, **query_params, **kwargs)
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )
                    raw, included, resp_links = _unwrap_response(result)
                    extra_links = _build_links(request, resp_links)
                    rel = self._rel_to_endpoint()
                    rel_mgmt = self._rel_mgmt_to_endpoint()
                    if is_plural:
                        return _many_response(
                            raw,
                            url_name,
                            self._type_to_endpoint(),
                            rel_to_endpoint=rel,
                            rel_mgmt_to_endpoint=rel_mgmt,
                            fields=_extract_fields(query_params),
                            included=included,
                            url_kwargs=kwargs,
                            extra_links=extra_links,
                        )
                    return _one_response(
                        raw,
                        url_name,
                        kwargs,
                        self._type_to_endpoint(),
                        rel_to_endpoint=rel,
                        rel_mgmt_to_endpoint=rel_mgmt,
                        fields=_extract_fields(query_params),
                        included=included,
                        extra_links=extra_links,
                    )

                wrapper = functools.update_wrapper(
                    async_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )
            else:

                def sync_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(
                            handler, request, exclude=frozenset(kwargs.keys())
                        )
                    except ValueError as exc:
                        return JsonResponse(
                            {
                                "errors": [
                                    {"status": "400", "title": "Bad request", "detail": str(exc)}
                                ]
                            },
                            status=400,
                        )
                    try:
                        result = handler(request, **query_params, **kwargs)
                    except DjsonApiException as exc:
                        return JsonResponse(
                            {"errors": exc.render()},
                            status=exc.status,
                            content_type="application/vnd.api+json",
                        )
                    except Exception as exc:
                        ise = InternalServerError(str(exc))
                        return JsonResponse(
                            {"errors": ise.render()},
                            status=ise.status,
                            content_type="application/vnd.api+json",
                        )
                    raw, included, resp_links = _unwrap_response(result)
                    extra_links = _build_links(request, resp_links)
                    rel = self._rel_to_endpoint()
                    rel_mgmt = self._rel_mgmt_to_endpoint()
                    if is_plural:
                        return _many_response(
                            raw,
                            url_name,
                            self._type_to_endpoint(),
                            rel_to_endpoint=rel,
                            rel_mgmt_to_endpoint=rel_mgmt,
                            fields=_extract_fields(query_params),
                            included=included,
                            url_kwargs=kwargs,
                            extra_links=extra_links,
                        )
                    return _one_response(
                        raw,
                        url_name,
                        kwargs,
                        self._type_to_endpoint(),
                        rel_to_endpoint=rel,
                        rel_mgmt_to_endpoint=rel_mgmt,
                        fields=_extract_fields(query_params),
                        included=included,
                        extra_links=extra_links,
                    )

                wrapper = functools.update_wrapper(
                    sync_wrapper,
                    handler,
                    assigned=("__module__", "__name__", "__qualname__", "__doc__"),
                    updated=(),
                )

            self._registry.append(
                {
                    "type_name": type_name,
                    "method": "get_relationship",
                    "rel_name": rel_name,
                    "handler": wrapper,
                    "pk_name": pk_name,
                    "pk_type": pk_type,
                    "resource_class": resource_class,
                    "is_plural": is_plural,
                    "errors": errors or [],
                }
            )
            return wrapper

        return decorator

    @property
    def urls(self):
        groups: dict = {}
        for entry in self._registry:
            type_name = entry["type_name"]
            if entry["method"] == "get_one":
                pk_name = entry["pk_name"]
                django_type = _PYTHON_TO_DJANGO_PATH.get(entry["pk_type"], "str")
                path_str = f"{type_name}/<{django_type}:{pk_name}>"
                groups.setdefault(path_str, {})["GET"] = (
                    entry["handler"],
                    f"get_one__{type_name}",
                )
            elif entry["method"] == "get_many":
                path_str = f"{type_name}/"
                groups.setdefault(path_str, {})["GET"] = (
                    entry["handler"],
                    f"get_many__{type_name}",
                )
            elif entry["method"] == "create_one":
                path_str = f"{type_name}/"
                groups.setdefault(path_str, {})["POST"] = (
                    entry["handler"],
                    f"create_one__{type_name}",
                )
            elif entry["method"] == "edit_one":
                pk_name = entry["pk_name"]
                django_type = _PYTHON_TO_DJANGO_PATH.get(entry["pk_type"], "str")
                path_str = f"{type_name}/<{django_type}:{pk_name}>"
                groups.setdefault(path_str, {})["PATCH"] = (
                    entry["handler"],
                    f"edit_one__{type_name}",
                )
            elif entry["method"] == "delete_one":
                pk_name = entry["pk_name"]
                django_type = _PYTHON_TO_DJANGO_PATH.get(entry["pk_type"], "str")
                path_str = f"{type_name}/<{django_type}:{pk_name}>"
                groups.setdefault(path_str, {})["DELETE"] = (
                    entry["handler"],
                    f"delete_one__{type_name}",
                )
            elif entry["method"] == "get_relationship":
                pk_name = entry["pk_name"]
                django_type = _PYTHON_TO_DJANGO_PATH.get(entry["pk_type"], "str")
                path_str = f"{type_name}/<{django_type}:{pk_name}>/{entry['rel_name']}"
                groups.setdefault(path_str, {})["GET"] = (
                    entry["handler"],
                    f"get_relationship__{type_name}__{entry['rel_name']}",
                )
            elif entry["method"] in (
                "edit_relationship", "reset_relationship", "add_to_relationship", "remove_from_relationship"
            ):
                pk_name = entry["pk_name"]
                django_type = _PYTHON_TO_DJANGO_PATH.get(entry["pk_type"], "str")
                path_str = f"{type_name}/<{django_type}:{pk_name}>/relationships/{entry['rel_name']}"
                method_map = {
                    "edit_relationship": "PATCH",
                    "reset_relationship": "PATCH",
                    "add_to_relationship": "POST",
                    "remove_from_relationship": "DELETE",
                }
                http_method = method_map[entry["method"]]
                groups.setdefault(path_str, {})[http_method] = (
                    entry["handler"],
                    f"{entry['method']}__{type_name}__{entry['rel_name']}",
                )
        result = []
        for path_str, methods in groups.items():
            if len(methods) == 1:
                (handler, name) = next(iter(methods.values()))
                result.append(path(path_str, handler, name=name))
            else:
                dispatch = _CombinedView({m: h for m, (h, _) in methods.items()})
                for _, name in methods.values():
                    result.append(path(path_str, dispatch, name=name))
        result.append(path("openapi.json", self._openapi_view, name="openapi"))
        result.append(path("docs/", self._docs_view, name="docs"))
        return result

    def _type_to_endpoint(self) -> dict[str, dict]:
        result = {}
        for entry in self._registry:
            if entry["method"] != "get_one":
                continue
            result[entry["type_name"]] = {
                "url_name": f"get_one__{entry['type_name']}",
                "pk_name": entry["pk_name"],
            }
        return result

    def _rel_to_endpoint(self) -> dict[tuple[str, str], dict]:
        result = {}
        for entry in self._registry:
            if entry["method"] != "get_relationship":
                continue
            result[(entry["type_name"], entry["rel_name"])] = {
                "url_name": f"get_relationship__{entry['type_name']}__{entry['rel_name']}",
                "pk_name": entry["pk_name"],
            }
        return result

    def _rel_mgmt_to_endpoint(self) -> dict[tuple[str, str], dict]:
        result = {}
        for entry in self._registry:
            if entry["method"] not in (
                "edit_relationship", "reset_relationship", "add_to_relationship", "remove_from_relationship"
            ):
                continue
            key = (entry["type_name"], entry["rel_name"])
            if key not in result:
                result[key] = {
                    "url_name": f"{entry['method']}__{entry['type_name']}__{entry['rel_name']}",
                    "pk_name": entry["pk_name"],
                }
        return result

    def _openapi_view(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse(self._build_openapi_spec())

    def _docs_view(self, request: HttpRequest) -> HttpResponse:
        try:
            openapi_url = reverse("openapi")
        except (NoReverseMatch, ImproperlyConfigured):
            openapi_url = "/openapi.json"
        html = f"""<!DOCTYPE html>
<html>
<head>
  <title>API Docs</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
  <redoc spec-url='{openapi_url}'></redoc>
  <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
</body>
</html>"""
        return HttpResponse(html.encode(), content_type="text/html")

    def _build_openapi_spec(self) -> dict:
        spec: dict = {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {},
            "components": {"schemas": {}},
        }
        for entry in self._registry:
            type_name = entry["type_name"]
            resource_class = entry.get("resource_class")
            type_to_endpoint = self._type_to_endpoint()
            raw_name = entry["handler"].__name__.replace("_", " ")
            summary = raw_name[0].upper() + raw_name[1:] if raw_name else raw_name

            if entry["method"] == "get_one":
                pk_name = entry["pk_name"]
                pk_type = entry["pk_type"]
                openapi_type = _PYTHON_TO_OPENAPI.get(pk_type, "string")
                path_str = f"/{type_name}/{{{pk_name}}}"
                path_item = spec["paths"].setdefault(path_str, {})
                param_schema = {"type": openapi_type}
                if pk_type is uuid_type.UUID:
                    param_schema["format"] = "uuid"
                response_schema: dict = {}
                if resource_class:
                    response_schema = _response_schema(
                        type_name, resource_class, type_to_endpoint, spec, rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint()
                    )
                path_item["get"] = {
                    "tags": [type_name],
                    "summary": summary,
                    "parameters": [
                        {
                            "name": pk_name,
                            "in": "path",
                            "required": True,
                            "schema": param_schema,
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/vnd.api+json": {
                                    "schema": response_schema or {"type": "object"}
                                }
                            },
                        }
                    },
                }
                _add_query_params_to_op(entry["handler"], path_item["get"])

            elif entry["method"] == "get_many":
                path_str = f"/{type_name}/"
                path_item = spec["paths"].setdefault(path_str, {})
                response_schema = _response_schema(
                    type_name, resource_class, type_to_endpoint, spec
                )
                path_item["get"] = {
                    "tags": [type_name],
                    "summary": summary,
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/vnd.api+json": {
                                    "schema": response_schema or {"type": "object"}
                                }
                            },
                        }
                    },
                }
                _add_query_params_to_op(entry["handler"], path_item["get"])

            elif entry["method"] == "create_one":
                path_str = f"/{type_name}/"
                path_item = spec["paths"].setdefault(path_str, {})
                response_schema: dict = {}
                if resource_class:
                    response_schema = _response_schema(
                        type_name, resource_class, type_to_endpoint, spec, rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint()
                    )
                path_item["post"] = {
                    "tags": [type_name],
                    "summary": summary,
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/vnd.api+json": {
                                "schema": resource_class.jsonschema_create()
                                if resource_class
                                else {"type": "object"},
                            }
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "Created",
                            "content": {
                                "application/vnd.api+json": {
                                    "schema": response_schema or {"type": "object"}
                                }
                            },
                        },
                    },
                }
                _add_query_params_to_op(entry["handler"], path_item["post"])

            elif entry["method"] == "edit_one":
                pk_name = entry["pk_name"]
                pk_type = entry["pk_type"]
                openapi_type = _PYTHON_TO_OPENAPI.get(pk_type, "string")
                path_str = f"/{type_name}/{{{pk_name}}}"
                path_item = spec["paths"].setdefault(path_str, {})
                param_schema = {"type": openapi_type}
                if pk_type is uuid_type.UUID:
                    param_schema["format"] = "uuid"
                response_schema: dict = {}
                if resource_class:
                    response_schema = _response_schema(
                        type_name, resource_class, type_to_endpoint, spec, rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint()
                    )
                path_item["patch"] = {
                    "tags": [type_name],
                    "summary": summary,
                    "parameters": [
                        {
                            "name": pk_name,
                            "in": "path",
                            "required": True,
                            "schema": param_schema,
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/vnd.api+json": {
                                "schema": resource_class.jsonschema_edit()
                                if resource_class
                                else {"type": "object"},
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/vnd.api+json": {
                                    "schema": response_schema or {"type": "object"}
                                }
                            },
                        },
                    },
                }
                _add_query_params_to_op(entry["handler"], path_item["patch"])

            elif entry["method"] == "delete_one":
                pk_name = entry["pk_name"]
                pk_type = entry["pk_type"]
                openapi_type = _PYTHON_TO_OPENAPI.get(pk_type, "string")
                path_str = f"/{type_name}/{{{pk_name}}}"
                path_item = spec["paths"].setdefault(path_str, {})
                param_schema = {"type": openapi_type}
                if pk_type is uuid_type.UUID:
                    param_schema["format"] = "uuid"
                path_item["delete"] = {
                    "tags": [type_name],
                    "summary": summary,
                    "parameters": [
                        {
                            "name": pk_name,
                            "in": "path",
                            "required": True,
                            "schema": param_schema,
                        }
                    ],
                    "responses": {
                        "204": {"description": "No Content"},
                    },
                }
            elif entry["method"] == "get_relationship":
                pk_name = entry["pk_name"]
                pk_type = entry["pk_type"]
                rel_name = entry["rel_name"]
                openapi_type = _PYTHON_TO_OPENAPI.get(pk_type, "string")
                path_str = f"/{type_name}/{{{pk_name}}}/{rel_name}"
                path_item = spec["paths"].setdefault(path_str, {})
                param_schema = {"type": openapi_type}
                if pk_type is uuid_type.UUID:
                    param_schema["format"] = "uuid"
                response_schema: dict = {}
                if resource_class:
                    rel_type_name = resource_class._type
                    if entry["is_plural"]:
                        _ensure_schema(rel_type_name, resource_class, type_to_endpoint, spec, rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint())
                        response_schema = {
                            "type": "object",
                            "properties": {
                                "data": {
                                    "type": "array",
                                    "items": {"$ref": f"#/components/schemas/{rel_type_name}_resource"},
                                },
                                "jsonapi": {
                                    "type": "object",
                                    "properties": {"version": {"const": "1.0"}},
                                },
                            },
                        }
                    else:
                        response_schema = _response_schema(
                            rel_type_name, resource_class, type_to_endpoint, spec, rel_mgmt_to_endpoint=self._rel_mgmt_to_endpoint()
                        )
                path_item["get"] = {
                    "tags": [type_name],
                    "summary": summary,
                    "parameters": [
                        {
                            "name": pk_name,
                            "in": "path",
                            "required": True,
                            "schema": param_schema,
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/vnd.api+json": {
                                    "schema": response_schema or {"type": "object"}
                                }
                            },
                        }
                    },
                }
                _add_query_params_to_op(entry["handler"], path_item["get"])
            elif entry["method"] in (
                "edit_relationship", "reset_relationship", "add_to_relationship", "remove_from_relationship"
            ):
                pk_name = entry["pk_name"]
                pk_type = entry["pk_type"]
                rel_name = entry["rel_name"]
                openapi_type = _PYTHON_TO_OPENAPI.get(pk_type, "string")
                path_str = f"/{type_name}/{{{pk_name}}}/relationships/{rel_name}"
                path_item = spec["paths"].setdefault(path_str, {})
                param_schema = {"type": openapi_type}
                if pk_type is uuid_type.UUID:
                    param_schema["format"] = "uuid"
                raw_handler = inspect.unwrap(entry["handler"])
                sig = inspect.signature(raw_handler)
                non_request = [p for p in list(sig.parameters.values()) if p.name != "request"]
                rel_id_param = non_request[1]
                rel_id_type = rel_id_param.annotation if rel_id_param.annotation != inspect.Parameter.empty else str
                is_plural = entry["method"] in ("reset_relationship", "add_to_relationship", "remove_from_relationship")
                request_schema = _build_relationship_schema(rel_id_type, is_plural)
                http_method_map = {
                    "edit_relationship": "patch",
                    "reset_relationship": "patch",
                    "add_to_relationship": "post",
                    "remove_from_relationship": "delete",
                }
                http_method = http_method_map[entry["method"]]
                path_item[http_method] = {
                    "tags": [type_name],
                    "summary": summary,
                    "parameters": [
                        {
                            "name": pk_name,
                            "in": "path",
                            "required": True,
                            "schema": param_schema,
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/vnd.api+json": {
                                "schema": request_schema,
                            }
                        },
                    },
                    "responses": {
                        "204": {"description": "No Content"},
                    },
                }
            if entry.get("errors"):
                method = entry["method"]
                _ENTRY_METHOD_TO_HTTP = {
                    "get_one": "get", "get_many": "get", "create_one": "post",
                    "edit_one": "patch", "delete_one": "delete",
                    "get_relationship": "get", "edit_relationship": "patch",
                    "reset_relationship": "patch", "add_to_relationship": "post",
                    "remove_from_relationship": "delete",
                }
                http_method = _ENTRY_METHOD_TO_HTTP[method]
                if method in ("get_one", "edit_one", "delete_one"):
                    pk_name = entry["pk_name"]
                    path_str = f"/{type_name}/{{{pk_name}}}"
                elif method in ("get_many", "create_one"):
                    path_str = f"/{type_name}/"
                elif method == "get_relationship":
                    path_str = f"/{type_name}/{{{entry['pk_name']}}}/{entry['rel_name']}"
                elif method in ("edit_relationship", "reset_relationship", "add_to_relationship", "remove_from_relationship"):
                    path_str = f"/{type_name}/{{{entry['pk_name']}}}/relationships/{entry['rel_name']}"
                else:
                    path_str = None
                if path_str:
                    op = spec["paths"][path_str].get(http_method)
                    if op:
                        for ex_class in entry["errors"]:
                            schema_name = _build_error_schema(ex_class, spec)
                            status_code = str(ex_class.STATUS)
                            ex_title = ex_class.TITLE if ex_class.TITLE is not None else _class_name_to_title(ex_class.__name__)
                            op["responses"][status_code] = {
                                "description": ex_title,
                                "content": {
                                    "application/vnd.api+json": {
                                        "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                                    }
                                },
                            }
        schema_names = list(spec["components"]["schemas"].keys())
        if schema_names:
            endpoint_tags = sorted(set(entry["type_name"] for entry in self._registry))
            schema_tags = []
            for schema_name in schema_names:
                type_name = schema_name.removesuffix("_resource")
                tag_name = f"{type_name}_schema"
                schema_tags.append(tag_name)
                spec.setdefault("tags", []).append(
                    {
                        "name": tag_name,
                        "x-displayName": type_name,
                        "description": f'<SchemaDefinition schemaRef="#/components/schemas/{schema_name}" />',
                    }
                )
            spec["x-tagGroups"] = [
                {"name": "Endpoints", "tags": endpoint_tags},
                {"name": "Schemas", "tags": schema_tags},
            ]
        return spec


def _add_relationship_links(resource, type_to_endpoint, rel_to_endpoint=None, rel_mgmt_to_endpoint=None):
    parent_type = resource.get("type")
    for rel_field, rel_data in resource.get("relationships", {}).items():
        if rel_mgmt_to_endpoint:
            mgmt = rel_mgmt_to_endpoint.get((parent_type, rel_field))
            if mgmt:
                try:
                    self_url = reverse(
                        mgmt["url_name"],
                        kwargs={mgmt["pk_name"]: resource["id"]},
                    )
                    rel_data.setdefault("links", {})["self"] = self_url
                except (NoReverseMatch, ImproperlyConfigured):
                    pass
        data = rel_data.get("data")
        if isinstance(data, dict):
            if rel_to_endpoint:
                rel_endpoint = rel_to_endpoint.get((parent_type, rel_field))
                if rel_endpoint:
                    try:
                        related_url = reverse(
                            rel_endpoint["url_name"],
                            kwargs={rel_endpoint["pk_name"]: resource["id"]},
                        )
                        rel_data.setdefault("links", {})["related"] = related_url
                        continue
                    except (NoReverseMatch, ImproperlyConfigured):
                        pass
            rel_type = data.get("type")
            endpoint = type_to_endpoint.get(rel_type)
            if endpoint:
                try:
                    related_url = reverse(
                        endpoint["url_name"],
                        kwargs={endpoint["pk_name"]: data["id"]},
                    )
                    rel_data.setdefault("links", {})["related"] = related_url
                except (NoReverseMatch, ImproperlyConfigured):
                    pass


def _apply_fields(resource, fields_for_type):
    if not fields_for_type:
        return
    if "attributes" in resource:
        resource["attributes"] = {
            k: v for k, v in resource["attributes"].items() if k in fields_for_type
        }
    if "relationships" in resource:
        resource["relationships"] = {
            k: v for k, v in resource["relationships"].items() if k in fields_for_type
        }


def _serialize_resource(result, type_to_endpoint, fields, rel_to_endpoint=None, rel_mgmt_to_endpoint=None):
    resource = result.serialize()
    _add_relationship_links(resource, type_to_endpoint, rel_to_endpoint=rel_to_endpoint, rel_mgmt_to_endpoint=rel_mgmt_to_endpoint)
    if fields:
        _apply_fields(resource, fields.get(result._type))
    return resource


def _one_response(result, url_name, kwargs, type_to_endpoint, fields=None, included=None, rel_to_endpoint=None, rel_mgmt_to_endpoint=None, extra_links=None):
    resource = _serialize_resource(result, type_to_endpoint, fields, rel_to_endpoint=rel_to_endpoint, rel_mgmt_to_endpoint=rel_mgmt_to_endpoint)
    try:
        self_url = reverse(url_name, kwargs=kwargs)
        resource.setdefault("links", {})["self"] = self_url
        links = {"self": self_url}
    except (NoReverseMatch, ImproperlyConfigured):
        links = {}
    if extra_links:
        links = {**extra_links, **links}

    body: dict = {"data": resource, "links": links, "jsonapi": {"version": "1.0"}}
    if included:
        body["included"] = [_serialize_resource(r, type_to_endpoint, fields, rel_to_endpoint=rel_to_endpoint, rel_mgmt_to_endpoint=rel_mgmt_to_endpoint) for r in included]
    return JsonResponse(body, content_type="application/vnd.api+json")


def _many_response(result_list, url_name, type_to_endpoint, fields=None, included=None, rel_to_endpoint=None, rel_mgmt_to_endpoint=None, url_kwargs=None, extra_links=None):
    resources = [_serialize_resource(r, type_to_endpoint, fields, rel_to_endpoint=rel_to_endpoint, rel_mgmt_to_endpoint=rel_mgmt_to_endpoint) for r in result_list]
    try:
        if url_kwargs:
            self_url = reverse(url_name, kwargs=url_kwargs)
        else:
            self_url = reverse(url_name)
        links = {"self": self_url}
    except (NoReverseMatch, ImproperlyConfigured):
        links = {}
    if extra_links:
        links = {**extra_links, **links}

    body: dict = {"data": resources, "links": links, "jsonapi": {"version": "1.0"}}
    if included:
        body["included"] = [_serialize_resource(r, type_to_endpoint, fields, rel_to_endpoint=rel_to_endpoint, rel_mgmt_to_endpoint=rel_mgmt_to_endpoint) for r in included]
    return JsonResponse(body, content_type="application/vnd.api+json")


def _add_links_to_schema(schema, resource_class, type_to_endpoint, rel_mgmt_to_endpoint=None):
    rel_props = schema.get("properties", {}).get("relationships", {}).get("properties", {})
    for rel_field, rel_type_name in resource_class._singular_relationships:
        endpoint = type_to_endpoint.get(rel_type_name)
        if endpoint and rel_field in rel_props:
            rel_props[rel_field]["properties"] = rel_props[rel_field].get("properties", {})
            links_props = {
                "related": {"type": "string", "format": "uri"},
            }
            if rel_mgmt_to_endpoint:
                links_props["self"] = {"type": "string", "format": "uri"}
            rel_props[rel_field]["properties"]["links"] = {
                "type": "object",
                "properties": links_props,
            }


def _ensure_schema(type_name, resource_class, type_to_endpoint, spec, rel_mgmt_to_endpoint=None):
    schema_name = f"{type_name}_resource"
    if schema_name not in spec["components"]["schemas"]:
        schema_obj = resource_class.jsonschema_read()
        _add_links_to_schema(schema_obj, resource_class, type_to_endpoint, rel_mgmt_to_endpoint=rel_mgmt_to_endpoint)
        schema_obj["title"] = type_name
        spec["components"]["schemas"][schema_name] = schema_obj


def _response_schema(type_name, resource_class, type_to_endpoint, spec, rel_mgmt_to_endpoint=None):
    _ensure_schema(type_name, resource_class, type_to_endpoint, spec, rel_mgmt_to_endpoint=rel_mgmt_to_endpoint)
    return {
        "type": "object",
        "properties": {
            "data": {"$ref": f"#/components/schemas/{type_name}_resource"},
            "jsonapi": {
                "type": "object",
                "properties": {"version": {"const": "1.0"}},
            },
        },
    }


_ERROR_STATUS_MAP: dict[int, list[type[DjsonApiExceptionSingle]]] = {}
for _cls in DjsonApiExceptionSingle.__subclasses__():
    _ERROR_STATUS_MAP.setdefault(int(_cls.STATUS), []).append(_cls)


def _build_error_schema(ex_class: type[DjsonApiExceptionSingle], spec: dict) -> str:
    schema_name = f"{ex_class.__name__}_error"
    if schema_name not in spec["components"]["schemas"]:
        code = ex_class.CODE if ex_class.CODE is not None else _class_name_to_code(ex_class.__name__)
        title = ex_class.TITLE if ex_class.TITLE is not None else _class_name_to_title(ex_class.__name__)
        error_props: dict = {
            "status": {"type": "string", "const": str(ex_class.STATUS)},
            "code": {"type": "string", "const": code},
            "title": {"type": "string", "const": title},
            "detail": {"type": "string"},
        }
        if ex_class.STATUS == 400:
            error_props["source"] = {
                "type": "object",
                "properties": {"pointer": {"type": "string"}},
            }
        spec["components"]["schemas"][schema_name] = {
            "type": "object",
            "properties": {
                "errors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": error_props,
                    },
                }
            },
        }
    return schema_name


class _CombinedView:
    def __init__(self, handlers):
        self._handlers = handlers

    def __call__(self, request, **kwargs):
        handler = self._handlers.get(request.method)
        if handler is None:
            return JsonResponse(
                {"errors": [{"status": "405", "title": "Method not allowed"}]},
                status=405,
            )
        return handler(request, **kwargs)


def _create_response(result, type_name, type_to_endpoint, fields=None, included=None, rel_to_endpoint=None, rel_mgmt_to_endpoint=None, extra_links=None):
    if result is None:
        body = {"jsonapi": {"version": "1.0"}}
        if extra_links:
            body["links"] = extra_links
        return JsonResponse(body, status=202)

    resource = _serialize_resource(result, type_to_endpoint, fields, rel_to_endpoint=rel_to_endpoint, rel_mgmt_to_endpoint=rel_mgmt_to_endpoint)

    endpoint = type_to_endpoint.get(type_name)
    location = None
    if endpoint:
        pk_value = getattr(result, "id", None)
        if pk_value is not None:
            try:
                location = reverse(
                    endpoint["url_name"],
                    kwargs={endpoint["pk_name"]: str(pk_value)},
                )
            except (NoReverseMatch, ImproperlyConfigured):
                pass

    body: dict = {"data": resource, "jsonapi": {"version": "1.0"}}
    if extra_links:
        body["links"] = extra_links
    if included:
        body["included"] = [_serialize_resource(r, type_to_endpoint, fields, rel_to_endpoint=rel_to_endpoint, rel_mgmt_to_endpoint=rel_mgmt_to_endpoint) for r in included]
    response = JsonResponse(body, status=201, content_type="application/vnd.api+json")
    if location:
        response["Location"] = location
    return response


def _convert_rel_id(raw_id: Any, tp: type) -> Any:
    if _is_nullable(tp):
        non_null_args = [a for a in get_args(tp) if a is not type(None)]
        effective_type = non_null_args[0] if non_null_args else str
    else:
        effective_type = tp
    if effective_type is int:
        return int(raw_id)
    if effective_type is float:
        return float(raw_id)
    if effective_type is uuid_type.UUID:
        return uuid_type.UUID(raw_id)
    return raw_id


def _validation_error_to_error_obj(exc: jsonschema.ValidationError) -> dict:
    pointer_parts = ["data"] + [str(p) for p in exc.absolute_path]
    return {
        "status": "400",
        "title": "Bad request",
        "detail": exc.message,
        "source": {"pointer": "/" + "/".join(pointer_parts)},
    }
