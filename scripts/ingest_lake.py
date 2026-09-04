#!/usr/bin/env python3
"""Incrementally copy CHU deposits into a pseudonymized local data lake."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import hmac
import json
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator


MANIFEST_VERSION = 1
BATCH_NAMESPACE = uuid.UUID("137282c9-c49b-4edc-a0d4-8e16df0f8fb1")
SENSITIVE_PATIENT_COLUMNS = {"patient_id", "nir", "nom", "prenom", "birth_date"}
ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "source-filestorage")
    parser.add_argument("--lake", type=Path, default=ROOT / "data-lake")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def pseudonymization_secret(env_file: Path) -> bytes:
    load_env_file(env_file)
    value = os.environ.get("PSEUDONYMIZATION_KEY", "")
    if len(value) < 32 or value in {"change-me", "replace-with-a-long-random-secret"}:
        raise SystemExit(
            "PSEUDONYMIZATION_KEY must contain at least 32 characters. "
            "Set it in .env or in the process environment."
        )
    return value.encode("utf-8")


def pseudonymize(patient_id: str, secret: bytes) -> str:
    if not patient_id:
        return ""
    return hmac.new(secret, patient_id.encode("utf-8"), hashlib.sha256).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_date(relative_path: Path) -> str:
    for part in relative_path.parts:
        try:
            return date.fromisoformat(part).isoformat()
        except ValueError:
            continue
    raise ValueError(f"No deposit date found in {relative_path}")


def domain_for(relative_path: Path) -> str:
    if not relative_path.parts:
        raise ValueError("Empty relative path")
    domain = relative_path.parts[0]
    if domain == "referentiels":
        if relative_path.name == "services.csv":
            return "services"
        if relative_path.name == "cim10.csv":
            return "cim10"
        if relative_path.name == "description_service.csv":
            return "description_service"
        if relative_path.name == "ccam.csv":
            return "ccam"
    if domain in {"patients", "sejours", "diagnostics", "monitoring", "actes"}:
        return domain
    raise ValueError(f"Unsupported source file: {relative_path}")


def lake_relative_path(relative_path: Path, source_checksum: str) -> Path:
    versioned_name = (
        f"{relative_path.stem}__{source_checksum[:12]}{relative_path.suffix}"
    )
    return relative_path.with_name(versioned_name)


def empty_manifest() -> dict[str, Any]:
    return {"version": MANIFEST_VERSION, "entries": {}}


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_manifest()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != MANIFEST_VERSION:
        raise ValueError(f"Unsupported manifest version in {path}")
    if not isinstance(manifest.get("entries"), dict):
        raise ValueError(f"Invalid manifest entries in {path}")
    return manifest


def atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".manifest-", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


@contextmanager
def ingestion_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another lake ingestion is already running") from error
        yield


def csv_row_count(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.reader(handle)) - 1


def json_row_count(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    return len(data) if isinstance(data, list) else 1


def parquet_row_count(path: Path) -> int:
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return 0
    return pq.ParquetFile(path).metadata.num_rows


def source_row_count(path: Path) -> int:
    if path.suffix.lower() == ".csv":
        return max(0, csv_row_count(path))
    if path.suffix.lower() == ".json":
        return json_row_count(path)
    if path.suffix.lower() == ".parquet":
        return parquet_row_count(path)
    return 0


def write_patients(source: Path, target: Path, secret: bytes) -> None:
    with source.open(encoding="utf-8-sig", newline="") as input_handle, target.open(
        "w", encoding="utf-8", newline=""
    ) as output_handle:
        reader = csv.DictReader(input_handle)
        writer = csv.DictWriter(
            output_handle,
            fieldnames=["patient_key", "birth_year", "sex", "region_code"],
        )
        writer.writeheader()
        for row in reader:
            birth_date = row.get("birth_date", "")
            try:
                birth_year = str(date.fromisoformat(birth_date).year)
            except ValueError:
                birth_year = ""
            writer.writerow(
                {
                    "patient_key": pseudonymize(row.get("patient_id", ""), secret),
                    "birth_year": birth_year,
                    "sex": row.get("sex", ""),
                    "region_code": row.get("region_code", ""),
                }
            )


def write_stays(source: Path, target: Path, secret: bytes) -> None:
    fields = [
        "stay_id",
        "patient_key",
        "service_code",
        "admission_ts",
        "discharge_ts",
        "admission_mode",
        "discharge_mode",
    ]
    with source.open(encoding="utf-8-sig", newline="") as input_handle, target.open(
        "w", encoding="utf-8", newline=""
    ) as output_handle:
        reader = csv.DictReader(input_handle)
        writer = csv.DictWriter(output_handle, fieldnames=fields)
        writer.writeheader()
        for row in reader:
            writer.writerow(
                {
                    "stay_id": row.get("stay_id", ""),
                    "patient_key": pseudonymize(row.get("patient_id", ""), secret),
                    "service_code": row.get("service_code", ""),
                    "admission_ts": row.get("admission_ts", ""),
                    "discharge_ts": row.get("discharge_ts", ""),
                    "admission_mode": row.get("admission_mode", ""),
                    "discharge_mode": row.get("discharge_mode", ""),
                }
            )


def copy_to_lake(source: Path, target: Path, domain: str, secret: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        if domain == "patients":
            write_patients(source, temporary, secret)
        elif domain == "sejours":
            write_stays(source, temporary, secret)
        else:
            with source.open("rb") as input_handle, temporary.open("wb") as output_handle:
                shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
                output_handle.flush()
                os.fsync(output_handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def assert_lake_privacy(path: Path, domain: str) -> None:
    if domain not in {"patients", "sejours"}:
        return
    with path.open(encoding="utf-8", newline="") as handle:
        headers = set(next(csv.reader(handle), []))
    forbidden = headers & SENSITIVE_PATIENT_COLUMNS
    if forbidden:
        raise RuntimeError(f"Sensitive columns found in lake file: {sorted(forbidden)}")


def discover_files(source: Path) -> list[Path]:
    return sorted(
        path
        for path in source.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(source).parts)
    )


def ingest(source: Path, lake: Path, secret: bytes, dry_run: bool = False) -> dict[str, int]:
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source}")

    state_directory = lake / "_state"
    manifest_path = state_directory / "ingestion-manifest.json"
    lock_path = state_directory / "ingestion.lock"
    summary = {"discovered": 0, "copied": 0, "skipped": 0, "failed": 0}

    with ingestion_lock(lock_path):
        manifest = load_manifest(manifest_path)
        key_fingerprint = hashlib.sha256(secret).hexdigest()
        previous_fingerprint = manifest.get("pseudonymization_key_fingerprint")
        if previous_fingerprint and previous_fingerprint != key_fingerprint:
            raise RuntimeError(
                "PSEUDONYMIZATION_KEY differs from the key used by this lake. "
                "Restore the original key before ingesting new files."
            )
        if not previous_fingerprint and not dry_run:
            manifest["pseudonymization_key_fingerprint"] = key_fingerprint
            atomic_json_write(manifest_path, manifest)
        for source_path in discover_files(source):
            relative = source_path.relative_to(source)
            summary["discovered"] += 1
            try:
                domain = domain_for(relative)
                checksum = sha256_file(source_path)
                manifest_key = f"{relative.as_posix()}|{checksum}"
                previous = manifest["entries"].get(manifest_key)
                if previous and previous.get("status") == "SUCCESS":
                    target = lake / previous["lake_file"]
                    if target.exists() and sha256_file(target) == previous["lake_checksum"]:
                        summary["skipped"] += 1
                        continue

                batch_id = str(uuid.uuid5(BATCH_NAMESPACE, manifest_key))
                lake_relative = lake_relative_path(relative, checksum)
                target_path = lake / lake_relative
                if dry_run:
                    print(f"WOULD_COPY {relative} -> {lake_relative}")
                    summary["copied"] += 1
                    continue

                copy_to_lake(source_path, target_path, domain, secret)
                assert_lake_privacy(target_path, domain)
                manifest["entries"][manifest_key] = {
                    "batch_id": batch_id,
                    "domain": domain,
                    "source_file": relative.as_posix(),
                    "source_checksum": checksum,
                    "source_date": source_date(relative),
                    "source_rows": source_row_count(source_path),
                    "lake_file": lake_relative.as_posix(),
                    "lake_checksum": sha256_file(target_path),
                    "status": "SUCCESS",
                    "processed_at": utc_now(),
                }
                atomic_json_write(manifest_path, manifest)
                summary["copied"] += 1
                print(f"COPIED {relative} -> {lake_relative}")
            except Exception as error:
                summary["failed"] += 1
                print(f"FAILED {relative}: {type(error).__name__}: {error}")

        if summary["failed"]:
            raise RuntimeError(f"Lake ingestion failed for {summary['failed']} file(s)")
    return summary


def main() -> None:
    args = parse_args()
    secret = pseudonymization_secret(args.env_file)
    summary = ingest(args.source, args.lake, secret, args.dry_run)
    print(" ".join(f"{key}={value}" for key, value in summary.items()))


if __name__ == "__main__":
    main()
