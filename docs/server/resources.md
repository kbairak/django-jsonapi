# Resources

`Resource` is the base class for all your API entities. Subclasses behave like
dataclasses and get serialization, schema generation, and payload parsing for
free.

## Minimal subclass

```python
from djsonapi import Resource
from typing import ClassVar

class ArticleResource(Resource):
    _type: ClassVar = "articles"
    _attributes: ClassVar = ["title", "content", "created_at"]
    _singular_relationships: ClassVar = [("author", "users")]
    _plural_relationships: ClassVar = ["categories"]
    _create_fields: ClassVar = ["title", "content", "author", "categories"]
    _required_create_fields: ClassVar = ["title", "content"]
    _edit_fields: ClassVar = ["title", "content", "author"]

    id: int
    title: str
    content: str
    created_at: datetime
    author: int
    categories: list[int] | None = None
```

## Interacting with Resources

Resources instantiate like dataclasses — `__init__` is auto-generated from type
annotations:

```python
article = ArticleResource(
    id=1,
    title="Hello",
    content="...",
    created_at=datetime.now(),
    author=42,
    categories=[1, 3],
)
```

Read and write attributes directly:

```python
article.title            # "Hello"
article.title = "Updated"
article.author           # 42 (foreign key ID)
```

Relationships are stored as raw IDs (or lists of IDs) on the server side:

```python
article.author = 7       # change author relationship
```

## What these 15 lines give you

The Resource subclass alone is enough to generate a full JSON:API schema.

Call `jsonschema_read()` to see it:

```python
import json
print(json.dumps(ArticleResource.jsonschema_read(), indent=2))
```

```json
{
  "type": "object",
  "properties": {
    "type": { "const": "articles" },
    "id": { "type": "integer" },
    "attributes": {
      "type": "object",
      "properties": {
        "title": { "type": "string" },
        "content": { "type": "string" },
        "created_at": { "type": "string", "format": "date-time" }
      },
      "required": ["title", "content", "created_at"],
      "additionalProperties": false
    },
    "relationships": {
      "type": "object",
      "properties": {
        "author": { "type": "object", ... },
        "categories": { "type": "object", ... }
      },
      "required": ["author", "categories"],
      "additionalProperties": false
    }
  },
  "required": ["type", "id", "attributes", "relationships"],
  "additionalProperties": false
}
```

This schema powers request validation, OpenAPI generation, and SDK type
conversions.

## `UNSET` sentinel

`Resource.UNSET` (also exported at module level as `UNSET`) indicates a field
was not provided in a request. Critical for PATCH handlers:

```python
@api.edit_one("articles")
def edit_article(request, article_id: int, payload: ArticleResource) -> ArticleResource:
    article = Article.objects.get(id=article_id)
    if payload.title is not ArticleResource.UNSET:
        article.title = payload.title
    if payload.content is not ArticleResource.UNSET:
        article.content = payload.content
    article.save()
    return ArticleResource.from_model(article)
```

Without the `UNSET` check, there's no way to distinguish "client didn't send
this field" from "client sent `null`".

### `as_create_payload` / `as_edit_payload`

Filter a Resource's fields to only those allowed by `_create_fields` /
`_edit_fields`, excluding anything still set to `UNSET`:

```python
resource = ArticleResource._from_jsonapi_payload(
    body, fields=ArticleResource._create_fields
)
Article.objects.create(**resource.as_create_payload())
```

```python
payload = ArticleResource._from_jsonapi_payload(body, fields=ArticleResource._edit_fields)
for key, value in payload.as_edit_payload().items():
    setattr(article, key, value)
```

## ClassVars

All configuration is done via `ClassVar` annotations on the class.

| ClassVar | Type | Purpose |
|----------|------|---------|
| `_type` | `str` | JSON:API `type` value |
| `_attributes` | `list[str]` | Field names exposed as attributes |
| `_singular_relationships` | `list[str \| tuple[str, str]]` | To-one relationships |
| `_plural_relationships` | `list[str \| tuple[str, str]]` | To-many relationships |
| `_create_fields` | `list[str]` | Fields accepted in POST |
| `_required_create_fields` | `list[str]` | Fields required in POST |
| `_edit_fields` | `list[str]` | Fields accepted in PATCH |
| `_read_fields` | `list[str]` | Fields included in responses (empty = all) |

### Write-only fields

By default, all fields in `_attributes` and all relationships appear in
responses. To exclude sensitive fields (e.g. password hashes, internal flags),
set `_read_fields`:

```python
class User(Resource):
    _type: ClassVar = "users"
    _attributes: ClassVar = ["username", "password_hash"]
    _create_fields: ClassVar = ["username", "password_hash"]
    _edit_fields: ClassVar = ["password_hash"]
    _read_fields: ClassVar = ["username"]  # password_hash excluded from responses

    id: int
    username: str
    password_hash: str
```

When `_read_fields` is set, `serialize()` and `jsonschema_read()` only include
the listed fields. Create and edit are unaffected — `password_hash` is still
accepted in POST/PATCH, just never returned.

When `_read_fields` is empty (default), all `_attributes` and relationships are
readable. This maintains backward compatibility.

### Relationship shorthands

```python
# str — field name and JSON:API type are the same
_singular_relationships: ClassVar = ["author"]
# equivalent to: ("author", "author")

# tuple — (field_name, jsonapi_type)
_singular_relationships: ClassVar = [("author", "users")]
```

String form when field name matches the JSON:API type. Tuple form when they
diverge (e.g., `author` field → `users` type).

## Type conversions

Server-side type annotations drive both JSON Schema generation and wire-format
conversion:

| Python type | JSON:API format | Converted |
|-------------|----------------|-----------|
| `int` | `"42"` | `42` |
| `float` | `"3.14"` | `3.14` |
| `str` | `"hello"` | `"hello"` |
| `bool` | `true` | `True` |
| `datetime` | `"2026-07-17T10:00:00Z"` | `datetime(...)` |
| `date` | `"2026-07-17"` | `date(...)` |
| `UUID` | `"abc-123"` | `UUID(...)` |
| `list[int]` | `["1", "2"]` | `[1, 2]` |

## Internals (you probably won't need these)

### `serialize()`

Produces the JSON:API wire representation. Called internally by the framework
when building responses:

```python
resource.serialize()
# {"type": "articles", "id": "1", "attributes": {...}, "relationships": {...}}
```

### `_from_jsonapi_payload()`

Parses a JSON:API request body back into a Resource instance. The decorators
call this before passing the payload to your handler:

```python
body = {"data": {"type": "articles", "attributes": {"title": "New"}}}
resource = ArticleResource._from_jsonapi_payload(body, fields=["title"])
resource.title  # "New"
```

### `meta` field

Every Resource can carry a `meta` dict, serialized at the resource level:

```python
resource.meta = {"computed": 42}
```

### Factory pattern

The `from_model` pattern in examples is not built-in — write it yourself:

```python
@classmethod
def from_model(cls, article) -> Self:
    return cls(
        id=article.id,
        title=article.title,
        content=article.content,
        created_at=article.created_at,
        author=article.author_id,
    )
```
