# OpenAPI & Redoc

Every `DjsonApi` instance automatically generates an OpenAPI 3.0.3 specification
and serves interactive documentation via Redoc.

## Endpoints

| URL | Description |
|-----|-------------|
| `/api/openapi.json` | Raw OpenAPI specification |
| `/api/docs/` | Redoc interactive docs |

## What's generated

The spec includes:

- All registered endpoints with their paths, methods, and URL parameters
- Request body schemas for POST/PATCH endpoints (from `jsonschema_create` /
  `jsonschema_edit`)
- Response schemas for all endpoints (from `jsonschema_read`)
- Query parameter descriptions with types, defaults, and allowed values
- Sparse field parameters with available field names in the description
- Include parameter with allowed values
- Error responses for declared exception types (via `errors=(NotFound,)`)
- Tags grouping endpoints by resource type

### Schema generation

Schemas are built from your Resource class annotations:

```python
class ArticleResource(Resource):
    id: int
    title: str                           # → {"type": "string"}
    created_at: datetime                 # → {"type": "string", "format": "date-time"}
    score: Annotated[int, {"minimum": 0, "maximum": 100}]  # → extra props merged
```

### Tagging

Endpoints are tagged by `_type`. All `articles` endpoints appear under an
"articles" group.

## Serving

No additional setup. Just include `api.urls` in your URLconf:

```python
urlpatterns = [
    path("api/", api.urls),  # GET /api/openapi.json, GET /api/docs/
]
```

<!-- SCREENSHOT: browser showing Redoc at /api/docs/ with sidebar of endpoints grouped by resource type -->
