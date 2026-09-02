#!/usr/bin/env python3
"""Profile the CHU source files without exposing patient identities.

The script reads CSV and JSON with the Python standard library and Parquet
with PyArrow. It produces aggregate-only JSON and Markdown reports.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq


DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
VALID_SEX = {"M", "F"}
VALID_DIAGNOSIS_TYPES = {"principal", "associe"}
VALID_ADMISSION_MODES = {"urgence", "programme", "mutation"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("source-filestorage"))
    parser.add_argument(
        "--json-output", type=Path, default=Path("reports/source-profile.json")
    )
    parser.add_argument(
        "--markdown-output", type=Path, default=Path("docs/profilage-sources.md")
    )
    return parser.parse_args()


def deposit_date(path: Path) -> str:
    for part in path.parts:
        if DATE_RE.fullmatch(part):
            return part
    return "unknown"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def missing_counts(rows: Iterable[dict[str, Any]], columns: Iterable[str]) -> dict[str, int]:
    counts = {column: 0 for column in columns}
    for row in rows:
        for column in counts:
            if row.get(column) in (None, ""):
                counts[column] += 1
    return counts


def count_duplicates(values: Iterable[Any]) -> int:
    counts = Counter(values)
    return sum(count - 1 for count in counts.values() if count > 1)


def safe_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def safe_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def describe_numbers(values: list[float | int]) -> dict[str, float | int | None]:
    if not values:
        return {"min": None, "max": None, "mean": None, "median": None}
    return {
        "min": min(values),
        "max": max(values),
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
    }


def profile_patients(paths: list[Path]) -> tuple[dict[str, Any], set[str]]:
    per_file: list[dict[str, Any]] = []
    all_ids: list[str] = []
    versions: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    totals = Counter()
    patient_ids: set[str] = set()

    for path in paths:
        columns, rows = read_csv(path)
        ids = [row.get("patient_id", "") for row in rows if row.get("patient_id")]
        missing = missing_counts(rows, columns)
        invalid_birth_dates = 0
        future_birth_dates = 0
        invalid_sex = 0
        source_day = safe_date(deposit_date(path))

        for row in rows:
            patient_id = row.get("patient_id", "")
            birth = safe_date(row.get("birth_date", ""))
            if row.get("birth_date") and birth is None:
                invalid_birth_dates += 1
            if birth and source_day and birth > source_day:
                future_birth_dates += 1
            if row.get("sex") not in VALID_SEX:
                invalid_sex += 1
            if patient_id:
                patient_ids.add(patient_id)
                all_ids.append(patient_id)
                versions[patient_id].add(
                    (
                        row.get("birth_date", ""),
                        row.get("sex", ""),
                        row.get("region_code", ""),
                    )
                )

        file_result = {
            "date": deposit_date(path),
            "file": str(path),
            "bytes": path.stat().st_size,
            "rows": len(rows),
            "missing": missing,
            "duplicate_patient_ids_within_file": count_duplicates(ids),
            "invalid_birth_dates": invalid_birth_dates,
            "future_birth_dates": future_birth_dates,
            "invalid_sex": invalid_sex,
        }
        per_file.append(file_result)
        totals.update(
            {
                "rows": len(rows),
                "invalid_birth_dates": invalid_birth_dates,
                "future_birth_dates": future_birth_dates,
                "invalid_sex": invalid_sex,
                "duplicate_patient_ids_within_file": file_result[
                    "duplicate_patient_ids_within_file"
                ],
            }
        )
        totals.update({f"missing_{key}": value for key, value in missing.items()})

    occurrence_counts = Counter(all_ids)
    summary = dict(totals)
    summary.update(
        {
            "distinct_patient_ids": len(patient_ids),
            "patient_ids_repeated_across_deposits": sum(
                count > 1 for count in occurrence_counts.values()
            ),
            "rows_removed_by_latest_version_deduplication": len(all_ids)
            - len(patient_ids),
            "patients_with_changed_silver_attributes": sum(
                len(value) > 1 for value in versions.values()
            ),
        }
    )
    return {"summary": summary, "per_file": per_file}, patient_ids


def profile_references(paths: list[Path]) -> tuple[dict[str, Any], set[str], set[str]]:
    result: dict[str, Any] = {}
    service_codes: set[str] = set()
    diagnosis_codes: set[str] = set()

    for path in paths:
        columns, rows = read_csv(path)
        if "service_code" in columns:
            key = "services"
            code_column = "service_code"
            label_column = "service_label"
            service_codes.update(row[code_column] for row in rows if row.get(code_column))
        else:
            key = "cim10"
            code_column = "code_cim10"
            label_column = "libelle"
            diagnosis_codes.update(row[code_column] for row in rows if row.get(code_column))
        codes = [row.get(code_column, "") for row in rows if row.get(code_column)]
        result[key] = {
            "file": str(path),
            "bytes": path.stat().st_size,
            "rows": len(rows),
            "missing_codes": sum(not row.get(code_column) for row in rows),
            "missing_labels": sum(not row.get(label_column) for row in rows),
            "duplicate_codes": count_duplicates(codes),
        }

    return result, service_codes, diagnosis_codes


def profile_stays(
    paths: list[Path], patient_ids: set[str], service_codes: set[str]
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    per_file: list[dict[str, Any]] = []
    all_stay_ids: list[str] = []
    stays_by_id: dict[str, dict[str, Any]] = {}
    durations: list[float] = []
    admission_modes = Counter()
    discharge_modes = Counter()
    totals = Counter()

    for path in paths:
        columns, rows = read_csv(path)
        stay_ids = [row.get("stay_id", "") for row in rows if row.get("stay_id")]
        missing = missing_counts(rows, columns)
        file_counts = Counter()
        stay_id_counts = Counter(stay_ids)

        for row in rows:
            stay_id = row.get("stay_id", "")
            admission = safe_datetime(row.get("admission_ts"))
            discharge = safe_datetime(row.get("discharge_ts"))
            row_invalid = False
            if any(
                not row.get(column)
                for column in (
                    "stay_id",
                    "patient_id",
                    "service_code",
                    "admission_ts",
                    "admission_mode",
                )
            ):
                row_invalid = True
            if row.get("admission_ts") and admission is None:
                file_counts["invalid_admission_ts"] += 1
                row_invalid = True
            if row.get("discharge_ts") and discharge is None:
                file_counts["invalid_discharge_ts"] += 1
                row_invalid = True
            if admission and discharge:
                if discharge < admission:
                    file_counts["discharge_before_admission"] += 1
                    row_invalid = True
                else:
                    durations.append((discharge - admission).total_seconds() / 3600)
            if not row.get("discharge_ts"):
                file_counts["ongoing_stays"] += 1
                if row.get("discharge_mode"):
                    file_counts["ongoing_with_discharge_mode"] += 1
                    row_invalid = True
            elif not row.get("discharge_mode"):
                file_counts["finished_without_discharge_mode"] += 1
                row_invalid = True
            if row.get("admission_mode") not in VALID_ADMISSION_MODES:
                file_counts["invalid_admission_mode"] += 1
                row_invalid = True
            if row.get("patient_id") and row.get("patient_id") not in patient_ids:
                file_counts["unknown_patient_ids"] += 1
                row_invalid = True
            if row.get("service_code") and row.get("service_code") not in service_codes:
                file_counts["unknown_service_codes"] += 1
                row_invalid = True
            if stay_id and stay_id_counts[stay_id] > 1:
                row_invalid = True
            if row_invalid:
                file_counts["rows_rejected_by_silver_rules"] += 1
            else:
                file_counts["rows_accepted_silver"] += 1
            admission_modes[row.get("admission_mode", "<missing>")] += 1
            discharge_modes[row.get("discharge_mode", "<missing>")] += 1
            if stay_id:
                all_stay_ids.append(stay_id)
                stays_by_id[stay_id] = {
                    "patient_id": row.get("patient_id"),
                    "service_code": row.get("service_code"),
                    "admission_ts": admission,
                    "discharge_ts": discharge,
                    "silver_accepted": not row_invalid,
                }

        file_result = {
            "date": deposit_date(path),
            "file": str(path),
            "bytes": path.stat().st_size,
            "rows": len(rows),
            "missing": missing,
            "duplicate_stay_ids_within_file": count_duplicates(stay_ids),
            **dict(file_counts),
        }
        per_file.append(file_result)
        totals.update(file_counts)
        totals["rows"] += len(rows)
        totals["duplicate_stay_ids_within_file"] += file_result[
            "duplicate_stay_ids_within_file"
        ]
        totals.update({f"missing_{key}": value for key, value in missing.items()})

    summary = dict(totals)
    summary.update(
        {
            "distinct_stay_ids": len(set(all_stay_ids)),
            "duplicate_stay_ids_across_all_files": count_duplicates(all_stay_ids),
            "duration_hours": describe_numbers(durations),
            "admission_modes": dict(sorted(admission_modes.items())),
            "discharge_modes": dict(sorted(discharge_modes.items())),
        }
    )
    return {"summary": summary, "per_file": per_file}, stays_by_id


def profile_diagnostics(
    paths: list[Path], stays_by_id: dict[str, dict[str, Any]], diagnosis_codes: set[str]
) -> dict[str, Any]:
    per_file: list[dict[str, Any]] = []
    all_keys: list[tuple[str, str, str]] = []
    totals = Counter()
    diagnoses_per_stay: list[int] = []

    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        file_counts = Counter()
        file_keys: list[tuple[str, str, str]] = []

        for stay_entry in data:
            stay_id = stay_entry.get("stay_id", "")
            diagnoses = stay_entry.get("diagnostics")
            if not stay_id:
                file_counts["missing_stay_id"] += 1
            if stay_id and stay_id not in stays_by_id:
                file_counts["unknown_stay_ids"] += 1
            if not isinstance(diagnoses, list):
                file_counts["invalid_diagnostics_array"] += 1
                continue
            diagnoses_per_stay.append(len(diagnoses))
            if not diagnoses:
                file_counts["empty_diagnostics_arrays"] += 1
            principal_count = 0
            for diagnosis in diagnoses:
                file_counts["diagnosis_rows"] += 1
                code = diagnosis.get("code_cim10", "")
                diagnosis_type = diagnosis.get("type", "")
                row_invalid = False
                if not stay_id:
                    row_invalid = True
                stay = stays_by_id.get(stay_id)
                if stay and not stay["silver_accepted"]:
                    file_counts["rows_on_rejected_silver_stay"] += 1
                    row_invalid = True
                if not code:
                    file_counts["missing_diagnosis_code"] += 1
                    row_invalid = True
                elif code not in diagnosis_codes:
                    file_counts["unknown_diagnosis_codes"] += 1
                    row_invalid = True
                if diagnosis_type not in VALID_DIAGNOSIS_TYPES:
                    file_counts["invalid_diagnosis_type"] += 1
                    row_invalid = True
                if diagnosis_type == "principal":
                    principal_count += 1
                if stay_id and stay_id not in stays_by_id:
                    row_invalid = True
                if row_invalid:
                    file_counts["rows_rejected_by_silver_rules"] += 1
                else:
                    file_counts["rows_accepted_silver"] += 1
                key = (stay_id, code, diagnosis_type)
                file_keys.append(key)
                all_keys.append(key)
            if principal_count == 0:
                file_counts["stays_without_principal_diagnosis"] += 1
            elif principal_count > 1:
                file_counts["stays_with_multiple_principal_diagnoses"] += 1

        file_result = {
            "date": deposit_date(path),
            "file": str(path),
            "bytes": path.stat().st_size,
            "stay_entries": len(data),
            "duplicate_diagnoses_within_file": count_duplicates(file_keys),
            **dict(file_counts),
        }
        per_file.append(file_result)
        totals.update(file_counts)
        totals["stay_entries"] += len(data)
        totals["duplicate_diagnoses_within_file"] += file_result[
            "duplicate_diagnoses_within_file"
        ]

    summary = dict(totals)
    summary.update(
        {
            "distinct_diagnosis_events": len(set(all_keys)),
            "duplicate_diagnoses_across_all_files": count_duplicates(all_keys),
            "diagnoses_per_stay": describe_numbers(diagnoses_per_stay),
        }
    )
    return {"summary": summary, "per_file": per_file}


def profile_monitoring(
    paths: list[Path], stays_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    per_file: list[dict[str, Any]] = []
    all_keys: list[tuple[str, str]] = []
    totals = Counter()
    values: dict[str, list[float | int]] = {
        "heart_rate": [],
        "spo2": [],
        "temp_c": [],
    }

    for path in paths:
        parquet = pq.ParquetFile(path)
        file_counts = Counter()
        file_keys: list[tuple[str, str]] = []
        rows = 0
        source_day = safe_date(deposit_date(path))

        for batch in parquet.iter_batches(batch_size=65_536):
            for row in batch.to_pylist():
                rows += 1
                stay_id = row.get("stay_id")
                timestamp = safe_datetime(row.get("ts"))
                heart_rate = row.get("heart_rate")
                spo2 = row.get("spo2")
                temp_c = row.get("temp_c")
                required_invalid = False
                temporal_invalid = False
                parent_invalid = False

                for column, value in row.items():
                    if value is None:
                        file_counts[f"missing_{column}"] += 1
                        required_invalid = True
                if timestamp is None:
                    if row.get("ts") is not None:
                        file_counts["invalid_ts"] += 1
                    required_invalid = True
                elif source_day and timestamp.date() != source_day:
                    file_counts["timestamp_outside_deposit_date"] += 1

                if heart_rate is not None:
                    values["heart_rate"].append(heart_rate)
                    if not 20 <= heart_rate <= 250:
                        file_counts["heart_rate_out_of_range"] += 1
                        required_invalid = True
                if spo2 is not None:
                    values["spo2"].append(spo2)
                    if not 50 <= spo2 <= 100:
                        file_counts["spo2_out_of_range"] += 1
                        required_invalid = True
                if temp_c is not None:
                    values["temp_c"].append(temp_c)
                    if not 30 <= temp_c <= 45:
                        file_counts["temp_c_out_of_range"] += 1
                        required_invalid = True

                stay = stays_by_id.get(stay_id or "")
                if not stay:
                    file_counts["unknown_stay_ids"] += 1
                    parent_invalid = True
                else:
                    if not stay["silver_accepted"]:
                        file_counts["rows_on_rejected_silver_stay"] += 1
                        parent_invalid = True
                    if timestamp:
                        if stay["admission_ts"] and timestamp < stay["admission_ts"]:
                            file_counts["timestamp_before_admission"] += 1
                            temporal_invalid = True
                        if stay["discharge_ts"] and timestamp > stay["discharge_ts"]:
                            file_counts["timestamp_after_discharge"] += 1
                            temporal_invalid = True

                if required_invalid:
                    file_counts["rows_rejected_by_required_quality_rules"] += 1
                if temporal_invalid:
                    file_counts["rows_rejected_by_stay_window_rule"] += 1
                if required_invalid or temporal_invalid or parent_invalid:
                    file_counts["rows_rejected_by_all_silver_rules"] += 1
                else:
                    file_counts["rows_accepted_silver"] += 1
                key = (stay_id or "", timestamp.isoformat() if timestamp else "")
                file_keys.append(key)
                all_keys.append(key)

        file_result = {
            "date": deposit_date(path),
            "file": str(path),
            "bytes": path.stat().st_size,
            "rows": rows,
            "row_groups": parquet.metadata.num_row_groups,
            "duplicate_stay_timestamp_within_file": count_duplicates(file_keys),
            **dict(file_counts),
        }
        per_file.append(file_result)
        totals.update(file_counts)
        totals["rows"] += rows
        totals["duplicate_stay_timestamp_within_file"] += file_result[
            "duplicate_stay_timestamp_within_file"
        ]

    summary = dict(totals)
    summary.update(
        {
            "distinct_monitoring_events": len(set(all_keys)),
            "duplicate_stay_timestamp_across_all_files": count_duplicates(all_keys),
            "heart_rate": describe_numbers(values["heart_rate"]),
            "spo2": describe_numbers(values["spo2"]),
            "temp_c": describe_numbers(values["temp_c"]),
        }
    )
    return {"summary": summary, "per_file": per_file}


def value(data: dict[str, Any], key: str) -> Any:
    return data.get(key, 0)


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    result = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    result.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return "\n".join(result)


def build_markdown(profile: dict[str, Any]) -> str:
    patients = profile["patients"]["summary"]
    stays = profile["stays"]["summary"]
    diagnostics = profile["diagnostics"]["summary"]
    monitoring = profile["monitoring"]["summary"]

    inventory_rows: list[list[Any]] = []
    for domain in ("patients", "stays", "diagnostics", "monitoring"):
        for item in profile[domain]["per_file"]:
            row_count = item.get("rows", item.get("stay_entries", 0))
            inventory_rows.append(
                [domain, item["date"], f"{row_count:,}".replace(",", " "), item["bytes"]]
            )
    for domain, item in profile["references"].items():
        inventory_rows.append(
            [domain, deposit_date(Path(item["file"])), item["rows"], item["bytes"]]
        )

    quality_rows = [
        ["Patients", "Lignes reçues", patients["rows"], "Information"],
        ["Patients", "Patients distincts", patients["distinct_patient_ids"], "Information"],
        [
            "Patients",
            "Lignes retirées par déduplication version la plus récente",
            patients["rows_removed_by_latest_version_deduplication"],
            "Traitement Silver",
        ],
        ["Patients", "Sexes invalides", value(patients, "invalid_sex"), "Rejet"],
        ["Patients", "Dates de naissance invalides", value(patients, "invalid_birth_dates"), "Rejet"],
        ["Séjours", "Lignes reçues", stays["rows"], "Information"],
        ["Séjours", "Séjours en cours", value(stays, "ongoing_stays"), "Conserver"],
        ["Séjours", "Sortie antérieure à l'admission", value(stays, "discharge_before_admission"), "Rejet"],
        ["Séjours", "Séjour terminé sans mode de sortie", value(stays, "finished_without_discharge_mode"), "Rejet"],
        ["Séjours", "Lignes rejetées (règles combinées)", value(stays, "rows_rejected_by_silver_rules"), "Rejet"],
        ["Séjours", "Patients inconnus", value(stays, "unknown_patient_ids"), "Rejet / investigation"],
        ["Séjours", "Services inconnus", value(stays, "unknown_service_codes"), "Rejet / investigation"],
        ["Diagnostics", "Associations aplaties", diagnostics["diagnosis_rows"], "Information"],
        ["Diagnostics", "Codes CIM-10 inconnus", value(diagnostics, "unknown_diagnosis_codes"), "Rejet / investigation"],
        ["Diagnostics", "Types invalides", value(diagnostics, "invalid_diagnosis_type"), "Rejet"],
        ["Diagnostics", "Lignes liées à un séjour Silver rejeté", value(diagnostics, "rows_on_rejected_silver_stay"), "Rejet en cascade"],
        ["Monitoring", "Relevés reçus", monitoring["rows"], "Information"],
        ["Monitoring", "FC hors 20–250", value(monitoring, "heart_rate_out_of_range"), "Rejet"],
        ["Monitoring", "SpO2 hors 50–100", value(monitoring, "spo2_out_of_range"), "Rejet"],
        ["Monitoring", "Température hors 30–45", value(monitoring, "temp_c_out_of_range"), "Rejet"],
        [
            "Monitoring",
            "Lignes rejetées par les règles obligatoires",
            value(monitoring, "rows_rejected_by_required_quality_rules"),
            "Rejet",
        ],
        ["Monitoring", "Relevés hors fenêtre du séjour", value(monitoring, "rows_rejected_by_stay_window_rule"), "Rejet de cohérence"],
        ["Monitoring", "Lignes liées à un séjour Silver rejeté", value(monitoring, "rows_on_rejected_silver_stay"), "Rejet en cascade"],
        ["Monitoring", "Lignes rejetées (règles combinées)", value(monitoring, "rows_rejected_by_all_silver_rules"), "Rejet"],
    ]

    return f"""# Profilage des fichiers sources

