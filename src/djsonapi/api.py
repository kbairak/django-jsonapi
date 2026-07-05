import asyncio
import inspect
import uuid as uuid_type
from collections.abc import Callable
from typing import Any, get_args, get_origin

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, JsonResponse
from django.urls import NoReverseMatch, path, reverse

from .exceptions import DjsonApiException, InternalServerError
from .resource import Resource

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
                        result = await handler(request, **kwargs)
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
                    return _one_response(result, url_name, kwargs, self._type_to_endpoint())

                async_wrapper.__name__ = handler.__name__
                async_wrapper.__qualname__ = handler.__qualname__
                async_wrapper.__module__ = handler.__module__
                async_wrapper.__doc__ = handler.__doc__
                wrapper = async_wrapper
            else:

                def sync_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        result = handler(request, **kwargs)
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
                    return _one_response(result, url_name, kwargs, self._type_to_endpoint())

                sync_wrapper.__name__ = handler.__name__
                sync_wrapper.__qualname__ = handler.__qualname__
                sync_wrapper.__module__ = handler.__module__
                sync_wrapper.__doc__ = handler.__doc__
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
                        result = await handler(request, **kwargs)
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
                    return _many_response(result, url_name, self._type_to_endpoint())

                async_wrapper.__name__ = handler.__name__
                async_wrapper.__qualname__ = handler.__qualname__
                async_wrapper.__module__ = handler.__module__
                async_wrapper.__doc__ = handler.__doc__
                wrapper = async_wrapper
            else:

                def sync_wrapper(request, **kwargs) -> JsonResponse:
                    try:
                        result = handler(request, **kwargs)
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
                    return _many_response(result, url_name, self._type_to_endpoint())

                sync_wrapper.__name__ = handler.__name__
                sync_wrapper.__qualname__ = handler.__qualname__
                sync_wrapper.__module__ = handler.__module__
                sync_wrapper.__doc__ = handler.__doc__
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

    @property
    def urls(self):
        result = []
        for entry in self._registry:
            type_name = entry["type_name"]
            if entry["method"] == "get_one":
                pk_name = entry["pk_name"]
                django_type = _PYTHON_TO_DJANGO_PATH.get(entry["pk_type"], "str")
                result.append(
                    path(
                        f"{type_name}/<{django_type}:{pk_name}>",
                        entry["handler"],
                        name=f"get_one__{type_name}",
                    )
                )
            elif entry["method"] == "get_many":
                result.append(
                    path(
                        f"{type_name}/",
                        entry["handler"],
                        name=f"get_many__{type_name}",
                    )
                )
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

    def _docs_view(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse(self._build_openapi_spec())

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

            if entry["method"] == "get_one":
                pk_name = entry["pk_name"]
                pk_type = entry["pk_type"]
                openapi_type = _PYTHON_TO_OPENAPI.get(pk_type, "string")
                path_str = f"/{type_name}/{{{pk_name}}}"
                path_item = spec["paths"].setdefault(path_str, {})
                schema = {"type": openapi_type}
                if pk_type is uuid_type.UUID:
                    schema["format"] = "uuid"
                response_schema: dict = {}
                if resource_class:
                    schema_name = f"{type_name}_resource"
                    schema_obj = resource_class.jsonschema_read()
                    _add_links_to_schema(schema_obj, resource_class, type_to_endpoint)
                    spec["components"]["schemas"][schema_name] = schema_obj
                    response_schema = {
                        "type": "object",
                        "properties": {
                            "data": {"$ref": f"#/components/schemas/{schema_name}"},
                            "jsonapi": {
                                "type": "object",
                                "properties": {"version": {"const": "1.0"}},
                            },
                        },
                    }
                path_item["get"] = {
                    "parameters": [
                        {
                            "name": pk_name,
                            "in": "path",
                            "required": True,
                            "schema": schema,
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

            elif entry["method"] == "get_many":
                path_str = f"/{type_name}/"
                path_item = spec["paths"].setdefault(path_str, {})
                response_schema: dict = {}
                if resource_class:
                    schema_name = f"{type_name}_resource"
                    if schema_name not in spec["components"]["schemas"]:
                        schema_obj = resource_class.jsonschema_read()
                        _add_links_to_schema(schema_obj, resource_class, type_to_endpoint)
                        spec["components"]["schemas"][schema_name] = schema_obj
                    response_schema = {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "array",
                                "items": {"$ref": f"#/components/schemas/{schema_name}"},
                            },
                            "jsonapi": {
                                "type": "object",
                                "properties": {"version": {"const": "1.0"}},
                            },
                        },
                    }
                path_item["get"] = {
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


def _one_response(result, url_name, kwargs, type_to_endpoint):
    resource = result.serialize()
    try:
        self_url = reverse(url_name, kwargs=kwargs)
        resource.setdefault("links", {})["self"] = self_url
        links = {"self": self_url}
    except (NoReverseMatch, ImproperlyConfigured):
        links = {}

    _add_relationship_links(resource, type_to_endpoint)

    body = {"data": resource, "links": links, "jsonapi": {"version": "1.0"}}
    return JsonResponse(body, content_type="application/vnd.api+json")


def _many_response(result_list, url_name, type_to_endpoint):
    resources = []
    for result in result_list:
        resource = result.serialize()
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
