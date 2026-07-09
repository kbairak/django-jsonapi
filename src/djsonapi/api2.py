import functools
import inspect
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Sequence, get_args, get_origin
from uuid import UUID

from django.http import HttpRequest, JsonResponse
from django.urls import NoReverseMatch, URLPattern, reverse
from django.urls import path as django_path

from djsonapi.exceptions import (
    BadRequest,
    DjsonApiExceptionMulti,
    DjsonApiExceptionSingle,
    InternalServerError,
    MethodNotAllowed,
    NotFound,
)
from djsonapi.resource import Resource
from djsonapi.response import Response

# _VALID_PREFIXES = ["filter__", "page", "sort", "include__", "fields__", "extra__"]


@dataclass
class Endpoint:
    type_name: str
    handler: Callable[..., Any]
    errors: Sequence[type[DjsonApiExceptionSingle]] | None = None

    METHOD = ""
    URL_NAME_TEMPLATE = ""

    @property
    def url_name(self) -> str:
        return self.URL_NAME_TEMPLATE.format(type_name=self.type_name)

    @functools.cached_property
    def url(self):
        return f"{self.type_name}"

    @functools.cached_property
    def signature(self) -> inspect.Signature:
        return inspect.signature(self.handler)

    @functools.cached_property
    def parameters(self) -> list[inspect.Parameter]:
        return list(self.signature.parameters.values())

    @functools.cached_property
    def return_annotation(self):
        return self.signature.return_annotation

    @functools.cached_property
    def smart_parameters(self) -> list[inspect.Parameter]:
        return self.parameters[1:]

    @functools.cached_property
    def expected_extra(self) -> list[inspect.Parameter]:
        """Extra parameters that the handler function expects

        >>> @api.get_many("articles")
        ... def get_articles(
        ...     request: HttpRequest, extra__details: bool = False, extra__async: bool = False
        ... ) -> list[ArticleResource]: ...

        >>> get_articles.expected_extra
        <<< [inspect.Parameter(..), inspect.Parameter(..)]
        """

        return [
            parameter
            for parameter in self.smart_parameters
            if parameter.name.startswith("extra__")
        ]

    @functools.cached_property
    def return_resource_type(self):
        """Extract Resource subclass from return type annotation

        - `-> ResourceSubclass` returns `ResourceSubclass`
        - `-> Response[ResourceSubclass]` returns `ResourceSubclass`
        - `-> Response[list[ResourceSubclass]]` returns `ResourceSubclass`
        - Otherwise returns None
        """

        if isinstance(self.return_annotation, type) and issubclass(
            self.return_annotation, Resource
        ):
            return self.return_annotation
        origin = get_origin(self.return_annotation)
        if not (isinstance(origin, type) and issubclass(origin, Response)):
            return None
        args = get_args(self.return_annotation)
        if not args:
            return None
        inner = args[0]
        if isinstance(inner, type) and issubclass(inner, Resource):
            return inner
        iorigin = get_origin(inner)
        if isinstance(iorigin, type) and issubclass(iorigin, list):
            iargs = get_args(inner)
            if iargs and isinstance(iargs[0], type) and issubclass(iargs[0], Resource):
                return iargs[0]
        return None


