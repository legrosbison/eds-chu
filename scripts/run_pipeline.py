#!/usr/bin/env python3
"""Run the Lake, Bronze, Silver, and Gold data pipeline."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from ingest_lake import ingest, load_env_file, load_manifest, pseudonymization_secret


ROOT = Path(__file__).resolve().parents[1]

# Les deux dictionnaires ci-dessous disent simplement dans quel ordre charger
# les fichiers. Les référentiels passent avant les séjours, puis les données qui
# dépendent des séjours passent en dernier.
BRONZE_CONFIG: dict[str, dict[str, Any]] = {
    "services": {"table": "bronze.services", "priority": 10},
    "description_service": {
        "table": "bronze.service_descriptions",
        "priority": 11,
    },
    "cim10": {"table": "bronze.cim10", "priority": 12},
    "ccam": {"table": "bronze.ccam", "priority": 13},
    "patients": {"table": "bronze.patients", "priority": 20},
    "sejours": {"table": "bronze.stays", "priority": 30},
    "diagnostics": {"table": "bronze.diagnostics", "priority": 40},
    "monitoring": {"table": "bronze.monitoring", "priority": 50},
    "actes": {"table": "bronze.acts", "priority": 60},
}

SILVER_CONFIG: dict[str, dict[str, Any]] = {
    "services": {
        "script": "sql/silver/31_services.sql",
        "source": "bronze.services",
        "primary": "silver.dim_service",
        "cleanup": ["silver.dim_service"],
        "priority": 10,
    },
    "description_service": {
        "script": "sql/silver/36_service_descriptions.sql",
        "source": "bronze.service_descriptions",
        "primary": "silver.dim_service",
        "cleanup": ["silver.dim_service"],
        "priority": 11,
    },
    "cim10": {
        "script": "sql/silver/32_cim10.sql",
        "source": "bronze.cim10",
        "primary": "silver.dim_diagnosis",
        "cleanup": ["silver.dim_diagnosis"],
        "priority": 12,
    },
    "ccam": {
        "script": "sql/silver/37_ccam.sql",
        "source": "bronze.ccam",
        "primary": "silver.dim_ccam",
        "cleanup": ["silver.dim_ccam"],
        "priority": 13,
    },
    "patients": {
        "script": "sql/silver/30_patients.sql",
        "source": "bronze.patients",
        "primary": "silver.dim_patient",
        "cleanup": ["silver.dim_patient"],
        "priority": 20,
    },
    "sejours": {
        "script": "sql/silver/33_stays.sql",
        "source": "bronze.stays",
        "primary": "silver.fact_stay",
        "cleanup": ["silver.fact_stay", "silver.dim_date"],
        "priority": 30,
    },
    "diagnostics": {
        "script": "sql/silver/34_diagnostics.sql",
        "source": "bronze.diagnostics",
        "primary": "silver.fact_diagnosis",
        "cleanup": ["silver.fact_diagnosis"],
        "priority": 40,
    },
    "monitoring": {
        "script": "sql/silver/35_monitoring.sql",
        "source": "bronze.monitoring",
        "primary": "silver.fact_monitoring",
        "cleanup": ["silver.fact_monitoring", "silver.dim_date"],
        "priority": 50,
    },
    "actes": {
        "script": "sql/silver/38_acts.sql",
        "source": "bronze.acts",
        "primary": "silver.fact_acte",
        "cleanup": ["silver.fact_acte", "silver.dim_date"],
        "priority": 60,
    },
}

GOLD_TABLES = (
    "gold.kpi_dms_service",
    "gold.kpi_readmission_30d",
    "gold.kpi_emergency_daily",
    "gold.kpi_monitoring_alert_daily",
    "gold.kpi_pathology_prevalence",
    "gold.kpi_cohort_demographics",
    "gold.kpi_activity_dms_category",
    "gold.kpi_acts_service",
    "gold.kpi_acts_type",
    "gold.kpi_act_density_bed",
    "gold.kpi_billed_amount_service",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "source-filestorage")
    parser.add_argument("--lake", type=Path, default=ROOT / "data-lake")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument(
        "--step",
        choices=("all", "lake", "bronze", "silver", "gold"),
        default="all",
        help="Étape à lancer (par défaut : tout le pipeline)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Connexion ClickHouse
# ---------------------------------------------------------------------------

class ClickHouseClient:
    def __init__(self, url: str, user: str, password: str) -> None:
        self.url = url.rstrip("/") + "/"
        credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {credentials}"}

    def execute(
        self,
        sql: str,
        *,
        data: bytes | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        # Trailing whitespace is harmless for SQL but, with the HTTP interface,
        # it can be prepended to binary input and invalidate Parquet magic bytes.
        query_parameters: dict[str, str] = {"query": sql.strip()}
        for key, value in (params or {}).items():
            query_parameters[f"param_{key}"] = str(value)
        url = self.url + "?" + urllib.parse.urlencode(query_parameters)
        request = urllib.request.Request(
            url,
            data=data if data is not None else b"",
            headers=self.headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ClickHouse HTTP {error.code}: {detail}") from error

    def execute_file(self, path: Path, params: dict[str, Any] | None = None) -> None:
        # The ClickHouse HTTP interface executes one statement per request.
        # Project SQL files contain simple DDL/DML statements without semicolons
        # inside string literals, so a small splitter is sufficient here.
        statements = path.read_text(encoding="utf-8").split(";")
        for statement in statements:
            if statement.strip():
                self.execute(statement, params=params)

    def scalar(self, sql: str, params: dict[str, Any] | None = None) -> str:
        return self.execute(sql + " FORMAT TabSeparated", params=params).strip()


def clickhouse_client(env_file: Path) -> ClickHouseClient:
    load_env_file(env_file)
    return ClickHouseClient(
        os.environ.get("CLICKHOUSE_URL", "http://127.0.0.1:8123"),
        os.environ.get("CLICKHOUSE_USER", "eds_app"),
        os.environ.get("CLICKHOUSE_PASSWORD", "eds_local_password"),
    )


def bootstrap(client: ClickHouseClient) -> None:
    """Créer les tables si elles n'existent pas encore."""
    for relative in (
        "sql/00_audit_tables.sql",
        "sql/10_bronze_tables.sql",
        "sql/20_silver_tables.sql",
        "sql/40_gold_tables.sql",
    ):
        client.execute_file(ROOT / relative)


