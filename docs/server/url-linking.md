# URL Linking

djsonapi automatically populates `links` objects in serialized responses. No
manual URL construction.

## How links grow with your API

Start with a basic resource endpoint:

```python
@api.get_one("articles")
def get_article(request, article_id: int) -> ArticleResource:
    return ArticleResource.from_model(Article.objects.get(id=article_id))
```

Response:

```json
{
  "data": {
    "type": "articles",
    "id": "1",
    "links": {
      "self": "/api/articles/1"
    },
    "relationships": {
      "author": {
        "data": { "type": "users", "id": "42" }
      }
    }
  }
}
```

Relationship `links` are absent because no relationship endpoints are
registered yet. Add them:

```python
@api.get_one("articles")
def get_article(request, article_id: int) -> ArticleResource:
    return ArticleResource.from_model(Article.objects.get(id=article_id))

@api.get_related("articles", "author")
def get_article_author(request, article_id: int) -> UserResource: ...

@api.edit_relationship("articles", "author")
def edit_article_author(request, article_id: int, new_author_id: int) -> None: ...
```

Now the same response includes relationship links:

```json
{
  "data": {
    "type": "articles",
    "id": "1",
    "links": {
      "self": "/api/articles/1"
    },
    "relationships": {
      "author": {
        "data": { "type": "users", "id": "42" },
        "links": {
          "self": "/api/articles/1/relationship/author",
          "related": "/api/articles/1/author"
        }
      }
    }
  }
}
```

No manual link-building. The library walks registered URL patterns and
populates links based on which endpoints exist.

## How it works

During serialization, `Resource.serialize()` calls `reverse()` for each
relationship:

- URL name `{type}__{rel}__related` → `related` link
- URL name `{type}__{rel}__relationship` → `self` link

If `reverse()` succeeds, the link appears. Otherwise it's omitted.

### Auto-derivation

Registering only `get_related` is enough to get both links. The library
auto-creates a `GetRelationshipEndpoint` that calls your `get_related` handler
and strips the response to identifiers only.

## Top-level links

The response `links` object contains `self` pointing to the request URL:

```json
{
  "links": {
    "self": "/api/articles?filter[author]=42"
  }
}
```

### Pagination links

Return a `Response` with custom link parameters:

```python
@api.get_many("articles")
def list_articles(request, page: int = 1) -> Response[list[ArticleResource]]:
    ...
    return Response(
        data=[ArticleResource.from_model(a) for a in page_qs],
        links={
            "next": {"page": str(page + 1)},
            "prev": {"page": str(page - 1)},
            "first": {"page": "1"},
        },
    )
```

Each link value merges with current query parameters and resolves to a full
URL. If the request was `/api/articles?filter[author]=42&page=2`, the above
produces:

```json
{
  "links": {
    "self": "/api/articles?filter[author]=42&page=2",
    "next": "/api/articles?filter[author]=42&page=3",
    "prev": "/api/articles?filter[author]=42&page=1",
    "first": "/api/articles?filter[author]=42&page=1"
  }
}
```

This works with paginated collections in the generated SDK — `has_next()` /
`get_next()` operate on these links.

## URL name reference

| Pattern | Endpoints | Example |
|---------|-----------|---------|
| `{type}__item` | get_one, edit_one, delete_one | `articles__item` |
| `{type}__collection` | get_many, create_one | `articles__collection` |
| `{type}__{rel}__related` | get_related | `articles__author__related` |
| `{type}__{rel}__relationship` | get_relationship, edit, reset, add, remove | `articles__author__relationship` |
| `openapi` | built-in | `openapi` |
| `docs` | built-in | `docs` |