Rapport généré automatiquement par `scripts/profile_sources.py`. Il ne contient aucune identité ni valeur patient en clair.

## Périmètre

{md_table(["Domaine", "Dépôt", "Lignes / entrées", "Taille (octets)"], inventory_rows)}

Volume total des fichiers : **{profile['inventory']['total_bytes']:,} octets** pour **{profile['inventory']['file_count']} fichiers**.

## Résultats principaux

{md_table(["Domaine", "Contrôle", "Nombre", "Décision"], quality_rows)}

## Patients

- **{patients['rows']:,} lignes** reçues pour **{patients['distinct_patient_ids']:,} patients distincts**.
- **{patients['rows_removed_by_latest_version_deduplication']:,} lignes** sont des retours quotidiens à retirer en gardant la version la plus récente.
- **{patients['patients_with_changed_silver_attributes']:,} patients** ont changé sur au moins un attribut Silver (`birth_date`, `sex`, `region_code`) entre deux dépôts.
- Doublons à l'intérieur d'un même fichier : **{value(patients, 'duplicate_patient_ids_within_file')}**.
- Valeurs manquantes : patient_id **{value(patients, 'missing_patient_id')}**, birth_date **{value(patients, 'missing_birth_date')}**, sex **{value(patients, 'missing_sex')}**, region_code **{value(patients, 'missing_region_code')}**.

