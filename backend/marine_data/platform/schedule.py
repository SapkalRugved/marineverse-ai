"""Run explicitly configured retained-data jobs; suitable for cron/Task Scheduler."""

import argparse
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from backend.marine_data.platform.pipeline import run
from backend.marine_data.storage import PROJECT_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Untracked local JSON job list")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    jobs = json.loads(args.config.read_text(encoding="utf-8"))
    failures = 0
    for job in jobs:
        try:
            report = run(**job)
            print(
                json.dumps(
                    {
                        "dataset": job["dataset"],
                        "status": report["status"],
                        "release": report["release"],
                    }
                )
            )
        except Exception as exc:
            failures += 1
            print(
                json.dumps(
                    {
                        "dataset": job.get("dataset"),
                        "status": "failed",
                        "error_type": type(exc).__name__,
                    }
                ),
                file=sys.stderr,
            )
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
