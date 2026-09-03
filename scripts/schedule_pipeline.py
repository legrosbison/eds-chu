#!/usr/bin/env python3
"""Run the complete pipeline once a day and keep a readable local log."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = Path(os.environ.get("PIPELINE_LOG_FILE", ROOT / "logs/pipeline.log"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Lancer une fois puis quitter, pratique pour tester l'ordonnanceur.",
    )
    return parser.parse_args()


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "oui"}


def write_log(message: str) -> None:
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run_pipeline() -> bool:
    step = os.environ.get("PIPELINE_STEP", "all")
    command = [sys.executable, str(ROOT / "scripts/run_pipeline.py"), "--step", step]
    write_log(f"SCHEDULED_RUN_START step={step}")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for output_line in process.stdout:
        write_log("PIPELINE " + output_line.rstrip())
    return_code = process.wait()
    status = "SUCCESS" if return_code == 0 else "FAILED"
    write_log(f"SCHEDULED_RUN_END status={status} exit_code={return_code}")
    return return_code == 0


def next_execution(hour: int, minute: int) -> datetime:
    now = datetime.now().astimezone()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def main() -> None:
    args = parse_args()
    hour = int(os.environ.get("PIPELINE_SCHEDULE_HOUR", "2"))
    minute = int(os.environ.get("PIPELINE_SCHEDULE_MINUTE", "0"))
    if hour not in range(24) or minute not in range(60):
        raise SystemExit("PIPELINE_SCHEDULE_HOUR/MINUTE est hors plage")

    if args.once:
        raise SystemExit(0 if run_pipeline() else 1)

    if env_bool("PIPELINE_RUN_ON_START", True):
        run_pipeline()

    while True:
        target = next_execution(hour, minute)
        write_log(f"NEXT_RUN at={target.isoformat(timespec='minutes')}")
        while True:
            remaining = (target - datetime.now().astimezone()).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 60))
        run_pipeline()


if __name__ == "__main__":
    main()
