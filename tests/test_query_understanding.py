import unittest

from backend.query_understanding import (
    QueryUnderstandingService,
    build_retrieval_queries,
    local_query_understanding,
)


class FakeChatCompletions:
    def __init__(self):
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1

        class Message:
            content = """{
                "normalized_query": "produksi makanan beku berbahan ikan untuk dijual ke supermarket",
                "core_terms": ["produksi makanan beku", "pengolahan ikan"],
                "context_terms": ["supermarket"],
                "excluded_intents": ["restoran"],
                "summary": "Kegiatan utama adalah memproduksi makanan beku berbahan ikan."
            }"""

        class Choice:
            message = Message()

        class Response:
            choices = [Choice()]

        return Response()


class FakeClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": FakeChatCompletions()})()


class QueryUnderstandingTests(unittest.IsolatedAsyncioTestCase):
    def test_sparse_expansion_preserves_and_weights_original_meaning(self):
        understanding = {
            "normalized_query": "operator entri data sekolah",
            "core_terms": ["entri data", "pemutakhiran data"],
            "context_terms": ["sekolah"],
            "excluded_intents": ["kepala sekolah"],
            "summary": "Memasukkan dan memperbarui data sekolah.",
        }
        sparse, semantic, context = build_retrieval_queries(
            "operator sekolah mengelola dapodik",
            understanding,
        )
        self.assertIn("operator sekolah mengelola dapodik", sparse)
        self.assertGreaterEqual(sparse.count("entri data"), 2)
        self.assertIn("Memasukkan dan memperbarui data sekolah", semantic)
        self.assertIn("kepala sekolah", context)

    async def test_detailed_query_uses_llm_and_cache(self):
        client = FakeClient()
        service = QueryUnderstandingService(client, model="test-model")
        query = (
            "kami memproduksi makanan beku berbahan ikan lalu mengemasnya "
            "dan menjual produk tersebut ke jaringan supermarket"
        )
        first = await service.analyze(query, "kbli")
        second = await service.analyze(query, "kbli")

        self.assertEqual(first, second)
        self.assertEqual(first["method"], "llm")
        self.assertEqual(client.chat.completions.calls, 1)
        self.assertIn("pengolahan ikan", first["core_terms"])

    async def test_short_query_stays_local(self):
        client = FakeClient()
        service = QueryUnderstandingService(client, model="test-model")
        result = await service.analyze("warung makan", "kbli")
        self.assertEqual(result, local_query_understanding("warung makan", "kbli"))
        self.assertEqual(client.chat.completions.calls, 0)


if __name__ == "__main__":
    unittest.main()
