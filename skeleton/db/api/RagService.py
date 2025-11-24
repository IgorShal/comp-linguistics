import json
import logging
import os
from typing import List, Dict, Any, Optional

from gigachat import GigaChat
from gigachat.models import Chat

from db.api.TextRepository import TextRepository
from db.api.OntologyRepository import OntologyRepository
from db.api.EmbeddingsGenerator import EmbeddingsGenerator


logger = logging.getLogger(__name__)


class RagService:
    """RAG service that performs two-stage retrieval (N then M) using embeddings from Text (Django) and
    Ontology (Neo4j). Works with existing repositories and with embeddings stored in nodes/texts.

    Requirements / assumptions:
      - EmbeddingsGenerator.get_text_embedding(text) -> numpy array-like
      - OntologyRepository should ideally implement get_nodes_with_embeddings() and/or search_nodes_by_embedding()
      - Text model stores embedding as JSON string in Text.embedding (as in your project)
      - Gigachat client exposes generate_answer_by_messages(messages)
    """

    def __init__(self):
        self.text_repo = TextRepository()
        self.onto_repo = OntologyRepository()
        self.emb_gen = EmbeddingsGenerator()
        self.gigachat = GigaChat(credentials=os.getenv('GIGACHAT_CREDENTIALS'))

    def generate_answer_by_messages(self, messages: list):
        chat = Chat(messages=messages, model="GigaChat", )

        answer = self.gigachat.chat(chat)
        choice = answer.choices[0]
        content = choice.message.content
        content = content.replace("'", '"')
        content = content.strip()
        logger.info(content)
        print(content)
        return content
    def _collect_text_candidates(self) -> List[Dict[str, Any]]:
        """Collect all Text rows that have embeddings into candidate dicts.
        Each candidate: {'type':'text','id': id, 'title': title, 'text': text, 'embedding': list}
        """
        candidates = []
        try:
            from db.models import Text
            texts = Text.objects.exclude(embedding__isnull=True).exclude(embedding='')
            for t in texts:
                try:
                    emb = json.loads(t.embedding)
                except Exception:
                    continue
                candidates.append({
                    'type': 'text',
                    'id': t.pk,
                    'title': t.title,
                    'text': t.text,
                    'embedding': emb,
                })
        except Exception as e:
            logger.exception("Failed to collect text candidates: %s", e)
        return candidates

    def _collect_ontology_candidates(self) -> List[Dict[str, Any]]:
        """Collect ontology nodes as candidates. Prefer repository method get_nodes_with_embeddings if present.
        Candidate: {'type':'node','id': uri, 'title': title, 'text': fragment, 'embedding': list}
        """
        candidates = []
        try:
            # If repo provides helper that already returned nodes with embedding, use it
            if hasattr(self.onto_repo, 'get_nodes_with_embeddings'):
                nodes = self.onto_repo.get_nodes_with_embeddings()
                for n in nodes:
                    # try to get fragment if exists, otherwise build it on-the-fly
                    fragment = None
                    if isinstance(n, dict):
                        fragment = n.get('fragment') or n.get('signature') or None
                    if not fragment and hasattr(self.onto_repo, 'collect_fragment_for_node'):
                        fragment = self.onto_repo.collect_fragment_for_node(n.get('uri')) if n.get('uri') else None
                    candidates.append({
                        'type': 'node',
                        'id': n.get('uri') if isinstance(n, dict) else getattr(n, 'uri', None),
                        'title': n.get('title') if isinstance(n, dict) else None,
                        'text': fragment or n.get('description') if isinstance(n, dict) else None,
                        'embedding': n.get('embedding') if isinstance(n, dict) else None,
                    })
            else:
                # fallback: iterate over all nodes and try to read embedding prop
                nodes = self.onto_repo.get_all_nodes()
                for n in nodes:
                    emb = n.get('embedding')
                    fragment = None
                    if hasattr(self.onto_repo, 'collect_fragment_for_node'):
                        fragment = self.onto_repo.collect_fragment_for_node(n.get('uri'))
                    candidates.append({
                        'type': 'node',
                        'id': n.get('uri'),
                        'title': n.get('title'),
                        'text': fragment or n.get('description'),
                        'embedding': emb,
                    })
        except Exception as e:
            logger.exception("Failed to collect ontology candidates: %s", e)
        return candidates

    def _score_and_select(self, query_embedding, candidates: List[Dict[str, Any]], limit: int):
        """Score candidates by cosine similarity and return top-`limit` list with 'similarity' keys.
        If candidate embedding missing, it will be skipped.
        """
        import numpy as np
        scored = []
        try:
            qemb = np.array(list(map(float, query_embedding)))
        except Exception:
            qemb = None

        for c in candidates:
            emb = c.get('embedding')
            if emb is None or qemb is None:
                continue
            try:
                emb_arr = np.array(list(map(float, emb)))
                denom = (np.linalg.norm(qemb) * np.linalg.norm(emb_arr))
                sim = 0.0
                if denom != 0:
                    sim = float(np.dot(qemb, emb_arr) / denom)
                entry = dict(c)
                entry['similarity'] = sim
                scored.append(entry)
            except Exception:
                continue
        scored.sort(key=lambda x: x.get('similarity', 0), reverse=True)
        return scored[:limit]

    def _make_prompt(self, query: str, contexts: List[Dict[str, Any]], max_chars: int = 4000) -> List[Dict[str, str]]:
        """Construct messages array for gigachat. Trims contexts to max_chars total.
        Returns messages list suitable for gigachat.generate_answer_by_messages
        """
        system_msg = {
            "role": "system",
            "content": "You are an assistant. Use only the provided context to answer the question. If info missing, say you don't know."
        }

        # prepare context block; keep best-first order
        ctx_texts = []
        total = 0
        for c in contexts:
            header = f"[{c.get('type')}:{c.get('id')}] {c.get('title') or ''} (sim={c.get('similarity', 0):.3f})\n"
            body = c.get('text') or ''
            piece = header + body + "\n\n"
            if total + len(piece) > max_chars:
                # try to fit partial body if possible
                remaining = max_chars - total - len(header) - 10
                if remaining > 50:
                    piece = header + (body[:remaining] + "...\n\n")
                    ctx_texts.append(piece)
                    total += len(piece)
                break
            ctx_texts.append(piece)
            total += len(piece)

        contexts_block = "".join(ctx_texts)

        user_content = f"""Дай ответ на вопрос, используя только информацию из текста ниже. Если ответ нельзя дать однозначно — укажи это.
Вопрос:
{query}

Контекст (релевантные фрагменты):
{contexts_block}

Если нужно — кратко укажи, какие фрагменты использовались для ответа."""

        user_msg = {"role": "user", "content": user_content}
        return [system_msg, user_msg]

    # ----------------- main RAG flow -----------------
    def rag_query(self, query: str, top_n: int = 5, top_m: int = 5) -> Dict[str, Any]:
        """Main two-stage RAG query. Returns dict with intermediate and final answers and used contexts."""
        try:
            # 1) compute query embedding
            query_emb = self.emb_gen.get_text_embedding(query)

            # 2) collect candidates (texts + ontology)
            candidates = []
            candidates.extend(self._collect_text_candidates())
            candidates.extend(self._collect_ontology_candidates())

            # 3) primary retrieval (top_n)
            top_n_list = self._score_and_select(query_emb, candidates, top_n)

            # 4) first-generation
            messages_1 = self._make_prompt(query, top_n_list)
            try:
                answer_1 = self.generate_answer_by_messages(messages_1)
            except Exception:
                # older gigachat client signature might expect list of messages inside another list
                try:
                    answer_1 = self.generate_answer_by_messages([messages_1[0], messages_1[1]])
                except Exception as e:
                    logger.exception("gigachat call failed: %s", e)
                    answer_1 = ""

            if isinstance(answer_1, dict):
                answer_text_1 = answer_1.get('content') or str(answer_1)
            else:
                answer_text_1 = str(answer_1)

            # 5) compute embedding of answer_1 and secondary retrieval
            answer_emb = self.emb_gen.get_text_embedding(answer_text_1)

            # If OntologyRepository has vector search helper, use it preferentially
            top_m_list = []
            try:
                if hasattr(self.onto_repo, 'search_nodes_by_embedding'):
                    # this returns list of {'node':..., 'similarity':...}
                    nodes = self.onto_repo.search_nodes_by_embedding(answer_emb, top_k=top_m)
                    for n in nodes:
                        node_obj = n.get('node') if isinstance(n, dict) else n
                        sim = n.get('similarity') if isinstance(n, dict) else None
                        fragment = None
                        if isinstance(node_obj, dict):
                            fragment = node_obj.get('fragment') or node_obj.get('signature')
                        if not fragment and hasattr(self.onto_repo, 'collect_fragment_for_node'):
                            fragment = self.onto_repo.collect_fragment_for_node(node_obj.get('uri'))
                        top_m_list.append({
                            'type': 'node',
                            'id': node_obj.get('uri'),
                            'title': node_obj.get('title'),
                            'text': fragment,
                            'embedding': node_obj.get('embedding'),
                            'similarity': sim
                        })
                else:
                    # fallback: score all candidates against answer_emb
                    top_m_list = self._score_and_select(answer_emb, candidates, top_m)
            except Exception:
                top_m_list = self._score_and_select(answer_emb, candidates, top_m)

            # 6) merge unique contexts
            uniq = {}
            for c in (top_n_list + top_m_list):
                uid = (c.get('type'), c.get('id'))
                if uid not in uniq:
                    uniq[uid] = c
                else:
                    # keep max similarity
                    if c.get('similarity', 0) > uniq[uid].get('similarity', 0):
                        uniq[uid] = c
            final_contexts = list(uniq.values())

            # 7) final generation
            messages_final = self._make_prompt(query, final_contexts)
            try:
                final_answer = self.generate_answer_by_messages(messages_final)
            except Exception:
                try:
                    final_answer = self.generate_answer_by_messages([messages_final[0], messages_final[1]])
                except Exception as e:
                    logger.exception("gigachat final call failed: %s", e)
                    final_answer = ""

            if isinstance(final_answer, dict):
                final_answer_text = final_answer.get('content') or str(final_answer)
            else:
                final_answer_text = str(final_answer)

            result = {
                'query': query,
                'answer_first': answer_text_1,
                'answer_final': final_answer_text,
                'used_contexts': final_contexts,
                'top_n': top_n_list,
                'top_m': top_m_list,
            }
            return result

        except Exception as e:
            logger.exception("RAG query failed: %s", e)
            return {'error': str(e)}