@dataclass(kw_only=True)
class ReturnsDataMixin:
    return_annotation: ClassVar
    smart_parameters: ClassVar[Sequence[inspect.Parameter]]
    return_resource_type: ClassVar[type[Resource] | None]
    expected_extra: ClassVar[list[inspect.Parameter]]

    sparse: bool = True
    include_types: Sequence[type[Resource]] = field(default_factory=list)

    def __post_init__(self):
        if forbidden_includes := self.expected_includes - self.allowed_includes:
            raise ValueError(f"Invalid include types: {forbidden_includes}")
        if forbidden_sparse_types := self.expected_sparse - self.allowed_sparse.keys():
            raise ValueError(f"Invalid sparse types: {forbidden_sparse_types}")

    @functools.cached_property
    def expected_sparse(self) -> set[str]:
        """Sparse types that the handler function expects

        >>> @api.get_many("articles", include_types=[User, Category])
        ... def get_articles(
        ...     request: HttpRequest,
        ...     fields__articles: Sequence[str] | None = None,
        ...     fields__users: Sequence[str] | None = None,
        ...     fields__categories: Sequence[str] | None = None,
        ... ) -> Response[list[ArticleResource]: ...
        ...
        >>> get_articles.expected_sparse
        <<< {'articles', 'users', 'categories'}
        """

        return {
            parameter.name[len("fields__") :]
            for parameter in self.smart_parameters
            if parameter.name.startswith("fields__")
        }

    @functools.cached_property
    def expected_includes(self) -> set[str]:
        """Included types that the handler function expects

        >>> @api.get_many("articles", include_types=[User, Category])
        ... def get_articles(
        ...     request: HttpRequest,
        ...     include__articles: bool = False,
        ...     include__author: bool = False,
        ...     include__categories: bool = False,
        ... ) -> Response[list[ArticleResource]]: ...

        >>> get_articles.expected_includes
        <<< {"articles", "author", "categories"}
        """

        return {
            parameter.name[len("include__") :]
            for parameter in self.smart_parameters
            if parameter.name.startswith("include__")
        }

    @functools.cached_property
    def allowed_sparse(self) -> dict[str, set[str]]:
        """Allowed sparse types and fields based on return and include types

        >>> @api.get_many("articles", include_types=[User, Category])
        ... def get_articles(request: HttpRequest) -> Response[list[ArticleResource]]: ...

        >>> get_articles.allowed_sparse
        <<< {'articles': {'title', 'content', ...},
        ...  'users': {'username', ...},
        ...  'categories': {'name', ...}}
        """

        if not self.sparse:
            return {}

        result = {}

        if self.return_resource_type is not None:
            result[self.return_resource_type._type] = {
                *self.return_resource_type._attributes,
                *[_type for _, _type in self.return_resource_type._singular_relationships],
                *[_type for _, _type in self.return_resource_type._plural_relationships],
            }

        for include_type in self.include_types:
            result[include_type._type] = {
                *include_type._attributes,
                *[_type for _, _type in include_type._singular_relationships],
                *[_type for _, _type in include_type._plural_relationships],
            }

        return result

    @functools.cached_property
    def allowed_includes(self) -> set[str]:
        """Allowed include types based on return and include types

        >>> @api.get_many("articles", include_types=[User, Category])
        ... def get_articles(request: HttpRequest) -> Response[list[ArticleResource]]: ...

        >>> get_articles.allowed_sparse
        <<< {'articles', 'author', 'categories'}  # 'author', not 'users'
        """

        if self.return_resource_type is None:
            return set()
        return {
            *[rel for rel, _ in self.return_resource_type._singular_relationships],
            *[rel for rel, _ in self.return_resource_type._plural_relationships],
        }

    def extract_kwargs(
        self, query_parameters
    ) -> tuple[dict[str, Any], list[DjsonApiExceptionSingle]]:
        request_includes = {
            relationship
            for relationship in query_parameters.get("include", "").split(",")
            if relationship
        }
        request_sparse = {
            m.groups()[0]: {_field for _field in value.split(",") if _field}
            for key, value in query_parameters.items()
            if (m := re.search(r"^fields\[(\w+)\]$", key))
        }

        errors: list[DjsonApiExceptionSingle] = []
        kwargs: dict[str, Any] = {}

        if forbidden_includes := request_includes - self.expected_includes:
            errors.append(BadRequest(f"Invalid include types: {forbidden_includes}"))
        for include_relationship in request_includes:
            kwargs[f"include__{include_relationship}"] = True
        try:
            del query_parameters["include"]
        except KeyError:
            pass

        if forbidden_sparse_types := request_sparse.keys() - self.allowed_sparse.keys():
            errors.append(BadRequest(f"Invalid fields types: {forbidden_sparse_types}"))
        for sparse_type in request_sparse.keys():
            if forbidden_sparse_fields := (
                request_sparse[sparse_type] - self.allowed_sparse[sparse_type]
            ):
                errors.append(
                    BadRequest(
                        f"Invalid fields for type '{sparse_type}': {forbidden_sparse_fields}"
                    )
                )
            elif sparse_type in self.expected_sparse:
                kwargs[f"fields__{sparse_type}"] = request_sparse[sparse_type]

        for key in request_sparse:
            del query_parameters[f"fields[{key}]"]

        for param in self.expected_extra:
            extra_name = param.name[len("extra__") :]
            raw = query_parameters.pop(extra_name, None)
            if raw is not None:
                tp = param.annotation if param.annotation != inspect.Parameter.empty else str
                try:
                    kwargs[param.name] = tp(raw)
                except ValueError as e:
                    errors.append(BadRequest(str(e)))
            elif param.default is inspect.Parameter.empty:
                errors.append(BadRequest(f"Missing required extra parameter: {extra_name}"))
            else:
                kwargs[param.name] = param.default

        return kwargs, errors