def record_pipeline_status(
    client: ClickHouseClient,
    run_id: str,
    step: str,
    status: str,
    message: str = "",
) -> None:
    """Ajouter un événement au journal global du pipeline."""
    client.execute(
        """
        INSERT INTO audit.pipeline_runs
        SELECT {run_id:UUID}, {step:String}, {status:String},
               {message:String}, now64(3, 'UTC')
        """,
        params={
            "run_id": run_id,
            "step": step,
            "status": status,
            "message": " ".join(message.split())[:1000],
        },
    )


def successful_manifest_entries(lake: Path) -> list[dict[str, Any]]:
    """Lister les fichiers correctement copiés dans le Lake."""
    manifest_path = lake / "_state" / "ingestion-manifest.json"
    manifest = load_manifest(manifest_path)
    entries = [
        entry for entry in manifest["entries"].values() if entry.get("status") == "SUCCESS"
    ]
    return sorted(
        entries,
        key=lambda item: (
            BRONZE_CONFIG[item["domain"]]["priority"],
            item["source_date"],
            item["source_file"],
        ),
    )


def latest_status(
    client: ClickHouseClient,
    table: str,
    batch_id: str,
    target_table: str,
) -> str:
    return client.scalar(
        f"""
        SELECT if(count() = 0, '', argMax(status, processed_at))
        FROM {table}
        WHERE batch_id = {{batch_id:UUID}}
          AND target_table = {{target_table:String}}
        """,
        {"batch_id": batch_id, "target_table": target_table},
    )


# ---------------------------------------------------------------------------
# Étape Bronze : fichiers du Lake -> tables typées
# ---------------------------------------------------------------------------

