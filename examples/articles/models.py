from django.contrib.auth.models import User
from django.db import models


class Category(models.Model):
    id: int
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Article(models.Model):
    id: int
    author_id: int
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="articles")
    categories = models.ManyToManyField(Category, related_name="articles")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
