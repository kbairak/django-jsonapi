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
