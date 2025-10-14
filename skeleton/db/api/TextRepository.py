from typing import Dict, Any
import json

from db.models import Text, Corpus
from db.api.EmbeddingsGenerator import EmbeddingsGenerator


class TextRepository:
    def __init__(self):
        self.embeddings_gen = EmbeddingsGenerator()

    def collect_text(self, t: Text) -> Dict[str, Any]:
        embedding = None
        if t.embedding:
            try:
                embedding = json.loads(t.embedding)
            except (json.JSONDecodeError, TypeError):
                embedding = None
        
        return {
            'id': t.pk,
            'title': t.title,
            'description': t.description,
            'text': t.text,
            'corpus_id': t.corpus_id,
            'has_translation_ids': list(t.has_translation.values_list('id', flat=True)),
            'embedding': embedding,
        }

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        corpus_id = data.get('corpus_id')
        corpus = Corpus.objects.get(pk=corpus_id)
        text_content = data.get('text', '')
        
        # Generate embedding
        embedding = None
        if text_content:
            embedding_vector = self.embeddings_gen.get_text_embedding(text_content)
            embedding = json.dumps(embedding_vector.tolist())
        
        t = Text.objects.create(
            title=data.get('title', ''),
            description=data.get('description'),
            text=text_content,
            corpus=corpus,
            embedding=embedding,
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
        
        # Update text and recalculate embedding if text changed
        if 'text' in data:
            new_text = data['text']
            if new_text != t.text:
                t.text = new_text
                if new_text:
                    embedding_vector = self.embeddings_gen.get_text_embedding(new_text)
                    t.embedding = json.dumps(embedding_vector.tolist())
                else:
                    t.embedding = None
        
        if 'corpus_id' in data:
            t.corpus = Corpus.objects.get(pk=data['corpus_id'])
        
        t.save()
        
        if 'has_translation_ids' in data:
            t.has_translation.set(
                Text.objects.filter(pk__in=data['has_translation_ids'])
            )
        
        return self.collect_text(t)

    def get(self, text_id: int) -> Dict[str, Any]:
        t = Text.objects.get(pk=text_id)
        return self.collect_text(t)

    def delete(self, text_id: int) -> int:
        t = Text.objects.get(pk=text_id)
        t.delete()
        return text_id

    def find_similar(self, text_id: int, limit: int = 5) -> Dict[str, Any]:
        """Find texts similar to the given text by embedding similarity."""
        import numpy as np
        
        source_text = Text.objects.get(pk=text_id)
        if not source_text.embedding:
            return {'error': 'Source text has no embedding'}
        
        try:
            source_embedding = np.array(json.loads(source_text.embedding))
        except (json.JSONDecodeError, TypeError):
            return {'error': 'Invalid embedding format'}
        
        # Get all texts with embeddings (excluding source)
        all_texts = Text.objects.exclude(pk=text_id).exclude(embedding__isnull=True).exclude(embedding='')
        
        similarities = []
        for t in all_texts:
            try:
                target_embedding = np.array(json.loads(t.embedding))
                similarity = self.embeddings_gen.cos_compare(source_embedding, target_embedding)
                similarities.append({
                    'text': self.collect_text(t),
                    'similarity': float(similarity)
                })
            except (json.JSONDecodeError, TypeError):
                continue
        
        # Sort by similarity (descending) and limit
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        return {
            'source_text_id': text_id,
            'similar_texts': similarities[:limit]
        }

    def search_by_text(self, query_text: str, limit: int = 5) -> Dict[str, Any]:
        """Search texts by semantic similarity to query text."""
        import numpy as np
        
        if not query_text:
            return {'error': 'Query text is empty'}
        
        # Generate embedding for query
        query_embedding = self.embeddings_gen.get_text_embedding(query_text)
        
        # Get all texts with embeddings
        all_texts = Text.objects.exclude(embedding__isnull=True).exclude(embedding='')
        
        similarities = []
        for t in all_texts:
            try:
                target_embedding = np.array(json.loads(t.embedding))
                similarity = self.embeddings_gen.cos_compare(query_embedding, target_embedding)
                similarities.append({
                    'text': self.collect_text(t),
                    'similarity': float(similarity)
                })
            except (json.JSONDecodeError, TypeError):
                continue
        
        # Sort by similarity (descending) and limit
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        return {
            'query': query_text,
            'results': similarities[:limit]
        }


