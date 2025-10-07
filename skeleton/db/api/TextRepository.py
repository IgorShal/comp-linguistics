from typing import Dict, Any

from db.models import Text, Corpus


class TextRepository:
    def collect_text(self, t: Text) -> Dict[str, Any]:
        return {
            'id': t.pk,
            'title': t.title,
            'description': t.description,
            'text': t.text,
            'corpus_id': t.corpus_id,
            'has_translation_ids': list(t.has_translation.values_list('id', flat=True)),
        }

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        corpus_id = data.get('corpus_id')
        corpus = Corpus.objects.get(pk=corpus_id)
        t = Text.objects.create(
            title=data.get('title', ''),
            description=data.get('description'),
            text=data.get('text', ''),
            corpus=corpus,
        )
        # handle translations
        translations = data.get('has_translation_ids') or []
        if translations:
            t.has_translation.set(Text.objects.filter(pk__in=translations))
        return self.collect_text(t)

    def update(self, text_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        t = Text.objects.get(pk=text_id)
        t.title = data.get('title', t.title)
        t.description = data.get('description', t.description)
        t.text = data.get('text', t.text)
        t.corpus = Corpus.objects.get(pk=data.get('corpus_id', t.corpus_id))
        t.save()
        t.has_translation.set(
            Text.objects.filter(
                pk__in=(data.get('has_translation_ids', list(t.has_translation.values_list('id', flat=True))))
            )
        )
        return self.collect_text(t)

    def get(self, text_id: int) -> Dict[str, Any]:
        t = Text.objects.get(pk=text_id)
        return self.collect_text(t)

    def delete(self, text_id: int) -> int:
        t = Text.objects.get(pk=text_id)
        t.delete()
        return text_id


