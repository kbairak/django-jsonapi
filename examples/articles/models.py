import datetime

from django.contrib.auth.models import User
from django.db import models


class Category(models.Model):
    id: int
    name: str = models.CharField(max_length=100)  # pyright: ignore
    slug: str = models.SlugField(unique=True)  # pyright: ignore
    description: str = models.TextField(blank=True, default="")  # pyright: ignore
    created_at: datetime.datetime = models.DateTimeField(auto_now_add=True)  # pyright: ignore
    articles: models.Manager["Article"]

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Article(models.Model):
    id: int
    author_id: int
    title: str = models.CharField(max_length=200)  # pyright: ignore
    content: str = models.TextField()  # pyright: ignore
    author: User = models.ForeignKey(User, on_delete=models.CASCADE, related_name="articles")  # pyright: ignore
    categories: models.Manager[Category] = models.ManyToManyField(
        Category, related_name="articles"
    )  # pyright: ignore  # noqa: E501
    created_at: datetime.datetime = models.DateTimeField(auto_now_add=True)  # pyright: ignore

    def __str__(self):
        return self.title