Décision Silver : pseudonymiser `patient_id`, supprimer nom/prénom/NIR, généraliser `birth_date` en `birth_year`, normaliser le sexe et dédupliquer sur le pseudonyme stable.

## Séjours

- **{stays['rows']:,} lignes** et **{stays['distinct_stay_ids']:,} identifiants de séjour distincts**.
- **{value(stays, 'ongoing_stays'):,} séjours en cours** : sortie vide légitime, à conserver.
- **{value(stays, 'discharge_before_admission'):,} séjours** ont une sortie antérieure à l'admission et doivent être rejetés.
- **{value(stays, 'finished_without_discharge_mode'):,} séjours terminés** n'ont pas de mode de sortie et doivent être rejetés au titre des valeurs manquantes.
- Après combinaison des règles, **{value(stays, 'rows_accepted_silver'):,} séjours sont acceptés** et **{value(stays, 'rows_rejected_by_silver_rules'):,} rejetés**.
- Intégrité : **{value(stays, 'unknown_patient_ids')} patients inconnus**, **{value(stays, 'unknown_service_codes')} services inconnus**.
- Durée valide en heures : min **{stays['duration_hours']['min']}**, médiane **{stays['duration_hours']['median']}**, moyenne **{stays['duration_hours']['mean']}**, max **{stays['duration_hours']['max']}**.
- Modes d'admission observés : `{json.dumps(stays['admission_modes'], ensure_ascii=False)}`.

