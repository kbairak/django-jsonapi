from django.contrib.auth.models import User
from django.db import models


class Article(models.Model):
    id: int
    author_id: int
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="articles")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
