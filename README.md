# djsonapi

[JSON:API](https://jsonapi.org/) framework for Django.

```python
from djsonapi import DjsonApi, Resource

api = DjsonApi()


class ArticleResource(Resource):
    _type: ClassVar = "articles"
    _attributes: ClassVar = ["title", "content", "created_at"]
    _singular_relationships: ClassVar = [("author", "users")]

    id: int
    title: str
    content: str
    created_at: datetime.datetime
    author: int


class UserResource(Resource):
    _type: ClassVar = "users"
    _attributes: ClassVar = ["username", "email"]

    id: int
    username: str
    email: str


@api.get_one("articles")
def get_article(request: HttpRequest, article_id: int) -> ArticleResource:
    article = Article.objects.get(id=article_id)
    return ArticleResource(
        id=article.id,
        title=article.title,
        content=article.content,
        created_at=article.created_at,
        author=article.author_id,
    )


@api.get_many("articles")
def list_articles(request: HttpRequest) -> list[ArticleResource]:
    return [ArticleResource(...) for article in Article.objects.all()]
```

## TODO

- [x] `create_one` — `POST /articles`
- [x] ReDoc docs UI at `/docs`
- [x] Filters and other GET variables (for get_many)
- [x] `edit_one` — `PATCH /articles/:id`
- [x] `delete_one` — `DELETE /articles/:id`
- [x] `get_relationship` (singular) — `GET /articles/:id/relationships/author`
- [x] `get_relationship` (plural) — `GET /articles/:id/relationships/tags`
- [x] `edit_relationship` (singular) — `PATCH /articles/:id/relationships/author`
- [x] `add_to_relationship` (plural) — `POST /articles/:id/relationships/tags`
- [x] `remove_from_relationship` (plural) — `DELETE /articles/:id/relationships/tags`
- [x] `reset_relationship` (plural) — `PATCH /articles/:id/relationships/tags`
- [x] Compound documents (`include` param + `included` field in response)
- [x] Sparse fieldsets (`fields[type]=...`)
- [x] Sorting (`sort=...`)
- [ ] Pagination (for get_many)
- [ ] Mapping `/articles?filter[author]=...` to related resource URL
- [ ] Error responses in the openapi spec
- [ ] Authentication
