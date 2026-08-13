"""
Hybrid Search Engine for KBLI Classification
Implements: BM25 + Vector Search + Reciprocal Rank Fusion + Semantic Re-ranking

Architecture:
1. Stage 1: Parallel Retrieval (BM25 keyword + Vector semantic)
2. Stage 2: Reciprocal Rank Fusion to merge results
3. Stage 3: LLM-based semantic re-ranking for final top-K
"""

import asyncio
import copy
import hashlib
import json
import math
import os
import pickle
import re
import time
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Optional
import numpy as np
from openai import AsyncOpenAI


# ============================================================================
# BM25 Implementation
# ============================================================================

class BM25:
    """
    BM25 (Okapi BM25) ranking function for keyword-based retrieval.
    Better than TF-IDF for document ranking.
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1  # Term frequency saturation parameter
        self.b = b    # Length normalization parameter
        self.corpus_size = 0
        self.avgdl = 0  # Average document length
        self.doc_freqs = {}  # Document frequency for each term
        self.idf = {}  # Inverse document frequency
        self.doc_len = []  # Length of each document
        self.documents = []  # Tokenized documents
        self.original_docs = []  # Original document dicts
        self.postings = {}  # term -> [(doc_index, term_frequency)]
    
    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words, Indonesian-aware"""
        if not text:
            return []
        # Lowercase and split, keep only alphanumeric
        text = text.lower()
        # Remove punctuation but keep Indonesian characters
        tokens = re.findall(r'\b[a-z0-9]+\b', text)
        # Filter very short tokens
        return [t for t in tokens if len(t) > 1]
    
    def fit(self, documents: list[dict], text_fields: list[str] = None):
        """
        Build BM25 index from documents.
        
        Args:
            documents: List of document dicts
            text_fields: Fields to index (default: judul, hierarki, cakupan)
        """
        if text_fields is None:
            text_fields = ["judul", "hierarki", "cakupan"]
        
        self.original_docs = documents
        self.corpus_size = len(documents)
        self.documents = []
        self.doc_len = []
        
        # Tokenize all documents
        for doc in documents:
            combined_text = " ".join(str(doc.get(f, "")) for f in text_fields)
            tokens = self._tokenize(combined_text)
            self.documents.append(tokens)
            self.doc_len.append(len(tokens))
        
        # Calculate average document length
        self.avgdl = sum(self.doc_len) / self.corpus_size if self.corpus_size > 0 else 0
        
        # Calculate document frequencies
        self.doc_freqs = {}
        self.postings = {}
        for doc_idx, tokens in enumerate(self.documents):
            term_freqs = Counter(tokens)
            for token, frequency in term_freqs.items():
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1
                self.postings.setdefault(token, []).append((doc_idx, frequency))
        
        # Calculate IDF for each term
        self.idf = {}
        for term, df in self.doc_freqs.items():
            # IDF with smoothing to avoid negative values
            self.idf[term] = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1)
    
    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """
        Search for documents matching query.
        
        Returns:
            List of (doc_index, score) tuples, sorted by score descending
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        
        if self.avgdl <= 0 or top_k <= 0:
            return []

        # Score only documents containing a query term. The previous implementation
        # rebuilt a Counter for every document on every query (O(corpus size)).
        scores_by_doc = {}
        for term, query_frequency in Counter(query_tokens).items():
            idf = self.idf.get(term)
            if idf is None:
                continue
            for doc_idx, term_frequency in self.postings.get(term, ()):
                doc_len = self.doc_len[doc_idx]
                numerator = term_frequency * (self.k1 + 1)
                denominator = term_frequency + self.k1 * (
                    1 - self.b + self.b * (doc_len / self.avgdl)
                )
                scores_by_doc[doc_idx] = scores_by_doc.get(doc_idx, 0.0) + (
                    query_frequency * idf * (numerator / denominator)
                )

        scores = list(scores_by_doc.items())
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
    
    def _score_document(self, query_tokens: list[str], doc_tokens: list[str], doc_len: int) -> float:
        """Calculate BM25 score for a single document"""
        score = 0.0
        doc_term_freqs = Counter(doc_tokens)
        
        for term in query_tokens:
            if term not in self.idf:
                continue
            
            tf = doc_term_freqs.get(term, 0)
            if tf == 0:
                continue
            
            idf = self.idf[term]
            # BM25 formula
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / self.avgdl))
            score += idf * (numerator / denominator)
        
        return score


# ============================================================================
# Vector Store Implementation
# ============================================================================

class LocalVectorStore:
    """
    Local in-memory vector store using numpy for similarity search.
    Uses OpenAI text-embedding-3-small for embeddings.
    """
    
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIM = 1536
    CACHE_FILE = "kbli_embeddings_cache.pkl"
    
    def __init__(self, openai_client: AsyncOpenAI, cache_file: str = None):
        self.client = openai_client
        self.cache_file = cache_file or self.CACHE_FILE
        self.embeddings: np.ndarray = None  # Shape: (n_docs, embedding_dim)
        self.documents: list[dict] = []
        self.is_ready = False
        self._query_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._query_cache_size = 256
        self._embedding_inflight: dict[str, asyncio.Task] = {}
    
    async def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding for a single text"""
        response = await self.client.embeddings.create(
            model=self.EMBEDDING_MODEL,
            input=text
        )
        return np.array(response.data[0].embedding, dtype=np.float32)

    async def _get_query_embedding(self, text: str) -> np.ndarray:
        """Return a cached query embedding and coalesce concurrent duplicates."""
        key = " ".join(text.lower().split())
        cached = self._query_cache.pop(key, None)
        if cached is not None:
            self._query_cache[key] = cached
            return cached

        task = self._embedding_inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._get_embedding(text))
            self._embedding_inflight[key] = task

        try:
            embedding = await asyncio.shield(task)
        finally:
            if task.done() and self._embedding_inflight.get(key) is task:
                self._embedding_inflight.pop(key, None)

        self._query_cache[key] = embedding
        self._query_cache.move_to_end(key)
        while len(self._query_cache) > self._query_cache_size:
            self._query_cache.popitem(last=False)
        return embedding
    
    async def _get_embeddings_batch(self, texts: list[str], batch_size: int = 100) -> list[np.ndarray]:
        """Get embeddings for multiple texts in batches"""
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = await self.client.embeddings.create(
                model=self.EMBEDDING_MODEL,
                input=batch
            )
            batch_embeddings = [np.array(e.embedding, dtype=np.float32) for e in response.data]
            all_embeddings.extend(batch_embeddings)
            
            # Progress logging
            print(f"  📊 Embedded {min(i + batch_size, len(texts))}/{len(texts)} documents...")
        
        return all_embeddings
    
    def _get_cache_path(self, base_path: Path) -> Path:
        """Get path to embeddings cache file"""
        return base_path / self.cache_file
    
    @staticmethod
    def _documents_fingerprint(documents: list[dict]) -> str:
        digest = hashlib.sha256()
        for doc in documents:
            payload = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            digest.update(payload.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    def _load_cache(self, cache_path: Path, expected_fingerprint: str) -> bool:
        """Try to load embeddings from cache"""
        if cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    cached = pickle.load(f)
                    cached_documents = cached['documents']
                    cached_fingerprint = cached.get('fingerprint') or self._documents_fingerprint(cached_documents)
                    cached_model = cached.get('model', self.EMBEDDING_MODEL)
                    cached_embeddings = cached['embeddings']
                    if (
                        cached_fingerprint != expected_fingerprint
                        or cached_model != self.EMBEDDING_MODEL
                        or len(cached_embeddings) != len(cached_documents)
                    ):
                        print("⚠️ Embedding cache is stale, rebuilding...")
                        return False
                    self.embeddings = cached_embeddings
                    self.documents = cached_documents
                    self.is_ready = True
                    print(f"✅ Loaded {len(self.documents)} embeddings from cache")
                    return True
            except Exception as e:
                print(f"⚠️ Cache load failed: {e}")
        return False
    
    def _save_cache(self, cache_path: Path, fingerprint: str):
        """Save embeddings to cache"""
        try:
            temp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
            with open(temp_path, 'wb') as f:
                pickle.dump({
                    'embeddings': self.embeddings,
                    'documents': self.documents,
                    'fingerprint': fingerprint,
                    'model': self.EMBEDDING_MODEL,
                }, f)
            temp_path.replace(cache_path)
            print(f"✅ Saved embeddings cache to {cache_path}")
        except Exception as e:
            print(f"⚠️ Cache save failed: {e}")
    
    async def build_index(self, documents: list[dict], text_fields: list[str] = None, 
                          cache_dir: Path = None, force_rebuild: bool = False):
        """
        Build vector index from documents.
        
        Args:
            documents: List of document dicts
            text_fields: Fields to combine for embedding (default: judul, cakupan)
            cache_dir: Directory to store/load cache
            force_rebuild: If True, rebuild even if cache exists
        """
        if text_fields is None:
            text_fields = ["judul", "cakupan"]

        fingerprint = self._documents_fingerprint(documents)
        
        # Try loading from cache first
        if cache_dir and not force_rebuild:
            cache_path = self._get_cache_path(cache_dir)
            if self._load_cache(cache_path, fingerprint):
                return
        
        print(f"🔨 Building vector index for {len(documents)} documents...")
        self.documents = documents
        
        # Prepare texts for embedding
        texts = []
        for doc in documents:
            combined = " ".join(str(doc.get(f, ""))[:500] for f in text_fields)  # Limit length
            texts.append(combined)
        
        # Get embeddings in batches
        if not texts:
            self.embeddings = np.empty((0, self.EMBEDDING_DIM), dtype=np.float32)
            self.is_ready = True
            return

        embedding_list = await self._get_embeddings_batch(texts)
        self.embeddings = np.vstack(embedding_list)
        
        # Normalize for cosine similarity
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        self.embeddings = self.embeddings / (norms + 1e-10)
        
        self.is_ready = True
        print(f"✅ Vector index ready: {self.embeddings.shape}")
        
        # Save to cache
        if cache_dir:
            cache_path = self._get_cache_path(cache_dir)
            self._save_cache(cache_path, fingerprint)
    
    async def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """
        Search for similar documents using cosine similarity.
        
        Returns:
            List of (doc_index, similarity_score) tuples
        """
        if not self.is_ready:
            return []
        
        # Get query embedding
        if self.embeddings is None or len(self.embeddings) == 0 or top_k <= 0:
            return []

        query_embedding = await self._get_query_embedding(query)
        query_embedding = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)
        
        # Cosine similarity (embeddings are normalized)
        similarities = np.dot(self.embeddings, query_embedding)
        
        # Partition first so top-k does not sort the complete corpus.
        result_count = min(top_k, len(similarities))
        if result_count == len(similarities):
            top_indices = np.argsort(similarities)[::-1]
        else:
            candidates = np.argpartition(similarities, -result_count)[-result_count:]
            top_indices = candidates[np.argsort(similarities[candidates])[::-1]]
        
        results = [(int(idx), float(similarities[idx])) for idx in top_indices]
        return results