class ExpectsIdMixin:
    parameters: ClassVar[list[inspect.Parameter]]
    type_name: ClassVar[str]

    @functools.cached_property
    def pk_name(self):
        return self.parameters[1].name

    @functools.cached_property
    def pk_type(self):
        param = self.parameters[1]
        return param.annotation if param.annotation != inspect.Parameter.empty else str

    @functools.cached_property
    def url(self):
        path_type = {UUID: "uuid", int: "int", str: "str"}[self.pk_type]
        return f"{self.type_name}/<{path_type}:{self.pk_name}>"

    @functools.cached_property
    def smart_parameters(self) -> list[inspect.Parameter]:
        return self.parameters[2:]


@dataclass(kw_only=True)
class ExpectsRelationshipMixin(ExpectsIdMixin):
    relationship_name: str

    URL_NAME_TEMPLATE: ClassVar[str]

    @property
    def url_name(self):
        return self.URL_NAME_TEMPLATE.format(
            type_name=self.type_name, relationship_name=self.relationship_name
        )

    @functools.cached_property
    def url(self):
        return (
            f"{self.type_name}/<{self.pk_type}:{self.pk_name}>"
            f"/relationship/{self.relationship_name}"
        )


@dataclass
class GetOneEndpoint(ReturnsDataMixin, ExpectsIdMixin, Endpoint):
    METHOD = "GET"
    URL_NAME_TEMPLATE = "{type_name}__item"

    def view(self, request: HttpRequest, **url_kwargs: Any):
        obj_id = url_kwargs[self.pk_name]
        try:
            obj_id = self.pk_type(obj_id)
        except Exception:
            raise NotFound(f"The URL '{request.path}' does not exist")

        query_parameters = request.GET.dict()
        kwargs, errors = self.extract_kwargs(query_parameters)

        if query_parameters:
            errors.append(BadRequest(f"Unknown query parameters: {', '.join(query_parameters)}"))

        if errors:
            raise DjsonApiExceptionMulti(*errors)

        response = self.handler(request, obj_id, **kwargs)
        if not isinstance(response, Response):
            response = Response(data=response)
        return response


@dataclass
class EditOneEndpoint(ReturnsDataMixin, ExpectsIdMixin, Endpoint):
    METHOD = "PATCH"
    URL_NAME_TEMPLATE = "{type_name}__item"


@dataclass
class DeleteOneEndpoint(ExpectsIdMixin, Endpoint):
    METHOD = "DELETE"
    URL_NAME_TEMPLATE = "{type_name}__item"


@dataclass
class GetManyEndpoint(ReturnsDataMixin, Endpoint):
    METHOD = "GET"
    URL_NAME_TEMPLATE = "{type_name}__collection"


@dataclass
class CreateOneEndpoint(ReturnsDataMixin, Endpoint):
    METHOD = "POST"
    URL_NAME_TEMPLATE = "{type_name}__collection"


@dataclass
class GetRelationshipEndpoint(ReturnsDataMixin, ExpectsRelationshipMixin, Endpoint):
    METHOD = "GET"
    URL_NAME_TEMPLATE = "{type_name}__{relationship_name}__related"

    @functools.cached_property
    def url(self):
        return f"{self.type_name}/<{self.pk_type}:{self.pk_name}>/{self.relationship_name}"


@dataclass
class EditRelationshipEndpoint(ExpectsRelationshipMixin, Endpoint):
    METHOD = "PATCH"
    URL_NAME_TEMPLATE = "{type_name}__{relationship_name}__relationship"


@dataclass
class ResetRelationshipEndpoint(ExpectsRelationshipMixin, Endpoint):
    METHOD = "PATCH"
    URL_NAME_TEMPLATE = "{type_name}__{relationship_name}__relationship"


@dataclass
class AddToRelationshipEndpoint(ExpectsRelationshipMixin, Endpoint):
    METHOD = "POST"
    URL_NAME_TEMPLATE = "{type_name}__{relationship_name}__relationship"


@dataclass
class RemoveFromRelationshipEndpoint(ExpectsRelationshipMixin, Endpoint):
    METHOD = "DELETE"
    URL_NAME_TEMPLATE = "{type_name}__{relationship_name}__relationship"


