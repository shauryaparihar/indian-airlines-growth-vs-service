"""Download DGCA monthly Air Traffic reports into data/raw/monthly_traffic/."""

import argparse
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dgca_portal import clean_text, fetch_page, file_url, find_links, new_session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "monthly_traffic"
MANIFEST = OUT_DIR / "manifest.csv"

AIR_TRAFFIC_RULEBOOK_ID = "4264"
AIR_TRAFFIC_CONTENT_ID = "4206"

DELAY_SECONDS = 1.5
RETRIES = 3

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

NO_REPORT = {
    (2020, 4): "no operations (COVID lockdown)",
}
FIRST_MONTH = (2014, 6)

REVISED_IN_FILENAME = re.compile(r"\d\s*R\d?\.pdf$|\(R\)|revised", re.IGNORECASE)


def parse_month(label):
    key = re.sub(r"[^a-z]", "", label.lower())[:3]
    return MONTHS.get(key)


def parse_listing(listing_html):
    reports = []
    problems = []
    year = None
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", listing_html, re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
        if len(cells) < 2:
            continue
        year_text = clean_text(cells[0])
        if re.fullmatch(r"\d{4}", year_text):
            year = int(year_text)
        for cell in cells[1:]:
            cell_text = clean_text(cell)
            for path, link_text in find_links(cell):
                month = parse_month(link_text)
                if year is None or month is None:
                    problems.append(f"Could not read year/month for link '{link_text}' -> {path}")
                    continue
                source_file = path.rsplit("/", 1)[-1]
                is_revised = "revis" in cell_text.lower() or bool(REVISED_IN_FILENAME.search(source_file))
                reports.append({
                    "year": year,
                    "month": month,
                    "is_revised": is_revised,
                    "link_text": cell_text,
                    "source_file": source_file,
                    "url": file_url(path),
                })
    return reports, problems


def local_name(report):
    suffix = "_revised" if report["is_revised"] else ""
    return f"{report['year']}_{report['month']:02d}{suffix}.pdf"


def check_coverage(reports):
    warnings = []
    by_month = {}
    for r in reports:
        by_month.setdefault((r["year"], r["month"]), []).append(r)

    for key, rs in sorted(by_month.items()):
        if len(rs) > 1:
            files = ", ".join(r["source_file"] for r in rs)
            warnings.append(f"{key[0]}-{key[1]:02d}: {len(rs)} links ({files})")

    last = max(by_month)
    y, m = FIRST_MONTH
    while (y, m) <= last:
        if (y, m) not in by_month and (y, m) not in NO_REPORT:
            warnings.append(f"{y}-{m:02d}: no report listed")
        if (y, m) in by_month and (y, m) in NO_REPORT:
            warnings.append(f"{y}-{m:02d}: report listed, but expected none ({NO_REPORT[(y, m)]})")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return warnings


def pick_one_per_month(reports):
    chosen = {}
    for r in reports:
        key = (r["year"], r["month"])
        if key not in chosen or (r["is_revised"] and not chosen[key]["is_revised"]):
            chosen[key] = r
    return [chosen[k] for k in sorted(chosen)]


def download(session, url, dest):
    tmp = dest.with_suffix(".part")
    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.get(url, timeout=120)
            resp.raise_for_status()
            if not resp.content.startswith(b"%PDF"):
                raise RuntimeError(f"not a PDF (content-type {resp.headers.get('content-type')})")
            tmp.write_bytes(resp.content)
            tmp.replace(dest)
            return len(resp.content)
        except Exception as exc:
            if attempt == RETRIES:
                raise
            print(f"    retry {attempt}/{RETRIES - 1} after error: {exc}")
            time.sleep(DELAY_SECONDS * 2 * attempt)


def write_manifest(rows):
    fields = ["year", "month", "is_revised", "local_file", "source_file", "link_text",
              "url", "size_bytes", "status", "checked_at"]
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list reports without downloading")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = new_session()

    print("Fetching Air Traffic link list from DGCA...")
    reports, problems = parse_listing(fetch_page(session, AIR_TRAFFIC_RULEBOOK_ID, AIR_TRAFFIC_CONTENT_ID))
    for p in problems:
        print(f"  WARNING: {p}")
    print(f"Found {len(reports)} report links.")

    for w in check_coverage(reports):
        print(f"  CHECK: {w}")
    reports = pick_one_per_month(reports)

    if args.dry_run:
        for r in reports:
            print(f"  {local_name(r):<22} <- {r['source_file']}")
        return

    rows = []
    downloaded = skipped = failed = 0
    now = datetime.now().isoformat(timespec="seconds")
    for r in reports:
        name = local_name(r)
        dest = OUT_DIR / name
        row = {**r, "local_file": name, "checked_at": now}
        if dest.exists() and dest.stat().st_size > 0:
            row.update(size_bytes=dest.stat().st_size, status="already downloaded")
            skipped += 1
        else:
            print(f"  downloading {name} <- {r['source_file']}")
            try:
                row.update(size_bytes=download(session, r["url"], dest), status="downloaded")
                downloaded += 1
            except Exception as exc:
                print(f"    FAILED: {exc}")
                row.update(size_bytes="", status=f"failed: {exc}")
                failed += 1
            time.sleep(DELAY_SECONDS)
        rows.append(row)

    write_manifest(rows)
    print(f"\nDone. downloaded={downloaded} already_had={skipped} failed={failed}")
    print(f"Manifest: {MANIFEST.relative_to(PROJECT_ROOT)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
