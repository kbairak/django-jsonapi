# SDK Generation — Design Doc

## Goal

`./manage.py generate_jsonapi_client` that inspects a `DjsonApi` instance and generates a typed async client SDK for any project using `djsonapi`.

## Command

```bash
./manage.py generate_jsonapi_client \
  --language python \
  --output ~/articles_sdk \
  articles.views::api
```

- `articles.views::api` → import `articles.views`, get `api` attribute
- Generator inspects `api._registry` for all types, handlers, params, schemas

## Generated SDK Structure

```
~/articles_sdk/
  __init__.py       # ~5 lines: schema JSON blob + SDK(host="", __schema__=SCHEMA)
  __init__.pyi      # Typed stubs for IDE completion
  _runtime.py       # Generic runtime (same for all projects, ships with djsonapi)
  py.typed
  schemas/
    articles.create.json
    articles.edit.json
    categories.create.json
    ...
```

## Runtime (`_runtime.py`)

Single generic file, identical across all generated SDKs. Ships with the `djsonapi` package and is copied into the SDK output.

### `SDK`

```python
@dataclass
class SDK:
    host: str = ""
    headers: dict[str, str] | Callable | Callable[[], Awaitable[dict[str, str]]] = field(default_factory=dict)
    _registry: dict[str, type[Resource]] = field(default_factory=dict)
    __schema__: dict | None = None

    def setup(self, host="", headers=None):
        if host: self.host = host
        if headers is not None: self.headers = headers

    def __getattr__(self, name):
        if self.__schema__ and name not in self.__schema__["resources"]:
            raise AttributeError(name)
        typ = self.__schema__["resources"][name]
        cls = type(name, (Resource,), {"_api": self, "TYPE": typ})
        self._registry[name] = cls
        return cls
```

- `__getattr__` lazily creates Resource subclasses from schema metadata
- No Python resource class definitions needed in generated code
- Schema maps class names and lowercase plurals to JSON:API `type` strings (e.g., `"Article"` → `"articles"`, `"articles"` → `"articles"`)

### `Resource`

```python
class Resource:
    _api: ClassVar[SDK]
    TYPE: ClassVar[str]

    @classmethod
    async def list(cls, **kwargs) -> Collection: ...
    @classmethod
    async def filter(cls, **kwargs) -> Collection: ...
    @classmethod
    async def get(cls, id=None, **kwargs) -> Resource: ...
    @classmethod
    async def create(cls, **kwargs) -> Resource: ...
    @classmethod
    async def all(cls) -> AsyncGenerator[Resource]: ...

    async def save(self, *fields: str, **kwargs) -> None: ...
    async def delete(self) -> None: ...
    async def reload(self) -> None: ...
    async def fetch(self, rel_name: str) -> Collection | Resource: ...
    async def change(self, field: str, value) -> None: ...
    async def add(self, field: str, values: list) -> None: ...
    async def remove(self, field: str, values: list) -> None: ...
    async def reset(self, field: str, values: list) -> None: ...
```

- Attribute shortcut: `__getattr__` checks `self.attributes`, then `self.related`, then raises
- `__setattr__` writes to `self.attributes` or `self.related` for known fields
- HTTP via httpx.AsyncClient
- Mirrors Transifex `transifex.api.jsonapi.Resource` interface

### `Collection`

```python
class Collection:
    def filter(self, **kwargs) -> Collection: ...
    def include(self, *rels: str) -> Collection: ...
    def sort(self, *fields: str) -> Collection: ...
    def fields(self, *fields: str) -> Collection: ...
    def page(self, *args, **kwargs) -> Collection: ...
    def extra(self, **kwargs) -> Collection: ...

    async def get(self) -> Resource: ...
    async def all(self) -> AsyncGenerator[Resource]: ...
    async def __aiter__(self) -> AsyncIterator[Resource]: ...
    async def __len__(self) -> int: ...
```

- Lazy — no HTTP until iteration or `.get()`
- Chainable — each method returns new `Collection` with accumulated params

## Generated `__init__.py`

Minimal Python, schema-driven:

```python
import json
from ._runtime import SDK

SCHEMA = json.loads(r"""{
  "resources": {
    "Article": "articles",
    "articles": "articles",
    "Category": "categories",
    "categories": "categories",
    "User": "users",
    "users": "users"
  },
  "schemas": {
    "articles": {
      "create": { ... JSON Schema ... },
      "edit": { ... JSON Schema ... }
    }
  }
}""")

sdk = SDK(__schema__=SCHEMA)
```

