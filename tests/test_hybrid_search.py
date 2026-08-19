import asyncio
import unittest

import numpy as np

from backend.hybrid_search import BM25, HybridSearchEngine, LocalVectorStore


class FakeEmbeddings:
    def __init__(self):
        self.calls = 0

    async def create(self, *, model, input):
        self.calls += 1
        values = input if isinstance(input, list) else [input]

        class Item:
            def __init__(self, value):
                seed = sum(ord(char) for char in value)
                self.embedding = [float((seed + index) % 17) for index in range(8)]

        class Response:
            data = [Item(value) for value in values]

        return Response()


class FakeClient:
    def __init__(self):
        self.embeddings = FakeEmbeddings()


class BM25Tests(unittest.TestCase):
    def test_postings_search_matches_reference_scorer(self):
        documents = [
            {"judul": "warung makan tetap", "hierarki": "makanan", "cakupan": "restoran"},
            {"judul": "bengkel motor", "hierarki": "reparasi", "cakupan": "sepeda motor"},
            {"judul": "warung tenda", "hierarki": "makanan", "cakupan": "tidak tetap"},
        ]
        index = BM25()
        index.fit(documents)
        query = "warung makanan"
        tokens = index._tokenize(query)
        expected = []
        for doc_index, doc_tokens in enumerate(index.documents):
            score = index._score_document(tokens, doc_tokens, index.doc_len[doc_index])
            if score > 0:
                expected.append((doc_index, score))
        expected.sort(key=lambda item: item[1], reverse=True)

        actual = index.search(query, top_k=10)
        self.assertEqual([item[0] for item in actual], [item[0] for item in expected])
        np.testing.assert_allclose(
            [item[1] for item in actual],
            [item[1] for item in expected],
        )


class VectorStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_top_k_and_query_embedding_cache(self):
        client = FakeClient()
        store = LocalVectorStore(client)
        store.EMBEDDING_DIM = 8
        store.documents = [{"kode_kbli": str(index)} for index in range(5)]
        store.embeddings = np.eye(5, 8, dtype=np.float32)
        store.is_ready = True

        first = await store.search("warung makan", top_k=2)
        second = await store.search("  WARUNG   MAKAN ", top_k=2)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertEqual(client.embeddings.calls, 1)

    def test_cache_fingerprint_includes_indexed_fields(self):
        documents = [{"judul": "Warung", "cakupan": "Makanan"}]
        title_only = LocalVectorStore._documents_fingerprint(documents, ["judul"])
        title_and_scope = LocalVectorStore._documents_fingerprint(
            documents,
            ["judul", "cakupan"],
        )
        self.assertNotEqual(title_only, title_and_scope)


class HybridCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_concurrent_searches_are_coalesced_and_cached(self):
        engine = HybridSearchEngine(FakeClient())
        engine.is_ready = True
        calls = 0

        async def fake_uncached(
            query,
            top_k,
            use_reranking,
            retrieval_top_k,
            retrieval_query,
            semantic_query,
            query_context,
        ):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.02)
            return {"query": query, "results": [{"kode_kbli": "56101"}]}

        engine._search_uncached = fake_uncached
        first, second = await asyncio.gather(
            engine.search("warung makan"),
            engine.search("warung makan"),
        )
        third = await engine.search(" WARUNG   MAKAN ")

        self.assertEqual(calls, 1)
        self.assertEqual(first, second)
        self.assertEqual(second, third)

    async def test_understood_queries_reach_each_retrieval_stage(self):
        engine = HybridSearchEngine(FakeClient())
        engine.documents = [{"kode_kbli": "10219", "judul": "Industri Pengolahan Ikan"}]

        class RecordingBm25:
            query = None

            def search(self, query, top_k):
                self.query = query
                return [(0, 1.0)]

        class RecordingVector:
            query = None

            async def search(self, query, top_k):
                self.query = query
                return [(0, 0.9)]

        class RecordingReranker:
            context = None

            async def rerank(self, query, candidates, top_k, query_context=""):
                self.context = query_context
                return candidates[:top_k], True

        engine.bm25 = RecordingBm25()
        engine.vector_store = RecordingVector()
        engine.reranker = RecordingReranker()

        result = await engine._search_uncached(
            "usaha olahan ikan",
            1,
            True,
            10,
            "produksi pengolahan ikan makanan beku",
            "kegiatan memproduksi makanan beku berbahan ikan",
            "Aktivitas utama adalah produksi, bukan perdagangan.",
        )

        self.assertEqual(engine.bm25.query, "produksi pengolahan ikan makanan beku")
        self.assertIn("memproduksi", engine.vector_store.query)
        self.assertIn("bukan perdagangan", engine.reranker.context)
        self.assertEqual(result["rerank_status"], "success")


if __name__ == "__main__":
    unittest.main()
