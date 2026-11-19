"""Parse the airline-wise passengers table ("Market share of scheduled domestic airlines") from every monthly report."""

import re

import pdfplumber

from monthly_common import (LOG_DIR, MONTHS, OUT_DIR, airline_at, airline_key, clean, fiscal_year, header_columns,
                            is_value, load_mapping, reports, table_rows, write_csv)

ORDER = ["jan", "feb", "mar", "q1", "apr", "may", "jun", "q2", "jul", "aug", "sep", "q3",
         "oct", "nov", "dec", "q4", "total"]
QUARTERS = {"q1": ["jan", "feb", "mar"], "q2": ["apr", "may", "jun"],
            "q3": ["jul", "aug", "sep"], "q4": ["oct", "nov", "dec"]}
PERIOD_RE = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|qtr|quarter|otal", re.I)
SKIP_HEAD = re.compile(r"passengers carried|market share|private air|month|year|^&$|pax carried", re.I)
YTD_RE = re.compile(r"during\s+[A-Za-z]+\s*[-–]\s*[A-Za-z]+\s+(\d{4})\s+were\s+([\d.]+)\s*lakhs", re.I)
TOLERANCE_LAKH = 0.05


def find_table(pdf):
    for page in pdf.pages:
        text = page.extract_text() or ""
        if "Passengers Carried (in Lakhs)" in text or ("Pax Carried" in text and "Market Share" in text):
            tables = [t for t in page.find_tables() if len(t.rows) > 10]
            if tables:
                return max(tables, key=lambda t: len(t.rows))
    return None


def parse_table(table):
    rows = table_rows(table)
    long_format = any(t == "Pax Carried" for r in rows for t, _ in r)
    if long_format:
        first = next(i for i, r in enumerate(rows) if any(t == "Pax Carried" for t, _ in r))
    else:
        first = next(i for i, r in enumerate(rows) if sum(is_value(t) for t, _ in r) >= 2)
    columns = header_columns(rows[:first], SKIP_HEAD)
    share_x = min((c[0] for r in rows[:first] for t, c in r
                   if c is not None and re.search(r"market share", t, re.I) and not re.search(r"passengers", t, re.I)),
                  default=None)

    data = []
    for r in rows[first:]:
        texts = [t for t, _ in r]
        if long_format and "Pax Carried" not in texts:
            continue
        if not long_format and not any(PERIOD_RE.search(t.replace(" ", "")) for t in texts[:3]):
            continue
        data.append({airline_at(columns, c): t for t, c in r[1:]
                     if c is not None and is_value(t) and (long_format or share_x is None or c[0] < share_x)})
    return dict(zip(ORDER, data))


def check_quarters(periods):
    problems = []
    for q, months in QUARTERS.items():
        for airline, v in periods.get(q, {}).items():
            parts = [periods.get(m, {}).get(airline, "-") for m in months]
            if v == "-" or "-" in parts:
                continue
            if abs(sum(map(float, parts)) - float(v)) > TOLERANCE_LAKH:
                problems.append(f"{q} {airline}: months sum {sum(map(float, parts)):.2f} vs printed {v}")
    return problems


def stated_ytd(pdf):
    m = YTD_RE.search(clean(pdf.pages[0].extract_text()))
    return float(m.group(2)) if m else None


def parse_report(report):
    with pdfplumber.open(report["path"]) as pdf:
        table = find_table(pdf)
        if table is None:
            return None, ["no passengers table found"]
        periods = parse_table(table)
        problems = check_quarters(periods)
        ytd = stated_ytd(pdf)

    records = []
    for i, m in enumerate(MONTHS[:report["month"]], 1):
        for airline, v in periods.get(m, {}).items():
            if airline.lower() != "total" and v != "-":
                records.append({"airline_raw": airline, "airline_key": airline_key(airline),
                                "year": report["year"], "month": i, "pax_lakh": float(v.rstrip("*"))})
    if ytd is not None:
        summed = sum(r["pax_lakh"] for r in records)
        if abs(summed - ytd) > max(0.5, ytd * 0.002):
            problems.append(f"airlines sum to {summed:.2f} lakh, report states {ytd:.2f}")
    return records, problems


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    mapping = load_mapping()
    best, conflicts, checks, unmapped = {}, [], [], set()
    for report in reports():
        name = report["path"].name
        records, problems = parse_report(report)
        checks.append({"report": name, "status": "ok" if not problems else "; ".join(problems),
                       "rows": len(records or [])})
        for r in records or []:
            r["source_report"] = name
            r["airline"] = mapping.get(r["airline_key"])
            if r["airline"] is None:
                unmapped.add(r["airline_raw"])
                r["airline"] = r["airline_key"]
            key = (r["airline"], r["year"], r["month"])
            prev = best.get(key)
            if prev and abs(prev["pax_lakh"] - r["pax_lakh"]) > TOLERANCE_LAKH:
                conflicts.append({"airline_raw": r["airline_raw"], "year": r["year"], "month": r["month"],
                                  "report_a": prev["source_report"], "pax_lakh_a": prev["pax_lakh"],
                                  "report_b": name, "pax_lakh_b": r["pax_lakh"]})
            best[key] = r

    rows = sorted(best.values(), key=lambda r: (r["airline"], r["year"], r["month"]))
    for r in rows:
        r["fiscal_year"] = fiscal_year(r["year"], r["month"])
        r["passengers"] = round(r["pax_lakh"] * 100000)
    write_csv(OUT_DIR / "monthly_airline_passengers.csv", rows,
              ["airline", "airline_raw", "airline_key", "year", "month", "fiscal_year", "pax_lakh", "passengers",
               "source_report"])
    write_csv(LOG_DIR / "monthly_passengers_checks.csv", checks, ["report", "status", "rows"])
    write_csv(LOG_DIR / "monthly_passengers_revisions.csv", conflicts,
              ["airline_raw", "year", "month", "report_a", "pax_lakh_a", "report_b", "pax_lakh_b"])

    failed = [c for c in checks if c["status"] != "ok"]
    months = sorted({(r["year"], r["month"]) for r in rows})
    print(f"Reports: {len(checks)}  passed all checks: {len(checks) - len(failed)}")
    for c in failed:
        print(f"  {c['report']}: {c['status']}")
    print(f"Rows: {len(rows)}  airlines: {len({r['airline'] for r in rows})}"
          f"  unmapped names: {sorted(unmapped) or 'none'}")
    print(f"Months covered: {months[0][0]}-{months[0][1]:02d} .. {months[-1][0]}-{months[-1][1]:02d} ({len(months)})")
    print(f"Values revised by a later report: {len(conflicts)}")


if __name__ == "__main__":
    main()
