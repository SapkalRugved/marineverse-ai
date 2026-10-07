"""Retrieve and retain raw Indian port data from OpenStreetMap Overpass."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
REQUEST_TIMEOUT_SECONDS = (15, 240)
USER_AGENT = "MarineVerseAI-Objective2/1.0"

MODULE_DIRECTORY = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIRECTORY.parents[2]

QUERY_FILE = MODULE_DIRECTORY / "queries" / "ports_india.overpassql"
RAW_OUTPUT_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "ports"


class RetrievalError(RuntimeError):
    """Raised when a valid raw Overpass response cannot be retained."""


def load_query(query_file: Path = QUERY_FILE) -> str:
    """Load and validate the frozen Overpass query."""
    try:
        query = query_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RetrievalError(
            f"Could not read Overpass query file: {query_file}"
        ) from exc

    if not query:
        raise RetrievalError("Overpass query file is empty.")

    return query


def request_osm_ports(query: str) -> dict[str, Any]:
    """Send the query to Overpass and return its parsed JSON response."""
    try:
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RetrievalError(f"Overpass request failed: {exc}") from exc

    try:
        payload = response.json()
    except requests.JSONDecodeError as exc:
        raise RetrievalError(
            "Overpass returned a response that was not valid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise RetrievalError("Overpass response must be a JSON object.")

    elements = payload.get("elements")

    if not isinstance(elements, list):
        raise RetrievalError(
            "Overpass response does not contain an elements list."
        )

    if not elements:
        raise RetrievalError(
            "Overpass response contains zero source elements."
        )

    return payload


def build_output_path(
    output_directory: Path = RAW_OUTPUT_DIRECTORY,
) -> Path:
    """Create a timestamped path for one retained raw response."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return output_directory / f"osm_ports_india_{timestamp}.json"


def retain_raw_response(
    payload: dict[str, Any],
    output_file: Path,
) -> None:
    """Write JSON atomically so partial responses are not retained."""
    temporary_file = output_file.with_suffix(".json.tmp")

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")

        temporary_file.replace(output_file)
    except OSError as exc:
        temporary_file.unlink(missing_ok=True)
        raise RetrievalError(
            f"Could not retain raw response: {output_file}"
        ) from exc


def main() -> int:
    """Run one raw OSM ports retrieval."""
    try:
        query = load_query()
        payload = request_osm_ports(query)
        output_file = build_output_path()
        retain_raw_response(payload, output_file)
    except RetrievalError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("OSM ports retrieval completed successfully.")
    print(f"Source elements received: {len(payload['elements'])}")
    print(f"Raw response retained at: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())