# Error Handling

The library returns JSON:API-compliant error documents for validation failures
and lets you raise typed exceptions in handlers.

## Exception hierarchy

```
DjsonApiException
├── DjsonApiExceptionSingle  (raised directly → single error object)
│   ├── BadRequest           (400)
│   ├── Unauthorized         (401)
│   ├── Forbidden            (403)
│   ├── NotFound             (404)
│   ├── MethodNotAllowed     (405)
│   ├── NotAcceptable        (406)
│   ├── Conflict             (409)
│   ├── TooManyRequests      (429)
│   ├── UnsupportedMediaType (415)
│   └── InternalServerError  (500)
└── DjsonApiExceptionMulti   (raised → multiple error objects)
```

### Raising exceptions in handlers

```python
from djsonapi.exceptions import NotFound, Conflict

@api.get_one("articles", errors=(NotFound,))
def get_article(request, article_id: int) -> ArticleResource:
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        raise NotFound(f"Article with id '{article_id}' not found")
    return ArticleResource.from_model(article)
```

The `errors=(NotFound,)` decorator parameter declares which exceptions the
endpoint can raise — these become documented error responses in the OpenAPI
spec.

### Multiple errors

Raise `DjsonApiExceptionMulti` to return multiple error objects:

```python
from djsonapi.exceptions import DjsonApiExceptionMulti, NotFound, Conflict

def validate_article(data):
    errors = []
    if not data.get("title"):
        errors.append(BadRequest("Title is required"))
    if not data.get("content"):
        errors.append(BadRequest("Content is required"))
    if errors:
        raise DjsonApiExceptionMulti(*errors)
```

```json
{
  "errors": [
    { "status": "400", "title": "Bad Request", "detail": "Title is required" },
    { "status": "400", "title": "Bad Request", "detail": "Content is required" }
  ]
}
```

### Custom exceptions

Subclass `DjsonApiExceptionSingle` to define custom errors:

```python
from djsonapi.exceptions import DjsonApiExceptionSingle

class PaymentRequired(DjsonApiExceptionSingle):
    STATUS = 402
```

The class name is converted to a title: `PaymentRequired` → `"Payment Required"`.

## Error document shape

Single error:

```json
{
  "errors": [{
    "status": "400",
    "title": "Bad Request",
    "detail": "Payload must have a 'data' key"
  }]
}
```

Multiple errors (validation):

```json
{
  "errors": [
    {
      "status": "400",
      "title": "Bad Request",
      "detail": "'title' is a required property",
      "source": { "pointer": "/data/attributes" }
    },
    {
      "status": "400",
      "title": "Bad Request",
      "detail": "'author' is not a valid relationship",
      "source": { "pointer": "/data/relationships" }
    }
  ]
}
```

### Error sources

- `source.pointer` — JSON Pointer to the offending field in the request body
- `source.parameter` — name of the offending query parameter

## Auto-generated errors

The library generates error responses automatically for:

- Invalid Content-Type → `415 Unsupported Media Type`
- Invalid Accept header → `406 Not Acceptable`
- Invalid JSON body → `400 Bad Request`
- Schema validation failure → `400 Bad Request`
- Unknown query parameters → `400 Bad Request`
- Invalid path → `404 Not Found`
- Unregistered HTTP method → `405 Method Not Allowed`