def record_bronze_status(
    client: ClickHouseClient,
    entry: dict[str, Any],
    target_table: str,
    status: str,
    row_count: int,
    error_message: str = "",
) -> None:
    client.execute(
        """
        INSERT INTO audit.ingestion_files
        SELECT
            {batch_id:UUID}, {source_file:String}, {source_checksum:String},
            {lake_file:String}, {source_date:Date}, {target_table:String},
            {status:String}, {row_count:UInt64}, {error_message:String}, now64(3, 'UTC')
        """,
        params={
            "batch_id": entry["batch_id"],
            "source_file": entry["source_file"],
            "source_checksum": entry["source_checksum"],
            "lake_file": entry["lake_file"],
            "source_date": entry["source_date"],
            "target_table": target_table,
            "status": status,
            "row_count": row_count,
            "error_message": " ".join(error_message.split())[:1000],
        },
    )


def diagnostics_as_json_each_row(path: Path) -> bytes:
    source = json.loads(path.read_text(encoding="utf-8"))
    lines: list[bytes] = []
    for item in source:
        adapted = {
            "stay_id": item.get("stay_id", ""),
            "diagnostics": [
                {
                    "code_cim10": diagnosis.get("code_cim10", ""),
                    "diagnosis_type": diagnosis.get("type", ""),
                }
                for diagnosis in item.get("diagnostics", [])
            ],
        }
        lines.append(json.dumps(adapted, ensure_ascii=False).encode("utf-8"))
    return b"\n".join(lines) + b"\n"


def csv_without_header(path: Path) -> bytes:
    """Return a CSV payload without its first line for ClickHouse FORMAT CSV."""
    payload = path.read_bytes()
    newline = payload.find(b"\n")
    if newline < 0:
        return b""
    return payload[newline + 1 :]


def bronze_insert_query(domain: str) -> str:
    common = """
        toDate({source_date:String}), {source_file:String},
        rowNumberInAllBlocks() + 1, {batch_id:UUID}, now64(3, 'UTC')
    """
    queries = {
        "patients": f"""
            INSERT INTO bronze.patients
            SELECT patient_key, toUInt16OrNull(nullIf(birth_year, '')),
                   nullIf(sex, ''), nullIf(region_code, ''), {common}
            FROM input('patient_key String, birth_year String, sex String, region_code String')
            SETTINGS max_threads = 1
            FORMAT CSV
        """,
        "sejours": f"""
            INSERT INTO bronze.stays
            SELECT stay_id, patient_key, service_code,
                   parseDateTime64BestEffortOrNull(nullIf(admission_ts, ''), 3, 'UTC'),
                   parseDateTime64BestEffortOrNull(nullIf(discharge_ts, ''), 3, 'UTC'),
                   nullIf(admission_mode, ''), nullIf(discharge_mode, ''), {common}
            FROM input('stay_id String, patient_key String, service_code String, admission_ts String, discharge_ts String, admission_mode String, discharge_mode String')
            SETTINGS max_threads = 1
            FORMAT CSV
        """,
        "diagnostics": f"""
            INSERT INTO bronze.diagnostics
            SELECT stay_id, diagnostics, {common}
            FROM input('stay_id String, diagnostics Array(Tuple(code_cim10 String, diagnosis_type String))')
            SETTINGS max_threads = 1, input_format_json_named_tuples_as_objects = 1
            FORMAT JSONEachRow
        """,
        "monitoring": f"""
            INSERT INTO bronze.monitoring
            SELECT stay_id, ts, CAST(heart_rate, 'Nullable(Int16)'),
                   CAST(spo2, 'Nullable(Int16)'), CAST(temp_c, 'Nullable(Decimal(4, 1))'),
                   {common}
            FROM input('stay_id String, ts Nullable(DateTime64(6)), heart_rate Nullable(Int64), spo2 Nullable(Int64), temp_c Nullable(Float64)')
            SETTINGS max_threads = 1
            FORMAT Parquet
        """,
        "services": f"""
            INSERT INTO bronze.services
            SELECT service_code, nullIf(service_label, ''), {common}
            FROM input('service_code String, service_label String')
            SETTINGS max_threads = 1
            FORMAT CSV
        """,
        "cim10": f"""
            INSERT INTO bronze.cim10
            SELECT code_cim10, nullIf(libelle, ''), {common}
            FROM input('code_cim10 String, libelle String')
            SETTINGS max_threads = 1
            FORMAT CSV
        """,
        "description_service": f"""
            INSERT INTO bronze.service_descriptions
            SELECT service_code, nullIf(categorie, ''),
                   toInt32OrNull(nullIf(capacite_lits, '')), nullIf(pole, ''),
                   {common}
            FROM input('service_code String, categorie String, capacite_lits String, pole String')
            SETTINGS max_threads = 1
            FORMAT CSV
        """,
        "ccam": f"""
            INSERT INTO bronze.ccam
            SELECT code_ccam, nullIf(libelle, ''),
                   toInt32OrNull(nullIf(tarif_euros, '')), {common}
            FROM input('code_ccam String, libelle String, tarif_euros String')
            SETTINGS max_threads = 1
            FORMAT CSV
        """,
        "actes": f"""
            INSERT INTO bronze.acts
            SELECT stay_id, code_ccam, acte_ts, {common}
            FROM input('stay_id String, code_ccam String, acte_ts Nullable(DateTime64(3))')
            SETTINGS max_threads = 1
            FORMAT Parquet
        """,
    }
    return queries[domain]


