import unittest

from scripts.etl_kbji_parser import match_code_title, parse_entries, validate_entries


class KbjiParserTests(unittest.TestCase):
    def test_layout_rows_keep_codes_titles_and_descriptions_aligned(self):
        lines = [
            (44, "4110 Tenaga Perkantoran Umum"),
            (44, "4110 Tenaga Perkantoran Umum"),
            (44, "Melakukan berbagai tugas administrasi sesuai prosedur yang ditetapkan."),
            (45, "4132 Petugas Entri Data"),
            (45, "Memasukkan kode dan data ke dalam penyimpanan komputer."),
            (46, "4132.01 Operator Entri Data"),
            (46, "Memasukkan dan memeriksa data elektronik."),
        ]

        entries = parse_entries(lines)
        by_code = {entry["kode_kbji"]: entry for entry in entries}

        self.assertEqual(len(entries), 3)
        self.assertEqual(by_code["4110"]["judul"], "Tenaga Perkantoran Umum")
        self.assertIn("berbagai tugas administrasi", by_code["4110"]["deskripsi"])
        self.assertEqual(by_code["4132.01"]["judul"], "Operator Entri Data")

    def test_validation_rejects_severely_incomplete_data(self):
        with self.assertRaisesRegex(ValueError, "Expected"):
            validate_entries([
                {
                    "kode_kbji": "4132.01",
                    "judul": "Operator Entri Data",
                    "deskripsi": "Memasukkan data.",
                }
            ])

    def test_doubled_ocr_code_is_normalized(self):
        self.assertEqual(
            match_code_title("55331111..0033 Pengasuh Anak"),
            ("5311.03", "Pengasuh Anak"),
        )


if __name__ == "__main__":
    unittest.main()
