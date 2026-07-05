import asyncio
import inspect
import json as json_module
import uuid as uuid_type
from collections.abc import Callable
from typing import Any, get_args, get_origin

import jsonschema
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import NoReverseMatch, path, reverse

from .exceptions import DjsonApiException, InternalServerError
from .resource import MISSING, Resource

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


_QUERY_PARAM_FAMILIES: dict = {
    "filter": {"flat": False, "nested": True, "strip": False},
    "page": {"flat": True, "nested": True, "strip": False},
    "sort": {"flat": True, "nested": False, "strip": False},
    "include": {"flat": False, "nested": True, "strip": False, "bool_by_presence": True},
    "fields": {"flat": False, "nested": True, "strip": False},
    "extra": {"flat": False, "nested": True, "strip": True},
}

_MUTABLE_DEFAULT = object()


def _query_param_name(key: str) -> str:
    parts = key.split("__")
    prefix = parts[0]
    family = _QUERY_PARAM_FAMILIES.get(prefix)
    if family and family.get("strip"):
        return "__".join(parts[1:])
    result = parts[0]
    for part in parts[1:]:
        result += f"[{part}]"
    return result


def _validate_and_convert(raw: str, tp: type, query_name: str) -> Any:
    origin = get_origin(tp)
    if origin is list:
        args = get_args(tp)
        item_tp = args[0] if args else str
        if not raw.strip():
            return []
        return [  # type: ignore[return-value]
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


def _extract_query_params(handler: Callable, request: HttpRequest, exclude: frozenset = frozenset()) -> dict:
    sig = inspect.signature(handler)
    result: dict = {}
    for name, param in sig.parameters.items():
        if name == "request":
            continue
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            continue
        if name in exclude:
            continue
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
        if isinstance(annotation, type) and issubclass(annotation, Resource):
            continue
        parts = name.split("__")
        prefix = parts[0]
        family = _QUERY_PARAM_FAMILIES.get(prefix)
        if not family:
            continue
        is_flat = len(parts) == 1
        if is_flat and not family.get("flat", False):
            raise ValueError(f"'{prefix}' requires sub-parameters (e.g., '{prefix}__xxx')")
        if not is_flat and not family.get("nested", False):
            raise ValueError(f"'{prefix}' does not accept sub-parameters")
        default = param.default if param.default != inspect.Parameter.empty else _MUTABLE_DEFAULT
        query_name = _query_param_name(name)
        bool_by_presence = family.get("bool_by_presence", False) and annotation is bool
        if bool_by_presence:
            if query_name in request.GET:
                result[name] = True
            elif default is not _MUTABLE_DEFAULT:
                result[name] = default
            else:
                raise ValueError(f"Missing required query parameter: {query_name}")
            continue
        raw = request.GET.get(query_name)
        if raw is None:
            if default is _MUTABLE_DEFAULT:
                raise ValueError(f"Missing required query parameter: {query_name}")
            result[name] = default
            continue
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
    for name, param in sig.parameters.items():
        if name == "request":
            continue
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            continue
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
        if isinstance(annotation, type) and issubclass(annotation, Resource):
            continue
        parts = name.split("__")
        prefix = parts[0]
        family = _QUERY_PARAM_FAMILIES.get(prefix)
        if not family:
            continue
        is_flat = len(parts) == 1
        if is_flat and not family.get("flat", False):
            continue
        if not is_flat and not family.get("nested", False):
            continue
        has_default = param.default is not inspect.Parameter.empty
        query_name = _query_param_name(name)
        if family.get("bool_by_presence", False) and annotation is bool:
            param_obj = {
                "name": query_name,
                "in": "query",
                "required": False,
                "schema": {"type": "boolean"},
            }
        else:
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


class DjsonApi:
    def __init__(self):
        self._registry = []

    def get_one(self, type_name: str) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            url_name = f"get_one__{type_name}"
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            pk_param = [p for p in params if p.name != "request"][0]
            pk_name = pk_param.name
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
                        query_params = _extract_query_params(handler, request, exclude=frozenset(kwargs.keys()))
                    except ValueError as exc:
                        return JsonResponse(
                            {"errors": [{"status": "400", "title": "Bad request", "detail": str(exc)}]},
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
                    return _one_response(result, url_name, kwargs, self._type_to_endpoint(), fields=_extract_fields(query_params))

                async_wrapper.__name__ = handler.__name__
                async_wrapper.__qualname__ = handler.__qualname__
                async_wrapper.__module__ = handler.__module__
                async_wrapper.__doc__ = handler.__doc__
                async_wrapper.__wrapped__ = handler
                wrapper = async_wrapper
            else:

                def sync_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(handler, request, exclude=frozenset(kwargs.keys()))
                    except ValueError as exc:
                        return JsonResponse(
                            {"errors": [{"status": "400", "title": "Bad request", "detail": str(exc)}]},
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
                    return _one_response(result, url_name, kwargs, self._type_to_endpoint(), fields=_extract_fields(query_params))

                sync_wrapper.__name__ = handler.__name__
                sync_wrapper.__qualname__ = handler.__qualname__
                sync_wrapper.__module__ = handler.__module__
                sync_wrapper.__doc__ = handler.__doc__
                sync_wrapper.__wrapped__ = handler
                wrapper = sync_wrapper

            self._registry.append(
                {
                    "type_name": type_name,
                    "method": "get_one",
                    "handler": wrapper,
                    "pk_name": pk_name,
                    "pk_type": pk_type,
                    "resource_class": resource_class,
                }
            )
            return wrapper

        return decorator

    def get_many(self, type_name: str) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
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
                        query_params = _extract_query_params(handler, request, exclude=frozenset(kwargs.keys()))
                    except ValueError as exc:
                        return JsonResponse(
                            {"errors": [{"status": "400", "title": "Bad request", "detail": str(exc)}]},
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
                    return _many_response(result, url_name, self._type_to_endpoint(), fields=_extract_fields(query_params))

                async_wrapper.__name__ = handler.__name__
                async_wrapper.__qualname__ = handler.__qualname__
                async_wrapper.__module__ = handler.__module__
                async_wrapper.__doc__ = handler.__doc__
                async_wrapper.__wrapped__ = handler
                wrapper = async_wrapper
            else:

                def sync_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(handler, request, exclude=frozenset(kwargs.keys()))
                    except ValueError as exc:
                        return JsonResponse(
                            {"errors": [{"status": "400", "title": "Bad request", "detail": str(exc)}]},
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
                    return _many_response(result, url_name, self._type_to_endpoint(), fields=_extract_fields(query_params))

                sync_wrapper.__name__ = handler.__name__
                sync_wrapper.__qualname__ = handler.__qualname__
                sync_wrapper.__module__ = handler.__module__
                sync_wrapper.__doc__ = handler.__doc__
                sync_wrapper.__wrapped__ = handler
                wrapper = sync_wrapper

            self._registry.append(
                {
                    "type_name": type_name,
                    "method": "get_many",
                    "handler": wrapper,
                    "resource_class": resource_class,
                }
            )
            return wrapper

        return decorator

    def create_one(self, type_name: str) -> Callable[..., Any]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
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
                        query_params = _extract_query_params(handler, request, exclude=frozenset(kwargs.keys()))
                    except ValueError as exc:
                        return JsonResponse(
                            {"errors": [{"status": "400", "title": "Bad request", "detail": str(exc)}]},
                            status=400,
                        )
                    try:
                        body = json_module.loads(request.body)
                        data = body.get("data", {})
                        jsonschema.validate(data, resource_class.jsonschema_create())
                        payload = resource_class._from_jsonapi_payload(body)
                        result = await handler(request, payload=payload, **query_params)
                        return _create_response(result, type_name, self._type_to_endpoint())
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

                async_wrapper.__name__ = handler.__name__
                async_wrapper.__qualname__ = handler.__qualname__
                async_wrapper.__module__ = handler.__module__
                async_wrapper.__doc__ = handler.__doc__
                async_wrapper.__wrapped__ = handler
                wrapper = async_wrapper
            else:

                def sync_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        query_params = _extract_query_params(handler, request, exclude=frozenset(kwargs.keys()))
                    except ValueError as exc:
                        return JsonResponse(
                            {"errors": [{"status": "400", "title": "Bad request", "detail": str(exc)}]},
                            status=400,
                        )
                    try:
                        body = json_module.loads(request.body)
                        data = body.get("data", {})
                        jsonschema.validate(data, resource_class.jsonschema_create())
                        payload = resource_class._from_jsonapi_payload(body)
                        result = handler(request, payload=payload, **query_params)
                        return _create_response(result, type_name, self._type_to_endpoint())
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

                sync_wrapper.__name__ = handler.__name__
                sync_wrapper.__qualname__ = handler.__qualname__
                sync_wrapper.__module__ = handler.__module__
                sync_wrapper.__doc__ = handler.__doc__
                sync_wrapper.__wrapped__ = handler
                wrapper = sync_wrapper

            self._registry.append(
                {
                    "type_name": type_name,
                    "method": "create_one",
                    "handler": wrapper,
                    "resource_class": resource_class,
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
                        type_name, resource_class, type_to_endpoint, spec
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
                        type_name, resource_class, type_to_endpoint, spec
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
        return spec


def _add_relationship_links(resource, type_to_endpoint):
    for rel_data in resource.get("relationships", {}).values():
        data = rel_data.get("data")
        if isinstance(data, dict):
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
        resource["attributes"] = {k: v for k, v in resource["attributes"].items() if k in fields_for_type}
    if "relationships" in resource:
        resource["relationships"] = {k: v for k, v in resource["relationships"].items() if k in fields_for_type}


def _one_response(result, url_name, kwargs, type_to_endpoint, fields=None):
    resource = result.serialize()
    if fields:
        _apply_fields(resource, fields.get(result._type))
    try:
        self_url = reverse(url_name, kwargs=kwargs)
        resource.setdefault("links", {})["self"] = self_url
        links = {"self": self_url}
    except (NoReverseMatch, ImproperlyConfigured):
        links = {}

    _add_relationship_links(resource, type_to_endpoint)

    body = {"data": resource, "links": links, "jsonapi": {"version": "1.0"}}
    return JsonResponse(body, content_type="application/vnd.api+json")


def _many_response(result_list, url_name, type_to_endpoint, fields=None):
    resources = []
    for result in result_list:
        resource = result.serialize()
        if fields:
            _apply_fields(resource, fields.get(result._type))
        _add_relationship_links(resource, type_to_endpoint)
        resources.append(resource)

    try:
        self_url = reverse(url_name)
        links = {"self": self_url}
    except (NoReverseMatch, ImproperlyConfigured):
        links = {}

    body = {"data": resources, "links": links, "jsonapi": {"version": "1.0"}}
    return JsonResponse(body, content_type="application/vnd.api+json")


def _add_links_to_schema(schema, resource_class, type_to_endpoint):
    rel_props = schema.get("properties", {}).get("relationships", {}).get("properties", {})
    for rel_field, rel_type_name in resource_class._singular_relationships:
        endpoint = type_to_endpoint.get(rel_type_name)
        if endpoint and rel_field in rel_props:
            rel_props[rel_field]["properties"] = rel_props[rel_field].get("properties", {})
            rel_props[rel_field]["properties"]["links"] = {
                "type": "object",
                "properties": {
                    "related": {"type": "string", "format": "uri"},
                },
            }


def _ensure_schema(type_name, resource_class, type_to_endpoint, spec):
    schema_name = f"{type_name}_resource"
    if schema_name not in spec["components"]["schemas"]:
        schema_obj = resource_class.jsonschema_read()
        _add_links_to_schema(schema_obj, resource_class, type_to_endpoint)
        spec["components"]["schemas"][schema_name] = schema_obj


def _response_schema(type_name, resource_class, type_to_endpoint, spec):
    _ensure_schema(type_name, resource_class, type_to_endpoint, spec)
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


def _create_response(result, type_name, type_to_endpoint):
    if result is None:
        return JsonResponse({"jsonapi": {"version": "1.0"}}, status=202)

    resource = result.serialize()
    _add_relationship_links(resource, type_to_endpoint)

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

    response = JsonResponse(
        {"data": resource, "jsonapi": {"version": "1.0"}},
        status=201,
        content_type="application/vnd.api+json",
    )
    if location:
        response["Location"] = location
    return response


def _validation_error_to_error_obj(exc: jsonschema.ValidationError) -> dict:
    pointer_parts = ["data"] + [str(p) for p in exc.absolute_path]
    return {
        "status": "400",
        "title": "Bad request",
        "detail": exc.message,
        "source": {"pointer": "/" + "/".join(pointer_parts)},
    }