## Diagnostics

- **{diagnostics['stay_entries']:,} entrées séjour** deviennent **{diagnostics['diagnosis_rows']:,} lignes** après aplatissement du JSON.
- Nombre de diagnostics par séjour : min **{diagnostics['diagnoses_per_stay']['min']}**, médiane **{diagnostics['diagnoses_per_stay']['median']}**, moyenne **{diagnostics['diagnoses_per_stay']['mean']}**, max **{diagnostics['diagnoses_per_stay']['max']}**.
- Codes CIM-10 inconnus : **{value(diagnostics, 'unknown_diagnosis_codes')}** ; séjours inconnus : **{value(diagnostics, 'unknown_stay_ids')}**.
- Doublons sur `(stay_id, code_cim10, type)` : **{value(diagnostics, 'duplicate_diagnoses_across_all_files')}**.
- **{value(diagnostics, 'rows_on_rejected_silver_stay'):,} diagnostics** sont rejetés en cascade car leur séjour parent est invalide ; **{value(diagnostics, 'rows_accepted_silver'):,} lignes** restent acceptées.

## Monitoring

- **{monitoring['rows']:,} relevés** dont **{value(monitoring, 'rows_rejected_by_required_quality_rules'):,} lignes** rejetées par les règles physiologiques ou de format obligatoires.
- Fréquence cardiaque : min **{monitoring['heart_rate']['min']}**, max **{monitoring['heart_rate']['max']}**, hors plage **{value(monitoring, 'heart_rate_out_of_range')}**.
- SpO2 : min **{monitoring['spo2']['min']}**, max **{monitoring['spo2']['max']}**, hors plage **{value(monitoring, 'spo2_out_of_range')}**.
- Température : min **{monitoring['temp_c']['min']}**, max **{monitoring['temp_c']['max']}**, hors plage **{value(monitoring, 'temp_c_out_of_range')}**.
- Doublons sur `(stay_id, ts)` : **{value(monitoring, 'duplicate_stay_timestamp_across_all_files')}**.
- Intégrité : **{value(monitoring, 'unknown_stay_ids')} séjours inconnus**, **{value(monitoring, 'timestamp_before_admission')} relevés avant admission**, **{value(monitoring, 'timestamp_after_discharge')} après sortie**.
- **{value(monitoring, 'rows_on_rejected_silver_stay'):,} relevés** dépendent d'un séjour Silver rejeté. Après combinaison des règles physiologiques, temporelles et parentales, **{value(monitoring, 'rows_accepted_silver'):,} relevés sont acceptés** et **{value(monitoring, 'rows_rejected_by_all_silver_rules'):,} rejetés**.

