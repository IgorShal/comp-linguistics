from django.contrib import admin

from django.db import models
from .models import Test, Corpus, Text


class TestAdmin(admin.ModelAdmin):
    model = Test

admin.site.register(Test, TestAdmin)
@admin.register(Corpus)
class CorpusAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "genre")
    search_fields = ("name", "genre")

@admin.register(Text)
class TextAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "corpus")
    search_fields = ("title",)
    list_filter = ("corpus",)