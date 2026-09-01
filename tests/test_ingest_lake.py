from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_lake import ingest, pseudonymize  # noqa: E402


class LakeIngestionTests(unittest.TestCase):
    secret = b"a-test-secret-that-is-longer-than-32-bytes"

    def test_pseudonym_is_stable_and_keyed(self) -> None:
        first = pseudonymize("IPP0001", self.secret)

        self.assertEqual(first, pseudonymize("IPP0001", self.secret))
        self.assertNotEqual(first, pseudonymize("IPP0001", b"another-long-test-secret-of-32-bytes"))
        self.assertEqual(len(first), 64)

    def test_ingestion_removes_identity_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            lake = root / "lake"
            patient_directory = source / "patients" / "2026-08-26"
            stay_directory = source / "sejours" / "2026-08-26"
            patient_directory.mkdir(parents=True)
            stay_directory.mkdir(parents=True)

            (patient_directory / "patients.csv").write_text(
                "patient_id,nom,prenom,nir,birth_date,sex,region_code\n"
                "IPP0001,Dupont,Alice,2990000000000,1985-03-12,F,94\n",
                encoding="utf-8",
            )
            (stay_directory / "sejours.csv").write_text(
                "stay_id,patient_id,service_code,admission_ts,discharge_ts,"
                "admission_mode,discharge_mode\n"
                "S001,IPP0001,CARDIO,2026-08-26T08:00:00,"
                "2026-08-27T08:00:00,urgence,domicile\n",
                encoding="utf-8",
            )

            first_run = ingest(source, lake, self.secret)
            second_run = ingest(source, lake, self.secret)

            self.assertEqual(first_run, {"discovered": 2, "copied": 2, "skipped": 0, "failed": 0})
            self.assertEqual(second_run, {"discovered": 2, "copied": 0, "skipped": 2, "failed": 0})

            patient_file = next((lake / "patients" / "2026-08-26").glob("*.csv"))
            stay_file = next((lake / "sejours" / "2026-08-26").glob("*.csv"))
            with patient_file.open(encoding="utf-8", newline="") as handle:
                patient = next(csv.DictReader(handle))
            with stay_file.open(encoding="utf-8", newline="") as handle:
                stay = next(csv.DictReader(handle))

            self.assertEqual(set(patient), {"patient_key", "birth_year", "sex", "region_code"})
            self.assertEqual(patient["birth_year"], "1985")
            self.assertEqual(patient["patient_key"], stay["patient_key"])
            self.assertNotIn("IPP0001", patient_file.read_text(encoding="utf-8"))
            self.assertNotIn("IPP0001", stay_file.read_text(encoding="utf-8"))

            manifest = json.loads(
                (lake / "_state" / "ingestion-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(manifest["entries"]), 2)
            self.assertNotIn(self.secret.decode(), json.dumps(manifest))

    def test_ingestion_refuses_a_different_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            lake = root / "lake"
            source_file = source / "patients" / "2026-08-26" / "patients.csv"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                "patient_id,birth_date,sex,region_code\n"
                "IPP0001,1985-03-12,F,94\n",
                encoding="utf-8",
            )
            ingest(source, lake, self.secret)

            with self.assertRaisesRegex(RuntimeError, "PSEUDONYMIZATION_KEY differs"):
                ingest(source, lake, b"another-long-test-secret-of-32-bytes")


if __name__ == "__main__":
    unittest.main()
