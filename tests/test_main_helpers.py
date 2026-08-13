import unittest

from backend import main


class MainHelperTests(unittest.TestCase):
    def setUp(self):
        self.previous = main.kbli_lookup.copy()
        main.kbli_lookup.clear()
        main.kbli_lookup.update({
            "11111": {
                "kode": "11111",
                "judul": "PERTAMA",
                "hierarki": "HIERARKI PERTAMA",
                "cakupan": "",
                "metadata": {},
            },
            "22222": {
                "kode": "22222",
                "judul": "KEDUA",
                "hierarki": "HIERARKI KEDUA",
                "cakupan": "",
                "metadata": {},
            },
        })

    def tearDown(self):
        main.kbli_lookup.clear()
        main.kbli_lookup.update(self.previous)

    def test_multi_code_output_preserves_each_matching_hierarchy(self):
        titles, hierarchies, found = main.format_code_matches(
            ["11111", "99999", "22222"]
        )
        self.assertEqual(found, ["11111", "22222"])
        self.assertEqual(
            hierarchies,
            ["[11111] HIERARKI PERTAMA", "[99999] -", "[22222] HIERARKI KEDUA"],
        )
        self.assertIn("[99999] Not Found", titles)

    def test_output_filename_is_sanitized_and_bounded(self):
        stem = main.safe_output_stem("../../laporan saya<script>.xlsx")
        self.assertEqual(stem, "laporan_saya_script")
        self.assertLessEqual(len(main.safe_output_stem("x" * 200 + ".xlsx")), 80)

    def test_extract_codes_deduplicates_without_reordering(self):
        self.assertEqual(
            main.extract_kbli_codes("11111, 22222, lalu 11111"),
            ["11111", "22222"],
        )


if __name__ == "__main__":
    unittest.main()