No `@register`, no class definitions. Everything comes from the schema blob.

## Generated `__init__.pyi`

Full typed stubs for IDE completion. Generated per-project:

```python
class _Collection[T]:
    def filter(self, **kwargs) -> _Collection[T]: ...
    def include(self, *rels: str) -> _Collection[T]: ...
    def sort(self, *fields: str) -> _Collection[T]: ...
    def fields(self, *fields: str) -> _Collection[T]: ...
    async def get(self) -> T: ...
    def all(self) -> AsyncGenerator[T]: ...
    async def __aiter__(self) -> AsyncIterator[T]: ...

class Article:
    id: int | None
    title: str
    content: str
    created_at: datetime
    author: int
    categories: list[int]

    @classmethod
    async def list(cls, **kwargs) -> _Collection[Article]: ...
    @classmethod
    async def filter(cls, title__contains: str = "",
                     categories: str = "", sort: str = "",
                     page: int = 1,
                     include__author: bool = False,
                     include__categories: bool = False) -> _Collection[Article]: ...
    @classmethod
    async def get(cls, id: int | None = None, **kwargs) -> Article: ...
    @classmethod
    async def create(cls, title: str, content: str, author: int,
                     categories: list[int] | None = None) -> Article: ...
    @classmethod
    def all(cls) -> AsyncGenerator[Article]: ...

    async def save(self, *fields: str, **set_fields) -> None: ...
    async def delete(self) -> None: ...
    async def reload(self) -> None: ...
    async def fetch[T](self, rel_name: str) -> T: ...
    async def change(self, field: str, value) -> None: ...
    async def add(self, field: str, values: list) -> None: ...
    async def remove(self, field: str, values: list) -> None: ...
    async def reset(self, field: str, values: list) -> None: ...

class SDK:
    Article: type[Article]
    articles: type[Article]
    Category: type[Category]
    categories: type[Category]
    User: type[User]
    users: type[User]

    def __init__(self, host: str = "", headers: ... = ...,
                 __schema__: dict | None = None) -> None: ...
    def setup(self, host: str = "", headers: ... = ...) -> None: ...

sdk: SDK
```

## Generator (management command)

Lives at `src/djsonapi/management/commands/generate_jsonapi_client.py`.

Steps:
1. Import the specified module, extract the `DjsonApi` instance
2. Iterate `api._registry`, group by `type_name`
3. For each type:
   - Extract `resource_class` → `_type`, `_attributes`, `_singular_relationships`, `_plural_relationships`, `_create_fields`, `_edit_fields`
   - Extract filter params from handler signatures (via `handler.__wrapped__`)
   - Call `Resource.jsonschema_create()` / `.jsonschema_edit()` for JSON schemas
4. Build schema dict: `{resources: {name: type, ...}, schemas: {type: {create: ..., edit: ...}}}`
5. Write `__init__.py` with schema blob + `SDK(__schema__=SCHEMA)`
6. Write `__init__.pyi` with typed stubs
7. Copy `_runtime.py` from djsonapi package
8. Write `py.typed`
9. Write `schemas/*.json`

## Usage

```python
from articles_sdk import sdk

# Global convenience
sdk.setup(host="https://api.example.com/api", auth="<TOKEN>")
await sdk.Article.list()

# Per-user instances
api = SDK(host="https://api.example.com/api", auth="<USER_TOKEN>")
await api.Article.filter(title__contains="food")

article = await api.Article.get(1)
article.title  # IDE completion
await article.fetch('author')
await article.save(title="Updated")
```

## Future: TypeScript

Same pattern:
- `index.ts` with `Proxy` for dynamic resource access
- `index.d.ts` for IDE completion
- `schemas/*.json` for validation
- Generator flag: `--language typescript`

## Future: Multiple instances

```python
alice = SDK(host="https://api.example.com/api", auth="<ALICE_TOKEN>")
bob = SDK(host="https://api.example.com/api", auth="<BOB_TOKEN>")
await alice.Article.list()
await bob.Article.list()
```

Each `SDK` instance creates its own Resource subclasses via `__getattr__`, binding `_api` to that instance.