Les bornes fournies par le sujet sont des bornes de **validité**, pas des seuils d'alerte clinique. Les seuils d'alerte devront être validés par le métier avant leur calcul en Gold.

## Conséquences pour l'implémentation

1. Charger d'abord les référentiels et patients, puis les séjours, diagnostics et relevés afin de contrôler l'intégrité des clés.
2. Pseudonymiser avant l'entrée dans l'entrepôt et ne jamais tracer de donnée identifiante dans les rejets.
3. Écrire les lignes invalides dans `audit.quality_rejects` avec la règle, le lot et le fichier source.
4. Partitionner `fact_monitoring` par mois de `measurement_date_key` ; ne pas créer une partition par jour.
5. Effectuer Bronze → Silver → Gold en SQL dans ClickHouse. Le script de profilage sert uniquement à l'exploration initiale.
"""


def main() -> None:
    args = parse_args()
    source = args.source
    if not source.is_dir():
        raise SystemExit(f"Source directory not found: {source}")

    paths = sorted(path for path in source.rglob("*") if path.is_file())
    patient_paths = [path for path in paths if path.match("*/patients/*/patients.csv")]
    stay_paths = [path for path in paths if path.match("*/sejours/*/sejours.csv")]
    diagnostic_paths = [path for path in paths if path.match("*/diagnostics/*/diagnostics.json")]
    monitoring_paths = [path for path in paths if path.match("*/monitoring/*/monitoring.parquet")]
    reference_paths = [path for path in paths if "/referentiels/" in f"/{path.as_posix()}"]

    patients, patient_ids = profile_patients(patient_paths)
    references, service_codes, diagnosis_codes = profile_references(reference_paths)
    stays, stays_by_id = profile_stays(stay_paths, patient_ids, service_codes)
    diagnostics = profile_diagnostics(diagnostic_paths, stays_by_id, diagnosis_codes)
    monitoring = profile_monitoring(monitoring_paths, stays_by_id)

    profile = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(source),
        "inventory": {
            "file_count": len(paths),
            "total_bytes": sum(path.stat().st_size for path in paths),
        },
        "patients": patients,
        "references": references,
        "stays": stays,
        "diagnostics": diagnostics,
        "monitoring": monitoring,
    }

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(build_markdown(profile), encoding="utf-8")
    print(f"JSON report: {args.json_output}")
    print(f"Markdown report: {args.markdown_output}")


if __name__ == "__main__":
    main()
