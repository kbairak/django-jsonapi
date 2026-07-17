# SDK Generation — Design Doc

## Goal

`./manage.py generate_jsonapi_client` inspects a `DjsonApi` instance and
generates a typed async client SDK package for it. Most functionality lives in
the existing `djsonapi_client` runtime; the generated code is a thin typed
layer on top.

## Command

```bash
./manage.py generate_jsonapi_client \
  --output ~/articles_sdk \
  articles.views::api
```

- `articles.views::api` → import `articles.views`, get the `api` attribute
  (`::attr` may be omitted, defaults to `api`)
- `djsonapi` must be in `INSTALLED_APPS` for command discovery
- The output directory *is* the package; its basename must be a valid
  Python identifier
- Implementation: `djsonapi/management/commands/generate_jsonapi_client.py`
  (thin wrapper) + `djsonapi/generator.py` (`generate(api, output_dir)`)

## Generated package layout

```
~/articles_sdk/
  __init__.py      # re-exports: sdk, SDK, resource classes, Collection, Resource
  resources.py     # generated: TypedDicts, Collection subclasses, Resource subclasses
  sdk.py           # generated: SDK subclass + module-level `sdk` singleton
  py.typed
  _runtime/        # verbatim copy of djsonapi_client/*.py (aiohttp only dep)
    __init__.py
    collection.py
    exceptions.py
    resource.py
    sdk.py
```

No `pyproject.toml` — packaging is up to the user.

## Runtime hooks (in `djsonapi_client`, backwards compatible)

The lazy client behavior is unchanged; generated subclasses opt into stricter
behavior via ClassVars:

- **Type conversion** — `Resource._attribute_types: dict[str, Any]` maps
  attribute names (and `"id"`) to type annotations. On hydrate, values are
  converted (`datetime.datetime`, `datetime.date`, `datetime.time`,
  `uuid.UUID`, primitives, `list[...]`, `Optional[...]`). On payload build,
  values are serialized back (`isoformat`, `str`). Relationship ids are
  serialized to strings to match server JSON schemas.
- **Typed relationships** — `Resource._relationship_types:
  dict[str, tuple[str, bool]]` maps relationship names to
  `(target_type, plural)`. Plain ids assigned to such fields (e.g.
  `author=42`) are coerced into proper `{data: {type, id}}` relationship
  objects instead of being mistaken for attributes.
- **Capability gating** — `Resource._capabilities: frozenset[str]`
  (`get_one`/`get_many`/`create`/`edit`/`delete`) and
  `Resource._relationship_capabilities: dict[str, frozenset[str]] | None`
  (`fetch`/`add`/`remove`/`reset`). Unsupported operations raise
  `AttributeError`. Defaults allow everything (lazy client unchanged).
