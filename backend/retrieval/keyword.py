from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from heapq import nlargest
from typing import Sequence

from .models import KnowledgeChunk, RetrievalHit


def _tokens(text: str) -> list[str]:
    """Extract lowercase alphanumeric tokens."""
    return [w.casefold() for w in re.findall(r"[a-zA-Z0-9_]+", text) if len(w) > 0]


class KeywordRetriever:
    """Okapi BM25 lexical retrieval engine with filename/path metadata boosting.
    
    Implements standard Okapi BM25:
    k1 = 1.5, b = 0.75, with inverse document frequency (IDF) and
    document length normalization.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._chunks: dict[str, KnowledgeChunk] = {}
        # Term frequencies per chunk: chunk_id -> Counter of tokens
        self._term_freqs: dict[str, Counter[str]] = {}
        # Filename tokens per chunk: chunk_id -> set of tokens
        self._fn_tokens: dict[str, frozenset[str]] = {}
        # Inverted index: token -> set of chunk_ids
        self._inverted_index: dict[str, set[str]] = defaultdict(set)
        # Document lengths: chunk_id -> int
        self._doc_lens: dict[str, int] = {}
        self._avg_dl: float = 0.0

    @property
    def total_docs(self) -> int:
        return len(self._chunks)

    def upsert(self, chunks: Sequence[KnowledgeChunk]) -> None:
        """Upsert knowledge chunks into the BM25 inverted index."""
        for chunk in chunks:
            cid = chunk.chunk_id
            # Remove prior tokens if updating existing chunk
            if cid in self._chunks:
                self._remove_chunk(cid)

            toks = _tokens(chunk.content)
            fn_toks = frozenset(_tokens(chunk.source.filename or ""))
            tf = Counter(toks)

            self._chunks[cid] = chunk
            self._term_freqs[cid] = tf
            self._fn_tokens[cid] = fn_toks
            self._doc_lens[cid] = len(toks)

            for token in tf.keys():
                self._inverted_index[token].add(cid)
            for token in fn_toks:
                self._inverted_index[token].add(cid)

        # Recalculate average document length
        if self._doc_lens:
            self._avg_dl = sum(self._doc_lens.values()) / len(self._doc_lens)
        else:
            self._avg_dl = 0.0

    def _remove_chunk(self, chunk_id: str) -> None:
        if chunk_id in self._term_freqs:
            for token in self._term_freqs[chunk_id].keys():
                self._inverted_index[token].discard(chunk_id)
            del self._term_freqs[chunk_id]
        if chunk_id in self._fn_tokens:
            for token in self._fn_tokens[chunk_id]:
                self._inverted_index[token].discard(chunk_id)
            del self._fn_tokens[chunk_id]
        self._doc_lens.pop(chunk_id, None)
        self._chunks.pop(chunk_id, None)

    def search(self, query: str, top_k: int) -> list[RetrievalHit]:
        """Perform BM25 search across indexed chunks."""
        query_tokens = _tokens(query)
        if not query_tokens or top_k <= 0 or not self._chunks:
            return []

        # Find all candidate chunk IDs matching any query token
        candidates: set[str] = set()
        for token in query_tokens:
            if token in self._inverted_index:
                candidates.update(self._inverted_index[token])

        if not candidates:
            return []

        n_docs = len(self._chunks)
        avg_dl = self._avg_dl if self._avg_dl > 0 else 1.0

        # Query term frequencies
        q_tf = Counter(query_tokens)
        scored: list[tuple[float, str]] = []

        for cid in candidates:
            doc_tf = self._term_freqs.get(cid, Counter())
            doc_len = self._doc_lens.get(cid, 0)
            fn_toks = self._fn_tokens.get(cid, frozenset())

            bm25_score = 0.0
            matched_content_terms = 0

            for token, _ in q_tf.items():
                if token not in self._inverted_index:
                    continue

                # Document frequency for token
                df = len(self._inverted_index[token])
                # Robertson-Spärck Jones IDF with smoothing
                idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

                f = doc_tf.get(token, 0)
                if f > 0:
                    matched_content_terms += 1
                    # BM25 term frequency saturation
                    numerator = f * (self.k1 + 1.0)
                    denominator = f + self.k1 * (1.0 - self.b + self.b * (doc_len / avg_dl))
                    bm25_score += idf * (numerator / denominator)

                # Metadata bonus: term matches filename or extension
                if token in fn_toks:
                    bm25_score += idf * 0.75

            # Exact phrase or multi-term query coverage bonus
            if matched_content_terms > 0:
                coverage_ratio = matched_content_terms / len(set(query_tokens))
                bm25_score *= (1.0 + 0.5 * coverage_ratio)
                scored.append((bm25_score, cid))
            elif any(t in fn_toks for t in query_tokens):
                # Filename-only match: low baseline score
                scored.append((0.05, cid))

        best = nlargest(top_k, scored, key=lambda item: (item[0], item[1]))
        return [RetrievalHit(self._chunks[cid], score, "keyword") for score, cid in best]
