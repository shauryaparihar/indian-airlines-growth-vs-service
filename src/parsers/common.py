"""Helpers shared by the yearly Excel parsers."""

import csv
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "yearly_airline"
OUT_DIR = PROJECT_ROOT / "data" / "processed"
LOG_DIR = PROJECT_ROOT / "logs"

MAPPING_FILE = PROJECT_ROOT / "data" / "reference" / "airline_mapping.csv"
AGGREGATES = {"all_scheduled_indian_airlines", "scheduled_national_airlines", "scheduled_private_airlines"}
SLUG_TYPOS = {"akasha_air": "akasa_air", "alliance_air_national": "alliance_air"}
YEAR_RE = re.compile(r"^\s*(\d{4})\s*-\s*(\d{2,4})\*?\s*$")
CONFLICT_TOLERANCE = 0.001


def fiscal_year(cell):
    m = YEAR_RE.match(str(cell))
    return f"{m.group(1)}-{m.group(2)[-2:]}" if m else None


def load_mapping(source):
    with MAPPING_FILE.open(encoding="utf-8") as f:
        return {r["source_key"]: r["airline"] for r in csv.DictReader(f) if r["source"] == source}


YEARLY_MAPPING = load_mapping("yearly")


def airline_slug(path):
    slug = path.name.split("__")[0]
    slug = SLUG_TYPOS.get(slug, slug)
    return YEARLY_MAPPING.get(slug, slug)


def norm(text):
    return re.sub(r"\s+", " ", str(text)).strip().upper()


def reconcile(records, key_fields, value_fields):
    """Keep the latest-edition value per key; return (best, conflicts).

    `records` must already be in ascending edition order.
    """
    best = {}
    conflicts = []
    for record in records:
        key = tuple(record[f] for f in key_fields)
        prev = best.get(key)
        if prev:
            diffs = {f: (prev[f], record[f]) for f in value_fields
                     if prev[f] and abs(record[f] - prev[f]) / abs(prev[f]) > CONFLICT_TOLERANCE}
            if diffs:
                conflicts.append((*key, prev["source_edition"], record["source_edition"], diffs))
        best[key] = record
    return best, conflicts


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_conflicts(path, conflicts, key_fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([*key_fields, "edition_a", "edition_b", "column", "value_a", "value_b"])
        for *key, ed_a, ed_b, diffs in conflicts:
            for col, (a, b) in diffs.items():
                writer.writerow([*key, ed_a, ed_b, col, a, b])