def load_bronze(client: ClickHouseClient, lake: Path, entries: list[dict[str, Any]]) -> None:
    """Charger chaque fichier une seule fois dans sa table Bronze."""
    for entry in entries:
        domain = entry["domain"]
        target_table = BRONZE_CONFIG[domain]["table"]
        batch_id = entry["batch_id"]
        if latest_status(client, "audit.ingestion_files", batch_id, target_table) == "SUCCESS":
            print(f"BRONZE_SKIP {entry['source_file']}")
            continue

        lake_path = lake / entry["lake_file"]
        try:
            client.execute(
                f"ALTER TABLE {target_table} DELETE WHERE batch_id = {{batch_id:UUID}} SETTINGS mutations_sync = 2",
                params={"batch_id": batch_id},
            )
            if domain == "diagnostics":
                body = diagnostics_as_json_each_row(lake_path)
            elif lake_path.suffix == ".csv":
                body = csv_without_header(lake_path)
            else:
                body = lake_path.read_bytes()
            client.execute(
                bronze_insert_query(domain),
                data=body,
                params={
                    "batch_id": batch_id,
                    "source_date": entry["source_date"],
                    "source_file": entry["source_file"],
                },
            )
            row_count = int(
                client.scalar(
                    f"SELECT count() FROM {target_table} WHERE batch_id = {{batch_id:UUID}}",
                    {"batch_id": batch_id},
                )
            )
            record_bronze_status(client, entry, target_table, "SUCCESS", row_count)
            print(f"BRONZE_LOADED {target_table} rows={row_count} source={entry['source_file']}")
        except Exception as error:
            record_bronze_status(client, entry, target_table, "FAILED", 0, str(error))
            raise


# ---------------------------------------------------------------------------
# Étape Silver : nettoyage SQL -> dimensions et faits
# ---------------------------------------------------------------------------

def record_silver_status(
    client: ClickHouseClient,
    batch_id: str,
    source_table: str,
    target_table: str,
    status: str,
    accepted_rows: int,
    rejected_rows: int,
    error_message: str = "",
) -> None:
    client.execute(
        """
        INSERT INTO audit.silver_batches
        SELECT {batch_id:UUID}, {source_table:String}, {target_table:String},
               {status:String}, {accepted_rows:UInt64}, {rejected_rows:UInt64},
               {error_message:String}, now64(3, 'UTC')
        """,
        params={
            "batch_id": batch_id,
            "source_table": source_table,
            "target_table": target_table,
            "status": status,
            "accepted_rows": accepted_rows,
            "rejected_rows": rejected_rows,
            "error_message": " ".join(error_message.split())[:1000],
        },
    )


