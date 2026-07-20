# djsonapi — JSON:API for Django, without the headache

[JSON:API](https://jsonapi.org/) is a specification for building APIs that don't
make you want to throw your laptop out the window. `djsonapi` brings it to
Django with:

- **Server** — Declarative resources, decorator-based endpoints, JSON Schema
  validation, OpenAPI + Redoc docs, auto-generated relationship URLs
- **Client** — Generic async client (`djsonapi_client.DjsonApiSdk`) and a
  **typed SDK generator** that produces a sealed, IDE-friendly Python package
  mirroring your exact API

```python
pip install djsonapi
```

Needs Django ≥4.2, Python ≥3.13, and works with async views natively (sync
handlers get wrapped with `sync_to_async`).

---

# Server

## Quickstart

Define a resource, register some endpoints, plug the URLs into your project:

```python
# articles/resources.py
from djsonapi import DjsonApi, Resource, Response
from typing import ClassVar

api = DjsonApi()


class ArticleResource(Resource):
    _type: ClassVar = "articles"
    _attributes: ClassVar = ["title", "content", "created_at"]
    _singular_relationships: ClassVar = [("author", "users")]
    _create_fields: ClassVar = ["title", "content", "author"]
    _required_create_fields: ClassVar = ["title"]

    id: int
    title: str
    content: str
    created_at: datetime
    author: int


class UserResource(Resource):
    _type: ClassVar = "users"
    _attributes: ClassVar = ["username", "email"]
    id: int
    username: str
    email: str
```

```python
# articles/views.py
from articles.resources import api, ArticleResource, UserResource


@api.get_one("articles")
def get_article(request, article_id: int) -> ArticleResource:
    article = Article.objects.get(id=article_id)
    return ArticleResource(
        id=article.id,
        title=article.title,
        content=article.content,
        created_at=article.created_at,
        author=article.author_id,
    )


@api.get_many("articles")
def list_articles(request) -> list[ArticleResource]:
    return [
        ArticleResource(id=a.id, title=a.title, ...)
        for a in Article.objects.all()
    ]


@api.create_one("articles")
def create_article(request, payload: ArticleResource) -> ArticleResource:
    article = Article.objects.create(**payload.as_create_payload())
    return ArticleResource(id=article.id, title=article.title, ...)


@api.edit_one("articles")
def edit_article(request, article_id: int, payload: ArticleResource) -> ArticleResource:
    article = Article.objects.get(id=article_id)
    for key, value in payload.as_edit_payload().items():
        setattr(article, key, value)
    article.save()
    return ArticleResource(id=article.id, title=article.title, ...)


> [!NOTE]
> For `PATCH` endpoints, resource fields that were not included in the request
> body are set to `Resource.UNSET`. Check `payload.field is not Resource.UNSET`
> before applying an update, or use the `UNSET` sentinel to skip fields:

```python
if payload.title is not Resource.UNSET and article.title != payload.title:
    article.title = payload.title
```


@api.delete_one("articles")
def delete_article(request, article_id: int) -> None:
    Article.objects.get(id=article_id).delete()
```

Wire it up:

```python
# blog/urls.py
from articles.resources import api

urlpatterns = [
    path("api/", api.urls),
]
```

Done. You now have:

| Method   | URL                  | What it does           |
| -------- | -------------------- | ---------------------- |
| `GET`    | `/api/articles`      | List articles          |
| `POST`   | `/api/articles`      | Create article         |
| `GET`    | `/api/articles/{id}` | Get one article        |
| `PATCH`  | `/api/articles/{id}` | Edit article           |
| `DELETE` | `/api/articles/{id}` | Delete article         |
| `GET`    | `/api/openapi.json`  | OpenAPI 3.0.3 spec     |
| `GET`    | `/api/docs/`         | Redoc interactive docs |

## What's happening on the wire?

### GET /api/articles

```
GET /api/articles HTTP/1.1
Accept: application/vnd.api+json
```

```json
{
  "data": [
    {
      "type": "articles",
      "id": "1",
      "attributes": {
        "title": "Why JSON:API is great",
        "content": "Let me count the ways...",
        "created_at": "2026-07-17T10:00:00Z"
      },
      "relationships": {
        "author": {
          "data": { "type": "users", "id": "42" },
          "links": {
            "self": "/api/articles/1/relationship/author",
            "related": "/api/articles/1/author"
          }
        }
      },
      "links": {
        "self": "/api/articles/1"
      }
    }
  ],
  "meta": {
    "count": 1
  }
}
```

### GET /api/articles/1

```
GET /api/articles/1 HTTP/1.1
Accept: application/vnd.api+json
```

Response is the same shape as above, but `data` is a single object (not a list).

### POST /api/articles

```
POST /api/articles HTTP/1.1
Content-Type: application/vnd.api+json
Accept: application/vnd.api+json

{
  "data": {
    "type": "articles",
    "attributes": {
      "title": "New post!"
    },
    "relationships": {
      "author": {
        "data": { "type": "users", "id": "42" }
      }
    }
  }
}
```

Response: `201 Created` with the full resource in `data`, plus `self` link.

### PATCH /api/articles/1

```
PATCH /api/articles/1 HTTP/1.1
Content-Type: application/vnd.api+json
Accept: application/vnd.api+json

{
  "data": {
    "type": "articles",
    "id": "1",
    "attributes": {
      "title": "Updated title"
    }
  }
}
```

Response: `200 OK` with the updated resource.

### DELETE /api/articles/1

```
DELETE /api/articles/1 HTTP/1.1
Accept: application/vnd.api+json
```

Response: `204 No Content`, no body.

## What did the library do for you?

- Validated `Content-Type: application/vnd.api+json` on every write request
- Validated `Accept` header allows `application/vnd.api+json`
- Validated the request body against an auto-generated **JSON Schema** before
  your handler ever saw it (wrong types? missing required fields? extra keys? →
  `400 Bad Request` with a descriptive error document)
- Serialized your resource into proper JSON:API shape (type, id, attributes,
  relationships, links)
- Added `self` links and relationship links automatically
- Returned proper JSON:API error documents for 404, 400, 405, etc.

## Relationships

The library auto-derives relationship endpoints. If you register a
`get_related`, it generates the `/relationship/` URLs for you.

```python
@api.get_related("articles", "author")
def get_article_author(request, article_id: int) -> UserResource:
    article = Article.objects.get(id=article_id)
    user = article.author
    return UserResource(id=user.id, username=user.username, email=user.email)
```

This gives you:

| Method | URL                                   | What it does               |
| ------ | ------------------------------------- | -------------------------- |
| `GET`  | `/api/articles/1/author`              | Get the full author object |
| `GET`  | `/api/articles/1/relationship/author` | Get just `{type, id}`      |

### Link auto-discovery

Relationship `links` in responses are populated automatically based on which
endpoints you registered. Registering `get_article_author` above is enough to
make `GET /api/articles/1` include:

```json
{
  "data": {
    "type": "articles",
    "id": "1",
    "relationships": {
      "author": {
        "data": { "type": "users", "id": "42" },
        "links": {
          "self": "/api/articles/1/relationship/author",
          "related": "/api/articles/1/author"
        }
      }
    },
    "links": { "self": "/api/articles/1" }
  }
}
```

The library walks every registered URL pattern. If a reverse match exists for
`{type}__{relationship_name}__related`, the `related` link appears. Same for
`{type}__{relationship_name}__relationship` for the `self` link. No manual
link-building needed.

You can also register mutating relationship endpoints:

```python
@api.edit_relationship("articles", "author")
def edit_article_author(request, article_id: int, author_id: int) -> None:
    article = Article.objects.get(id=article_id)
    article.author_id = author_id
    article.save()
```

```python
@api.add_to_relationship("articles", "categories")
def add_to_article_categories(request, article_id: int, category_ids: list[int]) -> None:
    article = Article.objects.get(id=article_id)
    article.categories.add(*category_ids)
```

```python
@api.remove_from_relationship("articles", "categories")
def remove_from_article_categories(request, article_id: int, category_ids: list[int]) -> None:
    article = Article.objects.get(id=article_id)
    article.categories.remove(*category_ids)
```

```python
@api.reset_relationship("articles", "categories")
def reset_article_categories(request, article_id: int, category_ids: list[int]) -> None:
    article = Article.objects.get(id=article_id)
    article.categories.set(category_ids)
```

### What's happening on the wire for relationships?

**GET /articles/1/relationship/author** (check who the author is):

```
GET /api/articles/1/relationship/author HTTP/1.1
Accept: application/vnd.api+json
```

```json
{
  "data": {
    "type": "users",
    "id": "42"
  }
}
```

**PATCH /articles/1/relationship/author** (change the author):

```
PATCH /api/articles/1/relationship/author HTTP/1.1
Content-Type: application/vnd.api+json
Accept: application/vnd.api+json

{
  "data": {
    "type": "users",
    "id": "7"
  }
}
```

Response: `204 No Content`.

**POST /articles/1/relationship/categories** (add categories):

```json
{
  "data": [
    { "type": "categories", "id": "3" },
    { "type": "categories", "id": "5" }
  ]
}
```

Response: `204 No Content`.

**DELETE /articles/1/relationship/categories** (remove categories):

Body same shape as POST. Response: `204 No Content`.

**PATCH /articles/1/relationship/categories** (replace all categories):

Body same as POST. All previous categories replaced. Response: `204 No Content`.

## Filtering, Pagination, Sorting

Your handler parameters tell the library what to parse from the query string.
Parameter names use `__` as a separator that maps to JSON:API bracket syntax.

```python
@api.get_many("articles")
def list_articles(
    request,
    filter__title__contains: str = "",
    filter__author: int | None = None,
    sort: str = "",
    page: int = 1,
    include__author: bool = False,
) -> list[ArticleResource]:
    qs = Article.objects.all()
    if filter__title__contains:
        qs = qs.filter(title__contains=filter__title__contains)
    if filter__author:
        qs = qs.filter(author_id=filter__author)
    if sort:
        qs = qs.order_by(sort)
    # ... paginate with page param
    return [ArticleResource(...) for a in qs]
```

The query string
`?filter[title][contains]=json&filter[author]=42&sort=-created_at&page=2&include=author`
maps to:

| URL param                 | Handler parameter                  |
| ------------------------- | ---------------------------------- |
| `filter[title][contains]` | `filter__title__contains = "json"` |
| `filter[author]`          | `filter__author = 42`              |
| `sort=-created_at`        | `sort = "-created_at"`             |
| `page=2`                  | `page = 2`                         |
| `include=author`          | `include__author = True`           |

The library handles type conversion (string → int, etc.), validates integers for
`page`, and rejects unknown params with a `400`.

### Sparse fields

If `sparse=True` (default), clients can request only specific fields:

```
GET /api/articles?fields[articles]=title,created_at&fields[users]=username
```

Response will omit `content` from articles and `email` from included users.

## Includes

```python
@api.get_one("articles", include_types=[UserResource])
def get_article(
    request, article_id: int, include__author: bool = False
) -> Response[ArticleResource]:
    article = Article.objects.get(id=article_id)
    included = []
    if include__author:
        included.append(
            UserResource(id=article.author.id, username=article.author.username, ...)
        )
    return Response(
        data=ArticleResource(id=article.id, title=article.title, ...),
        included=included,
    )
```

The `include__author` parameter just tells your handler what the client
requested. You must populate `Response.included` yourself. Then the response
includes a top-level `included` array:

```json
{
  "data": { "type": "articles", "id": "1", "attributes": {...}, "relationships": {...} },
  "included": [
    { "type": "users", "id": "42", "attributes": { "username": "kbairak", "email": "..." } }
  ]
}
```

## Error handling

The library returns JSON:API-compliant error documents:

```json
{
  "errors": [
    {
      "status": "400",
      "title": "Bad Request",
      "detail": "Payload must have a 'data' key"
    }
  ]
}
```

## OpenAPI + Redoc

Your API is automatically documented:

- `GET /api/openapi.json` — OpenAPI 3.0.3 spec
- `GET /api/docs/` — Redoc interactive docs

The spec includes all paths, request/response schemas (auto-generated from your
Resource classes), parameter descriptions, and tags.

---

# Client

## SDK Generation

Generate a client package that knows every type, every operation, every query
parameter:

```bash
./manage.py generate_jsonapi_client articles.views::api --output ~/articles_sdk
```

(`djsonapi` must be in `INSTALLED_APPS`. `articles.views::api` is the import
path to your `DjsonApi` instance.)

The result is a **self-contained Python package** — only dependency is
`aiohttp`. It copies `djsonapi_client` as its `_runtime/` sub-package.

## Usage

```python
from articles_sdk import sdk

async with sdk:
    # IDE completion for everything. Every method, every filter, every field.
    article = await sdk.articles.get(1, include__author=True)
    print(article.title)          # str
    print(article.created_at)     # datetime — auto-converted from ISO string

    await article.save(title="New title")
    await article.delete()
```

### What's happening on the wire?

**`sdk.articles.get(1)`**:

```
GET /api/articles/1 HTTP/1.1
Accept: application/vnd.api+json
```

→ Parses the JSON:API response, creates a typed Resource with attributes
accessible as `article.title`, `article.author` (relationship stubs).

**`article.save(title="New title")`**:

```
PATCH /api/articles/1 HTTP/1.1
Content-Type: application/vnd.api+json
Accept: application/vnd.api+json

{
  "data": {
    "type": "articles",
    "id": "1",
    "attributes": {
      "title": "New title"
    }
  }
}
```

→ Re-parses the response, updates local state.

**`article.delete()`**: `DELETE /api/articles/1` → `204` → sets
`article.id = None`.

### Collections

```python
async with sdk:
    # Returns a lazy Collection — no HTTP request yet
    articles = sdk.articles.list()

    # Conditionally build the query before fetching
    if query:
        articles = articles.filter(title__contains=query)
    if page:
        articles = articles.page(page)
    if sort_by:
        articles = articles.sort(sort_by)

    # Only now fetch — triggers the GET
    for article in await articles:
        print(article.title)
```

`await`ing a collection triggers the fetch and returns the filled collection:

```python
articles = await sdk.articles.list()
# articles is now fetched — can index, slice, iterate
print(articles[0])
```

Trying to access an unfetched collection raises `RuntimeError`:

```python
articles = sdk.articles.list()
print(articles[0])  # RuntimeError: not fetched yet
```

Collections are immutable and chainable — every method returns a new instance:

```python
# Chaining creates new Collection instances without fetching
base = sdk.articles.list()
filtered = base.filter(title__contains="json")
sorted = filtered.sort("-created_at")
paged = sorted.page(2)

# Still no HTTP request until iteration
async for a in paged:
    ...
```

### Pagination iteration

```python
async with sdk:
    col = await sdk.articles.list().page(1)

    if col.has_next():
        next_page = col.get_next()
        async for a in await next_page:
            ...

    # Or iterate ALL pages
    async for page in col.all_pages():
        for article in page:
            print(article.title)

    # Or iterate ALL items across all pages
    async for article in col.all():
        print(article.title)
```

### Relationships

When a resource has a relationship, you access it as a regular attribute.
Whether that attribute is immediately usable depends on whether the
relationship was **included** in the response. If it wasn't, the attribute
is an *unfetched* stub — it only knows its own ID, so accessing its fields
raises an error until you `await` it.

#### Singular relationships (`author`)

```python
async with sdk:
    # ── Without include ──────────────────────────────────────────────
    article = await sdk.articles.get(1)
    # article.relationships["author"] = {"data": {"type": "users", "id": "42"}}
    # article.author → an unfetched User stub (only knows id=42)

    print(article.author.username)
    # ❌ AttributeError — no attributes fetched yet

    await article.author  # GET /api/articles/1/author  (or /users/42)
    # article.author is now a fully-fetched User

    print(article.author.username)  # ✅ "jdoe"

    # ── With include ─────────────────────────────────────────────────
    article = await sdk.articles.get(1, "author")
    # article.author is fully populated from the `included` payload

    print(article.author.username)  # ✅ "jdoe"

    await article.author  # ✅ Harmless — already fetched, does nothing

    await article.author.refetch()
    # ✅ Always hits the network, even if already fetched.
    # Useful if you want to ensure you have the latest data.
```

#### Plural relationships (`categories`)

Plural relationships behave the same way, but return a `Collection`
instead of a single resource. `await`-ing the collection triggers
the fetch from the server.

```python
async with sdk:
    # ── Without include ──────────────────────────────────────────────
    article = await sdk.articles.get(1)
    # article.categories → an unfetched Collection (no data yet)

    categories = await article.categories  # GET /api/articles/1/categories
    # categories is now a fetched Collection[Category]

    for cat in categories:
        print(cat.name)

    # ── With include ─────────────────────────────────────────────────
    article = await sdk.articles.get(1, "categories")
    # article.categories is a pre-populated Collection

    for cat in article.categories:
        print(cat.name)  # ✅  Works immediately

    await article.categories  # ✅ Harmless — already fetched

    await article.categories.refetch()
    # ✅ Always hits the network, replaces in-place.
```

#### Finding a single resource by filter (`find`)

```python
async with sdk:
    user = await sdk.users.find(username="admin")
    # GET /api/users?filter[username]=admin  → asserts exactly 1 result

    # You can also include related resources:
    article = await sdk.articles.find(
        title__contains="django",
        "author", "categories",
    )
    # GET /api/articles?filter[title][contains]=django&include=author,categories
```

#### Mutating relationships

```python
async with sdk:
    article = await sdk.articles.get(1)

    await article.add("categories", 3, 5)
    # POST /api/articles/1/relationship/categories
    # Body: {"data": [{"type": "categories", "id": "3"}, {"type": "categories", "id": "5"}]}

    await article.remove("categories", 3)
    # DELETE /api/articles/1/relationship/categories

    await article.reset("categories", 5, 7)
    # PATCH /api/articles/1/relationship/categories  (replaces all)

    await article.edit("author", 2)
    # PATCH /api/articles/1/relationship/author  (singular, replaces one)

    # After mutation, the local relationship is invalidated.
    # The next `await` fetches fresh data from the server:
    await article.categories  # GET /api/articles/1/categories
```

Only supported operations are available. If you didn't register
`add_to_relationship("articles", "categories")`, calling
`article.add("categories", ...)` raises `AttributeError` **at import time**.

### Error handling

HTTP errors raise typed exceptions:

```python
from articles_sdk.exceptions import NotFound

try:
    article = await sdk.articles.get(999)
except NotFound:
    print("Article not found")
```

| Status | Exception             |
| ------ | --------------------- |
| 400    | `BadRequest`          |
| 401    | `Unauthorized`        |
| 403    | `Forbidden`           |
| 404    | `NotFound`            |
| 405    | `MethodNotAllowed`    |
| 409    | `Conflict`            |
| 422    | `UnprocessableEntity` |
| 429    | `TooManyRequests`     |
| 500    | `InternalServerError` |

Unknown status codes get a dynamic `Http{N}` class.

### Capability gating

The generated SDK reflects exactly what your server supports:

- No `delete()` if you didn't register `@api.delete_one`
- No `create()` if you didn't register `@api.create_one`
- No `add()`/`remove()`/`reset()` on relationships that don't have those
  endpoints
- `sdk.unknown_type` → `AttributeError` (instead of making up URLs and
  getting 404)

This is enforced at the **class level** — capabilities are `frozenset` members
on resource classes, set during SDK generation.

### Type conversions

The SDK reads your resource's type annotations and generates conversion code:

| Python type | JSON:API format          | Client access                         |
| ----------- | ------------------------ | ------------------------------------- |
| `int`       | `"42"`                   | `resource.id → 42`                    |
| `datetime`  | `"2026-07-17T10:00:00Z"` | `resource.created_at → datetime(...)` |
| `date`      | `"2026-07-17"`           | `resource.published_on → date(...)`   |
| `UUID`      | `"abc-123"`              | `resource.uuid → UUID(...)`           |
| `str`       | `"hello"`                | `resource.title → "hello"`            |

Conversions are applied on response hydration and reversed on request
serialization.

### TypeScript SDK

Generate a typed TypeScript SDK instead:

```bash
./manage.py generate_jsonapi_client articles.views::api \
    --output ~/articles_sdk_ts \
    --language typescript
```

The output is a self-contained TypeScript package — the runtime is copied as
`_runtime/`, plus generated `resources.ts`, `sdk.ts`, `index.ts`.

```typescript
import { createSdk } from "./articles_sdk_ts/index.js";

const sdk = createSdk({
  host: "http://localhost:8000/api/",
  headers: async () => ({}),
});

// Typed resource access — full IDE autocomplete
const admin = await sdk.users.find({ username: "admin" });
console.log(admin.username);          // getter → "admin"

const article = await sdk.articles.create({
  title: "Hello from TS!",
  content: "Generated SDK demo",
  author: admin,
});
console.log(article.title);           // getter → "Hello from TS!"

await article.save({ title: "Updated" });
await article.refetch();

// Lazy collection with typed filter/sort
for await (const a of sdk.articles.list().filter({ title__contains: "TS" })) {
  console.log(a.title, a.author);
}

// Relationship methods — typed overloads
const cat = await sdk.categories.create({ name: "TypeScript" });
await article.add("categories", cat);
await article.remove("categories", cat);
await article.delete();
```

---

# Installation

```bash
pip install djsonapi
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "djsonapi",
]
```

---

# Full example

Check out the `examples/` directory for a complete blog application with
articles, users, categories, and all relationship operations. The `demo_sdk/`
directory contains a pre-generated typed client for it.

```bash
cd examples
python manage.py migrate
python manage.py runserver
# Hit http://localhost:8000/api/docs/ for Redoc
```

---

# Requirements

- Python ≥3.13
- Django ≥4.2
- aiohttp ≥3.14.1 (for the client)
- jsonschema ≥4.20 (for request validation)

---

# Wait, there's more

- **JSON Schema validation** — Every request body is validated before your
  handler sees it. Schemas are generated from type annotations and
  `_create_fields`/`_edit_fields`/`_required_create_fields`.
- **Dataclass integration** — `Resource` uses `@dataclass_transform`, so
  subclasses become dataclasses automatically. No `@dataclass` decorator needed.
- **Async-first, sync-welcome** — Handlers can be `async def` or `def`. Sync
  defs are wrapped with `sync_to_async`.
- **Self-contained SDK** — The generated client copies the runtime verbatim.
  Your SDK has zero dependency on `djsonapi` itself. Just `aiohttp`.
