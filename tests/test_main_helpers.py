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


class KbjiSearchTests(unittest.TestCase):
    def setUp(self):
        self.previous_lookup = main.kbji_lookup.copy()
        self.previous_raw = list(main.kbji_raw_data)
        entries = [
            {
                "kode_kbji": "1345.03",
                "judul": "Kepala Sekolah SMP Dan Sederajat",
                "deskripsi": "Mengendalikan kegiatan pendidikan di sekolah.",
                "level": "rinci",
            },
            {
                "kode_kbji": "4110.00",
                "judul": "Tenaga Perkantoran Umum",
                "deskripsi": "Melaksanakan administrasi, arsip, dan laporan.",
                "level": "rinci",
            },
            {
                "kode_kbji": "4132.01",
                "judul": "Operator Entri Data",
                "deskripsi": "Memasukkan dan memeriksa data elektronik.",
                "level": "rinci",
            },
            {
                "kode_kbji": "4132.02",
                "judul": "Petugas Input Data",
                "deskripsi": "Memasukkan dan mengoreksi data.",
                "level": "rinci",
            },
        ]
        prepared = [main.prepare_kbji_search_entry(entry) for entry in entries]
        main.kbji_lookup.clear()
        main.kbji_lookup.update({entry["kode_kbji"]: entry for entry in prepared})
        main.kbji_raw_data.clear()
        main.kbji_raw_data.extend(prepared)

    def tearDown(self):
        main.kbji_lookup.clear()
        main.kbji_lookup.update(self.previous_lookup)
        main.kbji_raw_data.clear()
        main.kbji_raw_data.extend(self.previous_raw)

    def test_operator_sekolah_uses_task_not_workplace_context(self):
        results = main.get_manual_kbji_classifications("operator sekolah")
        self.assertEqual(
            [result["kode_kbji"] for result in results],
            ["4132.01", "4132.02", "4110.00"],
        )
        self.assertNotIn("1345.03", [result["kode_kbji"] for result in results])

    def test_detailed_school_data_duties_use_same_occupation_family(self):
        results = main.get_manual_kbji_classifications(
            "memasukkan dan memutakhirkan data siswa lalu memeriksa data sekolah"
        )
        self.assertEqual(results[0]["kode_kbji"], "4132.01")

    def test_aliases_rank_operator_data_above_school_manager(self):
        results = main.search_kbji_entries("operator sekolah", limit=4)
        self.assertEqual(results[0]["kode_kbji"], "4132.01")
        self.assertNotEqual(results[0]["kode_kbji"], "1345.03")

    def test_workplace_only_match_does_not_replace_requested_role(self):
        results = main.search_kbji_entries("pengawas sekolah", limit=10)
        codes = [result["kode_kbji"] for result in results]
        self.assertNotIn("4132.01", codes)
        self.assertNotIn("4132.02", codes)


if __name__ == "__main__":
    unittest.main()
