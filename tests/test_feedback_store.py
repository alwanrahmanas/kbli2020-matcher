import asyncio
import tempfile
import unittest
from pathlib import Path

from backend.feedback_store import FeedbackStore, normalize_query, query_similarity, query_tokens
from backend import main


class FeedbackStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = FeedbackStore(Path(self.temp_dir.name) / "feedback.sqlite3")
        self.results = [
            {"code": "1345.03", "judul": "Kepala Sekolah"},
            {"code": "4132.01", "judul": "Operator Entri Data"},
            {"code": "4110.00", "judul": "Tenaga Perkantoran Umum"},
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def _select(self, client_id, query, code="4132.01"):
        session_id = self.store.create_impression(
            "kbji",
            query,
            [result["code"] for result in self.results],
            "test",
        )
        return self.store.save_feedback(session_id, client_id, selected_code=code)

    def test_personal_exact_query_moves_previous_selection_first(self):
        client_id = "client_11111111111111111111111111111111"
        self._select(client_id, "operator sekolah")

        ranked, learning = self.store.apply_feedback(
            "kbji",
            "operator sekolah",
            self.results,
            client_id=client_id,
        )

        self.assertEqual(ranked[0]["code"], "4132.01")
        self.assertTrue(learning["personalized"])
        self.assertIn("pilihan Anda", ranked[0]["feedback_note"])

    def test_global_boost_requires_two_distinct_clients(self):
        query = "operator sekolah mengelola data siswa"
        self._select("client_11111111111111111111111111111111", query)
        once, learning_once = self.store.apply_feedback(
            "kbji",
            "operator sekolah mengelola data murid",
            self.results,
        )
        self.assertEqual(once[0]["code"], "1345.03")
        self.assertFalse(learning_once["applied"])

        self._select("client_22222222222222222222222222222222", query)
        ranked, learning = self.store.apply_feedback(
            "kbji",
            "operator sekolah mengelola data murid",
            self.results,
        )
        self.assertEqual(ranked[0]["code"], "4132.01")
        self.assertTrue(learning["applied"])
        self.assertEqual(ranked[0]["feedback_support"], 2)

    def test_feedback_must_reference_displayed_candidate(self):
        session_id = self.store.create_impression(
            "kbli",
            "warung makan",
            ["56101", "56102"],
            "test",
        )
        with self.assertRaises(ValueError):
            self.store.save_feedback(
                session_id,
                "client_33333333333333333333333333333333",
                selected_code="99999",
            )

    def test_no_match_is_stored_without_becoming_a_positive_vote(self):
        session_id = self.store.create_impression(
            "kbli",
            "aktivitas tidak dikenal",
            [],
            "test",
        )
        saved = self.store.save_feedback(
            session_id,
            "client_44444444444444444444444444444444",
            no_match=True,
        )
        self.assertTrue(saved["no_match"])
        self.assertEqual(self.store.stats()["no_match"], 1)

    def test_query_normalization_and_similarity_are_stable(self):
        self.assertEqual(normalize_query("  Satpol-PP! "), "satpol pp")
        similarity = query_similarity(
            query_tokens("operator sekolah data siswa"),
            query_tokens("operator sekolah data murid"),
        )
        self.assertGreaterEqual(similarity, 0.6)


class FeedbackEndpointFlowTests(unittest.TestCase):
    def test_kbji_selection_is_applied_on_the_next_identical_search(self):
        previous_store = main.feedback_store
        client_id = "client_55555555555555555555555555555555"
        with tempfile.TemporaryDirectory() as temp_dir:
            main.feedback_store = FeedbackStore(Path(temp_dir) / "feedback.sqlite3")
            try:
                first = asyncio.run(main.kbji_search("operator sekolah", 5, client_id))
                self.assertTrue(first["feedback_session_id"])
                self.assertEqual(first["results"][0]["code"], "4132.01")

                saved = asyncio.run(main.submit_feedback(main.FeedbackRequest(
                    session_id=first["feedback_session_id"],
                    client_id=client_id,
                    selected_code="4110.00",
                )))
                self.assertEqual(saved["status"], "saved")

                second = asyncio.run(main.kbji_search("operator sekolah", 5, client_id))
                self.assertEqual(second["results"][0]["code"], "4110.00")
                self.assertTrue(second["feedback_learning"]["personalized"])
            finally:
                main.feedback_store = previous_store


if __name__ == "__main__":
    unittest.main()
