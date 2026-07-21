# Validation & Schemas

Every request body is validated against an auto-generated JSON Schema before
your handler sees it.

## Auto-generated schemas

Each Resource subclass produces three schemas:

| Schema | Method | Used by |
|--------|--------|---------|
| Read schema | `jsonschema_read()` | GET responses, OpenAPI spec |
| Create schema | `jsonschema_create()` | POST request validation |
| Edit schema | `jsonschema_edit()` | PATCH request validation |

### Create schema

Based on `_create_fields` and `_required_create_fields`:

```python
class ArticleResource(Resource):
    _create_fields = ["title", "content", "author", "categories"]
    _required_create_fields = ["title", "content"]
```

Produces a schema requiring `type: "articles"`, an `attributes` object with
`title` and `content` required, and optional `relationships` for `author` and
`categories`.

### Edit schema

Based on `_edit_fields`. Requires `type` and `id`. At least one of
`attributes` or `relationships` must be present (`minProperties: 3` counting
`type` and `id`).

### Read schema

Includes all `_attributes` and all relationships. Used for serialization
validation and OpenAPI response schemas.

## Validation flow

```
Request body → JSON parse → Schema validate → _from_jsonapi_payload → handler
```

1. **Content-Type** must be `application/vnd.api+json` (writes only)
2. **Accept** header must allow `application/vnd.api+json`
3. **JSON parse** — invalid JSON → `400 Bad Request`
4. **Schema validate** — wrong types, missing fields, extra keys → `400 Bad Request`
   with JSON:API error source pointers
5. **Payload extraction** — only declared `_create_fields` / `_edit_fields` are
   extracted, unknown fields are silently dropped

### Error source pointers

Validation errors include `source.pointer` following JSON Pointer (RFC 6901):

```json
{
  "errors": [{
    "status": "400",
    "title": "Bad Request",
    "detail": "'foo' is not of type 'integer'",
    "source": { "pointer": "/data/attributes/title" }
  }]
}
```

## Schema customization with `Annotated`

Use `Annotated` with a dict to add extra JSON Schema properties:

```python
from typing import Annotated

class ArticleResource(Resource):
    title: Annotated[str, {"description": "The article title", "maxLength": 200}]
    score: Annotated[int, {"minimum": 0, "maximum": 100}] = 50
```

The dict is merged into the generated schema for that field. This is forwarded
to OpenAPI as well.
