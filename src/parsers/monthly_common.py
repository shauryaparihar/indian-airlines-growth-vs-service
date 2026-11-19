"""Helpers shared by the monthly Air Traffic report parsers."""

import csv
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "monthly_traffic"
OUT_DIR = PROJECT_ROOT / "data" / "processed"
LOG_DIR = PROJECT_ROOT / "logs"

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")


def reports():
    with (RAW_DIR / "manifest.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return sorted(
        ({"year": int(r["year"]), "month": int(r["month"]), "is_revised": r["is_revised"] == "True",
          "path": RAW_DIR / r["local_file"]} for r in rows),
        key=lambda r: (r["year"], r["month"]),
    )


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def airline_key(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_mapping():
    with (PROJECT_ROOT / "data" / "reference" / "airline_mapping.csv").open(encoding="utf-8") as f:
        return {r["source_key"]: r["airline"] for r in csv.DictReader(f) if r["source"] == "monthly"}


def is_value(text):
    return text == "-" or bool(NUM_RE.match(text.rstrip("*")))


def table_rows(table):
    return [[(clean(t), c) for t, c in zip(texts, row.cells)] for row, texts in zip(table.rows, table.extract())]


def header_columns(rows, skip_re):
    """Airline name per column, built from the header rows by x-position (names wrap over several rows)."""
    heads = []
    for i, r in enumerate(rows):
        for t, c in r:
            if t and c is not None and not skip_re.search(t):
                heads.append(((c[0] + c[2]) / 2, i, t))
    clusters = []
    for x, i, t in sorted(heads):
        if clusters and abs(clusters[-1][0] - x) < 6:
            clusters[-1][1].append((i, t))
        else:
            clusters.append([x, [(i, t)]])
    return [[x, " ".join(dict.fromkeys(t for _, t in sorted(parts)))] for x, parts in clusters]


def airline_at(columns, cell):
    # the cell grid is not consistent row to row, so match by x-position; a merged cell spanning
    # several airlines (Air India incl. Alliance Air until 2021) goes to the first one it covers
    inside = [col for col in columns if cell[0] <= col[0] <= cell[2]]
    x = (cell[0] + cell[2]) / 2
    col = inside[0] if inside else min(columns, key=lambda col: abs(col[0] - x))
    return col[1].replace("*", "").strip()


def fiscal_year(year, month):
    start = year if month >= 4 else year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