def transform_silver(
    client: ClickHouseClient, entries: list[dict[str, Any]]
) -> None:
    """Exécuter les fichiers SQL Silver dans l'ordre de leurs dépendances."""
    ordered = sorted(
        entries,
        key=lambda item: (
            SILVER_CONFIG[item["domain"]]["priority"],
            item["source_date"],
            item["source_file"],
        ),
    )
    for entry in ordered:
        config = SILVER_CONFIG[entry["domain"]]
        batch_id = entry["batch_id"]
        source_table = config["source"]
        target_table = config["primary"]
        bronze_status = latest_status(
            client, "audit.ingestion_files", batch_id, source_table
        )
        if bronze_status != "SUCCESS":
            raise RuntimeError(
                f"Silver requires a successful Bronze batch for {entry['source_file']}"
            )
        if latest_status(client, "audit.silver_batches", batch_id, target_table) == "SUCCESS":
            print(f"SILVER_SKIP {entry['source_file']}")
            continue

        try:
            for table in config["cleanup"]:
                client.execute(
                    f"ALTER TABLE {table} DELETE WHERE batch_id = {{batch_id:UUID}} SETTINGS mutations_sync = 2",
                    params={"batch_id": batch_id},
                )
            client.execute(
                "ALTER TABLE audit.quality_rejects DELETE WHERE batch_id = {batch_id:UUID} SETTINGS mutations_sync = 2",
                params={"batch_id": batch_id},
            )
            client.execute_file(ROOT / config["script"], {"batch_id": batch_id})
            accepted_rows = int(
                client.scalar(
                    f"SELECT count() FROM {target_table} WHERE batch_id = {{batch_id:UUID}}",
                    {"batch_id": batch_id},
                )
            )
            rejected_rows = int(
                client.scalar(
                    "SELECT count() FROM audit.quality_rejects WHERE batch_id = {batch_id:UUID}",
                    {"batch_id": batch_id},
                )
            )
            record_silver_status(
                client,
                batch_id,
                source_table,
                target_table,
                "SUCCESS",
                accepted_rows,
                rejected_rows,
            )
            print(
                f"SILVER_LOADED {target_table} accepted={accepted_rows} "
                f"rejected={rejected_rows} source={entry['source_file']}"
            )
        except Exception as error:
            record_silver_status(
                client, batch_id, source_table, target_table, "FAILED", 0, 0, str(error)
            )
            raise


# ---------------------------------------------------------------------------
# Étape Gold : agrégats métier prêts pour Metabase
# ---------------------------------------------------------------------------

def build_gold(client: ClickHouseClient) -> None:
    """Reconstruire les petites tables KPI à partir des données Silver."""
    client.execute_file(ROOT / "sql/gold/40_build_gold.sql")
    for table in GOLD_TABLES:
        row_count = client.scalar(f"SELECT count() FROM {table}")
        print(f"GOLD_BUILT {table} rows={row_count}")


# ---------------------------------------------------------------------------
# Pipeline principal : Lake, puis Bronze, Silver et Gold
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    load_env_file(args.env_file)
    client = clickhouse_client(args.env_file)
    bootstrap(client)
    run_id = str(uuid.uuid4())
    record_pipeline_status(client, run_id, args.step, "RUNNING")
    print(f"PIPELINE_RUN run_id={run_id} step={args.step}")

    try:
        if args.step in {"all", "lake"}:
            secret = pseudonymization_secret(args.env_file)
            summary = ingest(args.source, args.lake, secret)
            print("LAKE " + " ".join(f"{key}={value}" for key, value in summary.items()))
        if args.step in {"all", "bronze"}:
            entries = successful_manifest_entries(args.lake)
            load_bronze(client, args.lake, entries)
        if args.step in {"all", "silver"}:
            entries = successful_manifest_entries(args.lake)
            transform_silver(client, entries)
        if args.step in {"all", "gold"}:
            build_gold(client)
    except Exception as error:
        record_pipeline_status(client, run_id, args.step, "FAILED", str(error))
        raise
    else:
        record_pipeline_status(client, run_id, args.step, "SUCCESS")
        print(f"PIPELINE_SUCCESS run_id={run_id} step={args.step}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"PIPELINE_FAILED {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from error