- **`fetch(relationship)`** — GETs the relationship's `related` link
  (falling back to `{type}/{id}/{relationship}`), parses the response,
  updates `self._related[relationship]`, and returns a `Resource` (singular)
  or a fetched `Collection` (plural, using the target's collection class).
- **Query translation** — `list(**query)`, `get(id, **query)` and
  `Collection.filter(**kwargs)` accept dunder-style kwargs and translate
  them to what the server expects: `filter__x__y` → `filter[x][y]`,
  `page__n` → `page[n]`, `include__a__b` → `include=a.b` (CSV),
  `fields__t` → `fields[t]`, `extra__x` → `x`; unknown keys pass through.
- **Typed collections** — `Collection` is `Generic[T]` and chainable
  methods return `Self`; `Resource._collection_class` lets generated
  resources return per-resource `Collection` subclasses.
- **Sealed registry** — `DjsonApiSdk._resource_classes` (ClassVar, default
  `None` = open/lazy). When set, `sdk.<attr>` only resolves known resource
  types (bound per-instance subclasses), anything else raises
  `AttributeError`.

## Generated code (thin layer)

For each resource type discovered from `api.registry`:

```python
class ArticleQuery(TypedDict, total=False):      # from get_many handler params
    filter__title__contains: str
    sort: str
    page: int
    include__author: bool

class ArticleGetQuery(TypedDict, total=False):   # from get_one handler params
    include__author: bool

class ArticleEdit(TypedDict, total=False):       # from _edit_fields
    title: str | None
    content: str | None
    author: int | None

class ArticleCollection(Collection[Article]):
    def filter(self, **kwargs: Unpack[ArticleQuery]) -> Self: ...

class Article(Resource):
    _type: ClassVar[str] = "articles"
    _attribute_types: ClassVar[dict[str, Any]] = {...}        # from server annotations
    _relationship_types: ClassVar[dict[str, tuple[str, bool]]] = {...}
    _capabilities: ClassVar[frozenset[str]] = frozenset({...})
    _relationship_capabilities: ClassVar[...] = {...}
    _collection_class: ClassVar = ArticleCollection

    id: int
    title: str
    created_at: datetime.datetime

    @classmethod
    def list(cls, **query: Unpack[ArticleQuery]) -> ArticleCollection: ...
    @classmethod
    async def get(cls, id: int | str | None = None, **query: Unpack[ArticleGetQuery]) -> Article: ...
    @classmethod
    async def create(cls, *, title: str, content: str, author: int | None = None) -> Article: ...
    async def save(self, *fields: str, force_create: bool = False, **kwargs: Unpack[ArticleEdit]) -> None: ...

    @overload
    async def fetch(self, relationship: Literal["author"]) -> User: ...
    @overload
    async def fetch(self, relationship: Literal["categories"]) -> CategoryCollection: ...
    @overload
    async def fetch(self, relationship: str) -> Resource | Collection: ...
```

Only supported operations get wrappers: no DELETE endpoint → no `delete`
mention, and the capability flag makes the inherited method raise. `create`
signatures come from `_create_fields`/`_required_create_fields`; relationship
fields take plain ids. `fetch` overloads give precise return types per
relationship (target's `Collection` subclass for plural when the target has a
list endpoint).

Generated `sdk.py`:

```python
class SDK(DjsonApiSdk):
    _resource_classes: ClassVar = {"articles": Article, "users": User, ...}
    articles: type[Article]
    users: type[User]

sdk = SDK()
```

## Generator introspection

`djsonapi/generator.py::_collect` walks `api.registry`:

- endpoint class → capability (`GetOneEndpoint` → `get_one`, etc.)
- `return_resource_type` (falls back to payload annotation) → the server
  `Resource` class → annotations, `_attributes`, `_singular/plural_relationships`,
  `_create_fields`, `_required_create_fields`, `_edit_fields`
- `GetManyEndpoint`/`GetOneEndpoint` handler signatures → query TypedDicts
  (`filter__*`/`page`/`sort`/`include__*`/`fields__*`/`extra__*` params with
  their annotations, `Literal` supported)
- relationship endpoints → relationship capabilities; `return_resource_type`
  + list detection → `fetch` overload targets

## Usage

```python
from articles_sdk import SDK, sdk

sdk.setup(host="https://api.example.com/api")
article = await sdk.articles.get(1)

# or per-user instances
alice = SDK(host="https://api.example.com/api", ...)
```

## Tests

- `tests/client/test_typed_features.py` — runtime hooks: conversion,
  capability gating, `fetch`, query translation, sealed registry
- `tests/server/test_generate_jsonapi_client.py` — end-to-end: generates a
  package from an inline API, imports it, exercises it with a mocked aiohttp
  session

## Server-side parsing notes

- `filter__x__y` handler params accept the bracket form `filter[x][y]`
  (preferred, matches the OpenAPI spec); the bare suffix form `x__y` is
  still accepted for backwards compatibility.
- `page__number`-style handler params are parsed from `page[number]`.
- Relationship ids must serialize as strings in payloads
  (`_rel_schema_*` declares `id: {"type": "string"}`).
- Handler return annotations must be real types for introspection — avoid
  `from __future__ import annotations` in view modules.

## Future: TypeScript

Same pattern: runtime copy + generated types. Not implemented.
