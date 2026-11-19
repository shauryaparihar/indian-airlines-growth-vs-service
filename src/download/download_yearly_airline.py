"""Download DGCA yearly airline-wise tables (Excel) into data/raw/yearly_airline/."""

import argparse
import csv
import io
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import openpyxl

from dgca_portal import (clean_text, fetch_page, file_url, find_links, new_session,
                         page_ids, table_rows)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "yearly_airline"
CATALOG = OUT_DIR / "catalog.csv"

YEARLY_STATS_PAGE = ("4267", "4210")
MIN_EDITION = "2016-17"

DELAY_SECONDS = 1.0
RETRIES = 3

KINDS = {
    "domestic_history": re.compile(
        r"(YEAR ON YEAR GROWTH AND CAGR|YEAR\s*-?\s*WISE DETAILS OF ANNUAL TRAFFIC).*"
        r"ON (SCHEDULED DOMESTIC|DOMESTIC SCHEDULED) SERVICES"),
    "coefficients": re.compile(r"SELECTED TRAFFIC COEFFICIENTS"),
    "monthly_domestic": re.compile(r"MONTHLY TRAFFIC AND OPERATING STATISTICS.*ON SCHEDULED DOMESTIC SERVICES"),
}
CANDIDATE_TABLES = {"1.01", "1.04", "1.07", "1.10"}

SKIP_SECTIONS = re.compile(
    r"INTERNATIONAL OPERATION|CITY.?WISE|CITY PAIR|NON.?SCHEDULED|BLUE DART|QUIKJET",
    re.IGNORECASE,
)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def short_edition(text):
    m = re.search(r"(\d{4})\s*-\s*(\d{2,4})", text)
    return f"{m.group(1)}-{m.group(2)[-2:]}" if m else None


def classify(title):
    title = re.sub(r"\s+", " ", title.upper())
    return next((k for k, pattern in KINDS.items() if pattern.search(title)), "")


def list_editions(session):
    editions = []
    for url, text in find_links(fetch_page(session, *YEARLY_STATS_PAGE)):
        ids = page_ids(url)
        edition = short_edition(text)
        if ids and edition and "Air Transport" in text and edition >= MIN_EDITION:
            editions.append((edition, ids))
    return editions


def list_airlines(session, edition_ids):
    links = find_links(fetch_page(session, *edition_ids))
    section = [ids for url, text in links
               if "airline wise air" in text.lower() and (ids := page_ids(url))]
    if section:
        time.sleep(DELAY_SECONDS)
        links = find_links(fetch_page(session, *section[0]))
    airlines = []
    for url, text in links:
        name = text.strip("- ").strip()
        ids = page_ids(url)
        if name and ids and not SKIP_SECTIONS.search(name):
            airlines.append((name, ids))
    return airlines


def list_tables(session, airline_ids):
    tables = []
    for cells in table_rows(fetch_page(session, *airline_ids)):
        if len(cells) < 2:
            continue
        m = re.match(r"TABLE\s*(?:NO\.?)?\s*-?\s*(\d+\.\d+)", clean_text(cells[0]), re.IGNORECASE)
        if not m:
            continue
        urls = [u for cell in cells[2:] for u, _ in find_links(cell)]
        pdf = next((u for u in urls if u.lower().endswith(".pdf")), "")
        xlsx = next((u for u in urls if u.lower().endswith(".xlsx")), "")
        title = clean_text(cells[1])
        tables.append({"table_no": m.group(1), "website_title": title, "website_kind": classify(title),
                       "pdf_url": file_url(pdf) if pdf else "",
                       "xlsx_url": file_url(xlsx) if xlsx else ""})
    return tables


def edition_from_titles(pages):
    # some edition links open another edition, so read the year from the table titles
    years = Counter()
    for tables in pages:
        for t in tables:
            m = re.search(r"DURING\s+(\d{4}\s*-\s*\d{2,4})", t["website_title"].upper())
            if m:
                years[short_edition(m.group(1))] += 1
                break
    return years.most_common(1)[0][0] if years else None


class MissingOnSite(Exception):
    pass


def fetch_bytes(session, url, magic):
    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.get(url, timeout=120)
            if resp.status_code in (403, 404):
                raise MissingOnSite(f"broken link on DGCA site (HTTP {resp.status_code})")
            resp.raise_for_status()
            if not resp.content.startswith(magic):
                raise RuntimeError(f"unexpected content (content-type {resp.headers.get('content-type')})")
            return resp.content
        except MissingOnSite:
            raise
        except Exception as exc:
            if attempt == RETRIES:
                raise
            print(f"    retry {attempt}/{RETRIES - 1} after error: {exc}")
            time.sleep(DELAY_SECONDS * 2 * attempt)


def title_inside_xlsx(content):
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    parts = [str(v) for row in ws.iter_rows(max_row=8, values_only=True)
             for v in row if isinstance(v, str)]
    wb.close()
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def save(dest, content):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(content)
    tmp.replace(dest)


