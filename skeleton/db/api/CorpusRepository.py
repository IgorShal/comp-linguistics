from typing import Dict, Any

from db.models import Corpus, Text


class CorpusRepository:
    def collect_text(self, t: Text) -> Dict[str, Any]:
        return {
            'id': t.pk,
            'title': t.title,
            'description': t.description,
            'text': t.text,
        }

    def collect_corpus(self, c: Corpus) -> Dict[str, Any]:
        return {
            'id': c.pk,
            'name': c.name,
            'description': c.description,
            'genre': c.genre,
            'texts': [self.collect_text(t) for t in c.texts.all()]
        }

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        c = Corpus.objects.create(
            name=data.get('name', ''),
            description=data.get('description'),
            genre=data.get('genre'),
        )
        return self.collect_corpus(c)

    def update(self, corpus_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        c = Corpus.objects.get(pk=corpus_id)
        c.name = data.get('name', '')
        c.description = data.get('description', '')
        c.genre = data.get('genre', '')
        c.save()
        return self.collect_corpus(c)

    def get(self, corpus_id: int) -> Dict[str, Any]:
        c = Corpus.objects.get(pk=corpus_id)
        return self.collect_corpus(c)

    def delete(self, corpus_id: int) -> int:
        c = Corpus.objects.get(pk=corpus_id)
        c.delete()
        return corpus_id


