from django.db import models


class Corpus(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    genre = models.CharField(max_length=120, blank=True)

    def __str__(self) -> str:
        return self.title


class Text(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    body = models.TextField()
    corpus = models.ForeignKey(Corpus, on_delete=models.CASCADE, related_name='texts')
    has_translation = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='translations')

    def __str__(self) -> str:
        return self.title