def write_catalog(rows):
    fields = ["edition", "listed_as", "airline", "table_no", "kind", "website_kind", "file_title",
              "website_title", "local_xlsx", "xlsx_status", "local_pdf", "pdf_status",
              "xlsx_url", "pdf_url", "checked_at"]
    with CATALOG.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kinds", default=",".join(KINDS),
                        help=f"comma-separated, from: {', '.join(KINDS)} (default: all)")
    parser.add_argument("--pdf", action="store_true", help="also download PDFs when an Excel version exists")
    parser.add_argument("--dry-run", action="store_true", help="build the catalog without saving files")
    args = parser.parse_args()
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    unknown = set(kinds) - set(KINDS)
    if unknown:
        parser.error(f"unknown kinds: {', '.join(sorted(unknown))}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = new_session()
    now = datetime.now().isoformat(timespec="seconds")

    print("Reading Yearly Statistics editions from DGCA...")
    editions = list_editions(session)
    print(f"Editions: {', '.join(e for e, _ in editions)}")

    rows = []
    seen = set()
    mislinked = {}
    warnings = []
    counts = {"saved": 0, "already_had": 0, "failed": 0, "broken_links": 0}

    for listed_as, edition_ids in editions:
        time.sleep(DELAY_SECONDS)
        airlines = list_airlines(session, edition_ids)
        print(f"\n== {listed_as}: {len(airlines)} sections")
        pages = []
        for airline, airline_ids in airlines:
            time.sleep(DELAY_SECONDS)
            pages.append((airline, list_tables(session, airline_ids)))
        edition = edition_from_titles(tables for _, tables in pages) or listed_as
        if edition != listed_as:
            mislinked[listed_as] = edition

        for airline, tables in pages:
            if (edition, airline) in seen:
                continue
            seen.add((edition, airline))
            print(f"  {edition} {airline}")

            found = {}
            for t in tables:
                row = {**t, "edition": edition, "listed_as": listed_as, "airline": airline,
                       "kind": "", "file_title": "", "checked_at": now}
                rows.append(row)
                if t["table_no"] not in CANDIDATE_TABLES and not t["website_kind"]:
                    continue

                # website titles are wrong in some editions, so classify by the title inside the file
                content = None
                xlsx_ok = False
                if t["xlsx_url"]:
                    try:
                        content = fetch_bytes(session, t["xlsx_url"], b"PK")
                        row["file_title"] = title_inside_xlsx(content)
                        row["kind"] = classify(row["file_title"])
                        xlsx_ok = True
                    except MissingOnSite as exc:
                        row["xlsx_status"] = str(exc)
                        counts["broken_links"] += 1
                    except Exception as exc:
                        row["xlsx_status"] = f"failed: {exc}"
                        counts["failed"] += 1
                    time.sleep(DELAY_SECONDS)
                if not xlsx_ok:
                    row["kind"] = t["website_kind"]

                if row["kind"] not in kinds:
                    continue
                found.setdefault(row["kind"], []).append(t["table_no"])
                base = OUT_DIR / edition / f"{slug(airline)}__{row['kind']}"

                if content is not None:
                    dest = base.with_suffix(".xlsx")
                    row["local_xlsx"] = dest.relative_to(OUT_DIR).as_posix()
                    if dest.exists() and dest.stat().st_size > 0:
                        row["xlsx_status"] = "already downloaded"
                        counts["already_had"] += 1
                    elif not args.dry_run:
                        save(dest, content)
                        row["xlsx_status"] = "downloaded"
                        counts["saved"] += 1

                if t["pdf_url"] and (args.pdf or not xlsx_ok):
                    dest = base.with_suffix(".pdf")
                    row["local_pdf"] = dest.relative_to(OUT_DIR).as_posix()
                    if dest.exists() and dest.stat().st_size > 0:
                        row["pdf_status"] = "already downloaded"
                        counts["already_had"] += 1
                    elif not args.dry_run:
                        print(f"    pdf <- {unquote(t['pdf_url'].rsplit('/', 1)[-1])}")
                        try:
                            save(dest, fetch_bytes(session, t["pdf_url"], b"%PDF"))
                            row["pdf_status"] = "downloaded"
                            counts["saved"] += 1
                        except MissingOnSite as exc:
                            row["pdf_status"] = str(exc)
                            counts["broken_links"] += 1
                        except Exception as exc:
                            row["pdf_status"] = f"failed: {exc}"
                            counts["failed"] += 1
                        time.sleep(DELAY_SECONDS)

            for kind, numbers in found.items():
                if len(numbers) > 1:
                    warnings.append(f"{edition} {airline}: {kind} matched more than one table ({numbers})")
            missing = [k for k in kinds if k not in found]
            if tables and missing:
                warnings.append(f"{edition} {airline}: no {', '.join(missing)}")

    write_catalog(rows)

    print()
    for listed, real in mislinked.items():
        warnings.insert(0, f"edition link '{listed}' opens the {real} edition (DGCA site error)")
    title_fixes = sum(1 for r in rows if r["kind"] and r["website_kind"] and r["kind"] != r["website_kind"])
    if title_fixes:
        warnings.insert(0, f"{title_fixes} tables have a website title that does not match the file (see catalog)")
    for w in warnings:
        print(f"  CHECK: {w}")
    picked = sum(1 for r in rows if r["kind"] in kinds)
    print(f"\nCatalog: {len(rows)} tables, {picked} of kinds {kinds} -> {CATALOG.relative_to(PROJECT_ROOT)}")
    print(f"Files: saved={counts['saved']} already_had={counts['already_had']} failed={counts['failed']} "
          f"broken_links_on_dgca_site={counts['broken_links']}"
          + (" (dry run: nothing saved)" if args.dry_run else ""))
    if counts["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
