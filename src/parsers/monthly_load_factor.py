"""Parse the month-wise passenger load factor table ("Month-wise seat factor of scheduled operators")."""

import re

import pdfplumber

from monthly_common import (LOG_DIR, MONTHS, OUT_DIR, airline_at, airline_key, fiscal_year, header_columns, is_value,
                            load_mapping, reports, table_rows, write_csv)

SKIP_HEAD = re.compile(r"^month$|^month & year$", re.I)
MONTH_RE = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.I)


def find_table(pdf):
    for page in pdf.pages:
        text = page.extract_text() or ""
        if re.search(r"SEAT FACTOR OF SCHEDULED", text, re.I):
            tables = [t for t in page.find_tables() if len(t.rows) >= 10]
            if tables:
                return max(tables, key=lambda t: len(t.rows))
    return None


def month_of(row):
    label = next((t for t, _ in row if t), "")
    m = MONTH_RE.match(label)
    return MONTHS.index(m.group(1).lower()) + 1 if m else None


def parse_table(table):
    rows = table_rows(table)
    first = next((i for i, r in enumerate(rows) if month_of(r)), None)
    if first is None:
        return None
    columns = header_columns(rows[:first], SKIP_HEAD)
    by_month = {}
    for r in rows[first:]:
        month = month_of(r)
        if month:
            by_month[month] = {airline_at(columns, c): t for t, c in r
                               if c is not None and is_value(t) and t != "-"}
    return by_month


def main():
    mapping = load_mapping()
    best, checks, revisions, unmapped = {}, [], [], set()
    for report in reports():
        name = report["path"].name
        with pdfplumber.open(report["path"]) as pdf:
            table = find_table(pdf)
            by_month = parse_table(table) if table else None
        problems = [] if by_month else ["no load factor table found" if table is None else "no month rows in table"]
        by_month = by_month or {}
        n = 0
        for month, values in by_month.items():
            if month > report["month"]:
                continue
            for raw, v in values.items():
                value = float(v.rstrip("*"))
                if not 0 <= value <= 100:
                    problems.append(f"{raw} {month}: {value} outside 0-100")
                    continue
                airline = mapping.get(airline_key(raw))
                if airline is None:
                    unmapped.add(raw)
                    continue
                key = (airline, report["year"], month)
                prev = best.get(key)
                if prev and abs(prev["pax_load_factor_pct"] - value) > 0.05:
                    revisions.append({"airline": airline, "year": report["year"], "month": month,
                                      "report_a": prev["source_report"], "value_a": prev["pax_load_factor_pct"],
                                      "report_b": name, "value_b": value})
                best[key] = {"airline": airline, "airline_raw": raw, "year": report["year"], "month": month,
                             "fiscal_year": fiscal_year(report["year"], month), "pax_load_factor_pct": value,
                             "source_report": name}
                n += 1
        checks.append({"report": name, "status": "; ".join(problems) or "ok", "rows": n})

    rows = sorted(best.values(), key=lambda r: (r["airline"], r["year"], r["month"]))
    write_csv(OUT_DIR / "monthly_airline_load_factor.csv", rows,
              ["airline", "airline_raw", "year", "month", "fiscal_year", "pax_load_factor_pct", "source_report"])
    write_csv(LOG_DIR / "monthly_load_factor_checks.csv", checks, ["report", "status", "rows"])
    write_csv(LOG_DIR / "monthly_load_factor_revisions.csv", revisions,
              ["airline", "year", "month", "report_a", "value_a", "report_b", "value_b"])

    failed = [c for c in checks if c["status"] != "ok"]
    months = sorted({(r["year"], r["month"]) for r in rows})
    print(f"Reports: {len(checks)}  ok: {len(checks) - len(failed)}")
    for c in failed:
        print(f"  {c['report']}: {c['status']}")
    print(f"Rows: {len(rows)}  airlines: {len({r['airline'] for r in rows})}  unmapped: {sorted(unmapped) or 'none'}")
    print(f"Months: {months[0][0]}-{months[0][1]:02d} .. {months[-1][0]}-{months[-1][1]:02d} ({len(months)})")
    print(f"Values revised by a later report: {len(revisions)}")


if __name__ == "__main__":
    main()
