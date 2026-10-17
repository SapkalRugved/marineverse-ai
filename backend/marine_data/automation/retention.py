"""Apply bounded retention to automated marine datasets."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg import Connection

from backend.marine_data.database import connect_to_database


@dataclass(frozen=True)
class RetentionPolicy:
    """Retention configuration for one database table."""

    dataset: str
    retention_days: int
    count_sql: str
    delete_sql: str


POLICIES = (
    RetentionPolicy(
        dataset="weather",
        retention_days=30,
        count_sql="""
SELECT COUNT(*)
FROM weather_conditions
WHERE valid_time < %s
  AND valid_time < (
      SELECT MAX(valid_time)
      FROM weather_conditions
  );
""",
        delete_sql="""
DELETE FROM weather_conditions
WHERE valid_time < %s
  AND valid_time < (
      SELECT MAX(valid_time)
      FROM weather_conditions
  );
""",
    ),
    RetentionPolicy(
        dataset="ocean",
        retention_days=14,
        count_sql="""
SELECT COUNT(*)
FROM ocean_conditions
WHERE valid_time < %s
  AND valid_time < (
      SELECT MAX(valid_time)
      FROM ocean_conditions
  );
""",
        delete_sql="""
DELETE FROM ocean_conditions
WHERE valid_time < %s
  AND valid_time < (
      SELECT MAX(valid_time)
      FROM ocean_conditions
  );
""",
    ),
)


class RetentionError(RuntimeError):
    """Raised when retention cannot be evaluated or applied."""


def execute_retention(
    connection: Connection,
    *,
    checked_at: datetime,
    apply_changes: bool,
) -> list[dict[str, Any]]:
    """Evaluate or apply all configured retention policies."""
    results: list[dict[str, Any]] = []

    with connection.cursor() as cursor:
        for policy in POLICIES:
            cutoff = checked_at - timedelta(
                days=policy.retention_days
            )

            cursor.execute(
                policy.count_sql,
                (cutoff,),
            )
            row = cursor.fetchone()

            if row is None:
                raise RetentionError(
                    f"Could not count {policy.dataset} records."
                )

            candidate_records = int(row[0])
            deleted_records = 0

            if apply_changes and candidate_records:
                cursor.execute(
                    policy.delete_sql,
                    (cutoff,),
                )
                deleted_records = cursor.rowcount

            results.append(
                {
                    "dataset": policy.dataset,
                    "retention_days": (
                        policy.retention_days
                    ),
                    "cutoff": cutoff,
                    "candidate_records": (
                        candidate_records
                    ),
                    "deleted_records": deleted_records,
                    "applied": apply_changes,
                }
            )

    return results


def print_results(
    results: list[dict[str, Any]],
) -> None:
    """Print a readable retention report."""
    for result in results:
        mode = (
            "APPLIED"
            if result["applied"]
            else "DRY RUN"
        )

        print(
            f"{result['dataset']}: "
            f"mode={mode}, "
            f"retention_days={result['retention_days']}, "
            f"cutoff={result['cutoff'].isoformat()}, "
            f"candidates={result['candidate_records']}, "
            f"deleted={result['deleted_records']}"
        )


def parse_arguments() -> argparse.Namespace:
    """Parse retention execution mode."""
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate MarineVerse retention policies. "
            "No records are deleted unless --apply is supplied."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete records outside retention limits.",
    )
    return parser.parse_args()


def main() -> int:
    """Evaluate or apply database retention."""
    arguments = parse_arguments()
    checked_at = datetime.now(timezone.utc)

    try:
        with connect_to_database(
            prompt_for_password=False,
        ) as connection:
            results = execute_retention(
                connection,
                checked_at=checked_at,
                apply_changes=arguments.apply,
            )

        print_results(results)

        if not arguments.apply:
            print(
                "Dry run completed. No records were deleted."
            )

        return 0

    except (
        RetentionError,
        psycopg.Error,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())