@dataclass
class DjsonApi:
    registry: list[Endpoint] = field(default_factory=list)

    def get_one(
        self,
        type_name: str,
        errors: Sequence[type[DjsonApiExceptionSingle]] | None = None,
        sparse: bool = True,
        include_types: Sequence[type[Resource]] | None = None,
    ) -> Callable[[Callable[..., Any]], Endpoint]:
        if include_types is None:
            include_types = []

        def decorator(handler: Callable[..., Any]) -> Endpoint:
            endpoint = GetOneEndpoint(
                type_name, handler, errors, sparse=sparse, include_types=include_types
            )
            self.registry.append(endpoint)
            return endpoint

        return decorator

    def get_many(
        self,
        type_name: str,
        errors: Sequence[type[DjsonApiExceptionSingle]] | None = None,
        sparse: bool = True,
        include_types: Sequence[type[Resource]] | None = None,
    ) -> Callable[[Callable[..., Any]], Endpoint]:
        if include_types is None:
            include_types = []

        def decorator(handler: Callable[..., Any]) -> Endpoint:
            endpoint = GetManyEndpoint(
                type_name, handler, errors, sparse=sparse, include_types=include_types
            )
            self.registry.append(endpoint)
            return endpoint

        return decorator

    def create_one(
        self,
        type_name: str,
        errors: Sequence[type[DjsonApiExceptionSingle]] | None = None,
        sparse: bool = True,
        include_types: Sequence[type[Resource]] | None = None,
    ) -> Callable[[Callable[..., Any]], Endpoint]:
        if include_types is None:
            include_types = []

        def decorator(handler: Callable[..., Any]) -> Endpoint:
            endpoint = CreateOneEndpoint(
                type_name, handler, errors, sparse=sparse, include_types=include_types
            )
            self.registry.append(endpoint)
            return endpoint

        return decorator

    def edit_one(
        self,
        type_name: str,
        errors: Sequence[type[DjsonApiExceptionSingle]] | None = None,
        sparse: bool = True,
        include_types: Sequence[type[Resource]] | None = None,
    ) -> Callable[[Callable[..., Any]], Endpoint]:
        if include_types is None:
            include_types = []

        def decorator(handler: Callable[..., Any]) -> Endpoint:
            endpoint = EditOneEndpoint(
                type_name, handler, errors, sparse=sparse, include_types=include_types
            )
            self.registry.append(endpoint)
            return endpoint

        return decorator

    def delete_one(
        self,
        type_name: str,
        errors: Sequence[type[DjsonApiExceptionSingle]] | None = None,
    ) -> Callable[[Callable[..., Any]], Endpoint]:
        def decorator(handler: Callable[..., Any]) -> Endpoint:
            endpoint = DeleteOneEndpoint(type_name, handler, errors)
            self.registry.append(endpoint)
            return endpoint

        return decorator

    def get_relationship(
        self,
        type_name: str,
        relationship_name: str,
        errors: Sequence[type[DjsonApiExceptionSingle]] | None = None,
        sparse: bool = True,
        include_types: Sequence[type[Resource]] | None = None,
    ) -> Callable[[Callable[..., Any]], Endpoint]:
        if include_types is None:
            include_types = []

        def decorator(handler: Callable[..., Any]) -> Endpoint:
            endpoint = GetRelationshipEndpoint(
                type_name,
                handler,
                errors,
                relationship_name=relationship_name,
                sparse=sparse,
                include_types=include_types,
            )
            self.registry.append(endpoint)
            return endpoint

        return decorator

    def edit_relationship(
        self,
        type_name: str,
        relationship_name: str,
        errors: Sequence[type[DjsonApiExceptionSingle]] | None = None,
    ) -> Callable[[Callable[..., Any]], Endpoint]:
        def decorator(handler: Callable[..., Any]) -> Endpoint:
            endpoint = EditRelationshipEndpoint(
                type_name, handler, errors, relationship_name=relationship_name
            )
            self.registry.append(endpoint)
            return endpoint

        return decorator

    def reset_relationship(
        self,
        type_name: str,
        relationship_name: str,
        errors: Sequence[type[DjsonApiExceptionSingle]] | None = None,
    ) -> Callable[[Callable[..., Any]], Endpoint]:
        def decorator(handler: Callable[..., Any]) -> Endpoint:
            endpoint = ResetRelationshipEndpoint(
                type_name, handler, errors, relationship_name=relationship_name
            )
            self.registry.append(endpoint)
            return endpoint

        return decorator

    def add_to_relationship(
        self,
        type_name: str,
        relationship_name: str,
        errors: Sequence[type[DjsonApiExceptionSingle]] | None = None,
    ) -> Callable[[Callable[..., Any]], Endpoint]:
        def decorator(handler: Callable[..., Any]) -> Endpoint:
            endpoint = AddToRelationshipEndpoint(
                type_name, handler, errors, relationship_name=relationship_name
            )
            self.registry.append(endpoint)
            return endpoint

        return decorator

    def remove_from_relationship(
        self,
        type_name: str,
        relationship_name: str,
        errors: Sequence[type[DjsonApiExceptionSingle]] | None = None,
    ) -> Callable[[Callable[..., Any]], Endpoint]:
        def decorator(handler: Callable[..., Any]) -> Endpoint:
            endpoint = RemoveFromRelationshipEndpoint(
                type_name, handler, errors, relationship_name=relationship_name
            )
            self.registry.append(endpoint)
            return endpoint

        return decorator

    @property
    def urls(self) -> list[URLPattern]:
        by_path: dict[str, list] = {}
        for endpoint in self.registry:
            by_path.setdefault(endpoint.url, []).append(endpoint)
        return [
            django_path(path, self.combine_views(endpoints), name=endpoints[0].url_name)
            for path, endpoints in by_path.items()
        ]

    def combine_views(self, endpoints: list[Endpoint]) -> Callable[..., Any]:
        by_method: dict[str, Endpoint] = {endpoint.METHOD: endpoint for endpoint in endpoints}

        def view(request: HttpRequest, *args, **kwargs):
            try:
                if request.method not in by_method:
                    raise MethodNotAllowed(
                        f"Method {request.method} not allowed for this endpoint, "
                        f"allowed methods: {', '.join(by_method.keys())}"
                    )
                endpoint = by_method[request.method]
                response = endpoint.view(request, *args, **kwargs)
            except DjsonApiExceptionSingle as exc:
                return JsonResponse({"errors": exc.render()}, status=exc.status)
            except Exception:
                logging.exception("Unhandled exception in djsonapi endpoint")
                exc = InternalServerError()
                return JsonResponse({"errors": exc.render()}, status=exc.status)

            if isinstance(response, Response):
                response = response.serialize(request)

            response.setdefault("links", {})["self"] = request.get_full_path()
            if isinstance(response["data"], list):
                for item in response["data"]:
                    self._fill_resource_links(item)
                    self._filter_out_sparse(item, request)
            else:
                self._fill_resource_links(response["data"])
                self._filter_out_sparse(response["data"], request)

            for item in response.get("included", []):
                self._fill_resource_links(item)
                self._filter_out_sparse(item, request)

            return JsonResponse(response, status=200)

        return view

    def _fill_resource_links(self, resource: dict[str, Any]) -> None:
        _type = resource.get("type")
        _id = resource.get("id")

        try:
            self_link = reverse(f"{_type}__item", args=(_id,))
        except NoReverseMatch:
            pass
        else:
            resource.setdefault("links", {})["self"] = self_link

        for relationship_name, relationship in resource.get("relationships", {}).items():
            related_link = None
            try:
                relationship_type = relationship["data"]["type"]
                relationship_id = relationship["data"]["id"]
            except Exception:
                pass
            else:
                try:
                    related_link = reverse(f"{relationship_type}__item", args=(relationship_id,))
                except NoReverseMatch:
                    pass
            try:
                related_link = reverse(f"{_type}__{relationship_name}__related", args=(_id,))
            except NoReverseMatch:
                pass
            try:
                related_link = reverse(f"{_type}__{relationship_name}__related", args=(_id,))
            except NoReverseMatch:
                pass

            if related_link:
                relationship.setdefault("links", {})["related"] = related_link

            try:
                relationship_link = reverse(
                    f"{_type}__{relationship_name}__relationship", args=(_id,)
                )
            except NoReverseMatch:
                pass
            else:
                relationship.setdefault("links", {})["self"] = relationship_link

    def _filter_out_sparse(self, resource: dict[str, Any], request: HttpRequest) -> None:
        _type = resource.get("type")
        if not _type:
            return

        allowed_fields: set[str] | None = None
        for key in request.GET.keys():
            if (m := re.search(r"^fields\[(\w+)\]$", key)) and m.group(1) == _type:
                raw = request.GET.get(key, "")
                allowed_fields = {f.strip() for f in raw.split(",") if f.strip()}
                break

        if allowed_fields is None:
            return

        if "attributes" in resource:
            resource["attributes"] = {
                k: v for k, v in resource["attributes"].items() if k in allowed_fields
            }
        if "relationships" in resource:
            resource["relationships"] = {
                k: v for k, v in resource["relationships"].items() if k in allowed_fields
            }
        if len(resource.get("attributes", {})) == 0:
            resource.pop("attributes", None)
        if len(resource.get("relationships", {})) == 0:
            resource.pop("relationships", None)
