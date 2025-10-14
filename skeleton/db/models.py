from django.db import models
from db_file_storage.model_utils import delete_file, delete_file_if_needed


class Test(models.Model):
    name = models.TextField()

    def __str__(self):
        return self.name  # Returns the value of the 'name' field
    
class Corpus(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    genre = models.CharField(max_length=128, blank=True, null=True)

    def __str__(self):
        return self.name


class Text(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    text = models.TextField()
    corpus = models.ForeignKey(Corpus, on_delete=models.CASCADE, related_name='texts')

    has_translation = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='is_translation_of')
    # Embedding vector (stored as JSON string, compatible with Django 3.0)
    embedding = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.title
