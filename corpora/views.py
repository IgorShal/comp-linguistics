from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Corpus, Text
from .serializers import CorpusSerializer, TextSerializer


class CorpusViewSet(viewsets.ModelViewSet):
    queryset = Corpus.objects.all().prefetch_related('texts')
    serializer_class = CorpusSerializer

    @action(detail=True, methods=['get'])
    def collect_corpus(self, request, pk=None):
        corpus = self.get_object()
        serializer = self.get_serializer(corpus)
        return Response(serializer.data)


class TextViewSet(viewsets.ModelViewSet):
    queryset = Text.objects.all()
    serializer_class = TextSerializer


