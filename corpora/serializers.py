from rest_framework import serializers

from .models import Corpus, Text


class TextSerializer(serializers.ModelSerializer):
    class Meta:
        model = Text
        fields = ['id', 'title', 'description', 'body', 'corpus', 'has_translation']


class CorpusSerializer(serializers.ModelSerializer):
    texts = TextSerializer(many=True, read_only=True)

    class Meta:
        model = Corpus
        fields = ['id', 'title', 'description', 'genre', 'texts']