# ============================================================================
# Reciprocal Rank Fusion
# ============================================================================

def reciprocal_rank_fusion(
    rankings: list[list[tuple[int, float]]], 
    k: int = 60
) -> list[tuple[int, float]]:
    """
    Combine multiple rankings using Reciprocal Rank Fusion.
    
    RRF Score = Σ 1/(k + rank_i) for each ranking list
    
    Args:
        rankings: List of ranking lists, each containing (doc_id, score) tuples
        k: Constant to prevent high scores for top-ranked docs (default: 60)
    
    Returns:
        Combined ranking as list of (doc_id, rrf_score) tuples
    """
    rrf_scores = {}
    
    for ranking in rankings:
        for rank, (doc_id, _) in enumerate(ranking):
            if doc_id not in rrf_scores:
                rrf_scores[doc_id] = 0.0
            rrf_scores[doc_id] += 1.0 / (k + rank + 1)  # rank is 0-indexed
    
    # Sort by RRF score descending
    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


# ============================================================================
# Semantic Re-ranker
# ============================================================================

class SemanticReranker:
    """
    LLM-based semantic re-ranker for final relevance scoring.
    Uses GPT to judge relevance between query and candidates.
    """
    
    def __init__(self, openai_client: AsyncOpenAI):
        self.client = openai_client
    
    async def rerank(
        self, 
        query: str, 
        candidates: list[dict], 
        top_k: int = 5
    ) -> list[dict]:
        """
        Re-rank candidates using LLM semantic understanding.
        
        Args:
            query: Original user query
            candidates: List of candidate documents with 'kode_kbli', 'judul', 'cakupan'
            top_k: Number of results to return
        
        Returns:
            Re-ranked list of candidates with added 'relevance_score' and 'reasoning'
        """
        if not candidates:
            return []
        
        # Limit candidates to prevent token overflow
        candidates = candidates[:15]
        
        # Build candidate list for prompt
        candidate_str = "\n".join([
            f"{i+1}. KODE: {c.get('kode_kbli', c.get('kode', 'N/A'))} | JUDUL: {c.get('judul', '')[:100]} | CAKUPAN: {c.get('cakupan', '')[:150]}"
            for i, c in enumerate(candidates)
        ])
        
        system_prompt = """Anda adalah ahli klasifikasi KBLI 2020 BPS Indonesia.
Tugas: Evaluasi relevansi setiap kandidat KBLI terhadap query pengguna.

ATURAN PENTING:
1. Fokus pada AKTIVITAS UTAMA yang dimaksud user
2. Bedakan: PERDAGANGAN (jual beli) vs INDUSTRI (produksi) vs JASA (layanan)
3. Perhatikan konteks informal bahasa Indonesia
4. Istilah profesi (PNS, ASN, PPPK, Satpol PP, Pegawai, dll) BUKANLAH suatu entitas bisnis atau lapangan usaha. Jika pengguna mencari ini, berikan 'relevance' 0 pada semua kandidat KBLI, dan tuliskan "BUKAN KBLI (Profesi bukan lapangan usaha)" pada 'reasoning'.

OUTPUT FORMAT (JSON only, no markdown):
{
  "rankings": [
    {
      "rank": 1,
      "index": <nomor kandidat 1-based>,
      "relevance": <0.0-1.0>,
      "reason": "<alasan singkat>"
    },
    ...
  ]
}

Urutkan berdasarkan relevansi tertinggi. Hanya sertakan kandidat yang RELEVAN (relevance > 0.3)."""

        user_prompt = f"""Query: "{query}"

Kandidat KBLI:
{candidate_str}

Evaluasi dan ranking berdasarkan relevansi. Output JSON saja."""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-5.4-mini-2026-03-17",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                max_completion_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            if "```" in content:
                match = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
                if match:
                    content = match.group(1).strip()
            
            result = json.loads(content)
            rankings = result.get("rankings", [])
            
            # Map back to candidates with scores
            reranked = []
            for r in rankings[:top_k]:
                idx = r.get("index", 1) - 1  # Convert to 0-based
                if 0 <= idx < len(candidates):
                    candidate = candidates[idx].copy()
                    candidate["relevance_score"] = r.get("relevance", 0.0)
                    candidate["reasoning"] = r.get("reason", "")
                    reranked.append(candidate)
            
            return reranked
            
        except Exception as e:
            print(f"Reranking error: {e}")
            # Fallback: return top candidates without reranking
            return candidates[:top_k]


# ============================================================================
# Hybrid Search Engine
# ============================================================================

class HybridSearchEngine:
    """
    Main Hybrid Search Engine combining all components.
    
    Pipeline:
    1. Parallel BM25 + Vector search
    2. Reciprocal Rank Fusion
    3. Semantic Re-ranking
    """
    
    def __init__(self, openai_client: AsyncOpenAI):
        self.client = openai_client
        self.bm25 = BM25()
        self.vector_store = LocalVectorStore(openai_client)
        self.reranker = SemanticReranker(openai_client)
        self.documents: list[dict] = []
        self.is_ready = False
        self._result_cache: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
        self._result_cache_ttl = 300.0
        self._result_cache_size = 256
        self._search_inflight: dict[tuple, asyncio.Task] = {}
    
    async def initialize(self, documents: list[dict], cache_dir: Path = None):
        """
        Initialize search engine with documents.
        Builds BM25 index and vector store.
        """
        # Filter valid 5-digit KBLI codes only
        valid_docs = [
            d for d in documents 
            if d.get("kode_kbli", "").isdigit() and len(d.get("kode_kbli", "")) == 5
        ]
        
        self.documents = valid_docs
        print(f"📚 Initializing Hybrid Search with {len(valid_docs)} valid KBLI entries...")
        
        # Build BM25 index (fast, synchronous)
        print("🔨 Building BM25 index...")
        self.bm25.fit(valid_docs, text_fields=["judul", "hierarki", "cakupan"])
        print(f"✅ BM25 index ready: {len(self.bm25.idf)} unique terms")
        
        # Build vector store (async, may use cache)
        print("🔨 Building Vector Store...")
        await self.vector_store.build_index(
            valid_docs, 
            text_fields=["judul", "cakupan"],
            cache_dir=cache_dir
        )
        
        self.is_ready = True
        print("✅ Hybrid Search Engine ready!")
    
    async def search(
        self, 
        query: str, 
        top_k: int = 5,
        use_reranking: bool = True,
        retrieval_top_k: int = 20
    ) -> dict:
        """
        Perform hybrid search.
        
        Args:
            query: User search query
            top_k: Number of final results to return
            use_reranking: Whether to use LLM re-ranking
            retrieval_top_k: Number of candidates from each retrieval method
        
        Returns:
            Dict with search results and metadata
        """
        if not self.is_ready:
            return {"error": "Search engine not initialized", "results": []}

        top_k = max(1, min(int(top_k), 20))
        retrieval_top_k = max(top_k, min(int(retrieval_top_k), 100))

        cache_key = (
            " ".join(query.lower().split()),
            int(top_k),
            bool(use_reranking),
            int(retrieval_top_k),
        )
        now = time.monotonic()
        cached = self._result_cache.pop(cache_key, None)
        if cached is not None and now - cached[0] <= self._result_cache_ttl:
            self._result_cache[cache_key] = cached
            return copy.deepcopy(cached[1])

        task = self._search_inflight.get(cache_key)
        if task is None:
            task = asyncio.create_task(
                self._search_uncached(query, top_k, use_reranking, retrieval_top_k)
            )
            self._search_inflight[cache_key] = task

        try:
            result = await asyncio.shield(task)
        finally:
            if task.done() and self._search_inflight.get(cache_key) is task:
                self._search_inflight.pop(cache_key, None)

        self._result_cache[cache_key] = (time.monotonic(), copy.deepcopy(result))
        self._result_cache.move_to_end(cache_key)
        while len(self._result_cache) > self._result_cache_size:
            self._result_cache.popitem(last=False)
        return result

    async def _search_uncached(
        self,
        query: str,
        top_k: int,
        use_reranking: bool,
        retrieval_top_k: int,
    ) -> dict:
        """Execute retrieval and reranking without consulting the result cache."""
        
        # ====== STAGE 1: Parallel Retrieval ======
        # Run BM25 and Vector search in parallel
        bm25_task = asyncio.create_task(asyncio.to_thread(self.bm25.search, query, retrieval_top_k))
        vector_task = asyncio.create_task(self.vector_store.search(query, retrieval_top_k))
        
        bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)
        
        # ====== STAGE 2: Reciprocal Rank Fusion ======
        fused_ranking = reciprocal_rank_fusion([bm25_results, vector_results], k=60)
        
        # Get candidate documents
        candidates = []
        seen_codes = set()
        for doc_idx, rrf_score in fused_ranking[:retrieval_top_k]:
            doc = self.documents[doc_idx]
            code = doc.get("kode_kbli", "")
            if code not in seen_codes:
                seen_codes.add(code)
                candidates.append({
                    **doc,
                    "rrf_score": rrf_score,
                    "_doc_idx": doc_idx
                })
        
        # ====== STAGE 3: Semantic Re-ranking ======
        if use_reranking and candidates:
            final_results = await self.reranker.rerank(query, candidates, top_k)
        else:
            final_results = candidates[:top_k]
        
        # Clean up internal fields
        for r in final_results:
            r.pop("_doc_idx", None)
        
        return {
            "query": query,
            "total_candidates": len(fused_ranking),
            "bm25_top": len(bm25_results),
            "vector_top": len(vector_results),
            "results": final_results
        }
    
    async def search_simple(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Simplified search returning just the results list.
        Useful for batch processing.
        """
        result = await self.search(query, top_k=top_k)
        return result.get("results", [])


# ============================================================================
# Test Function
# ============================================================================

async def test_hybrid_search():
    """Test the hybrid search engine"""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Load KBLI data
    json_path = Path(__file__).parent.parent / "kbli_parsed_fast.json"
    with open(json_path, 'r', encoding='utf-8') as f:
        kbli_data = json.load(f)
    
    print(f"Loaded {len(kbli_data)} KBLI entries")
    
    # Initialize
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    engine = HybridSearchEngine(client)
    
    cache_dir = Path(__file__).parent.parent
    await engine.initialize(kbli_data, cache_dir=cache_dir)
    
    # Test queries
    test_queries = [
        "jualan nasi goreng pinggir jalan",
        "tukang ojek online",
        "warung madura jual rokok",
        "konveksi baju muslim",
        "bengkel motor honda"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        result = await engine.search(query, top_k=5)
        print(f"Candidates evaluated: {result['total_candidates']}")
        print("Results:")
        for i, r in enumerate(result["results"], 1):
            score = r.get("relevance_score", r.get("rrf_score", 0))
            print(f"  {i}. [{r.get('kode_kbli', 'N/A')}] {r.get('judul', '')[:50]}... (score: {score:.3f})")
            if r.get("reasoning"):
                print(f"     Reason: {r['reasoning']}")


if __name__ == "__main__":
    asyncio.run(test_hybrid_search())
