"""Parse airline-wise cancellation rate, complaints per 10,000 passengers and OTP from each monthly report."""

import csv
import re

import pdfplumber

from monthly_common import LOG_DIR, OUT_DIR, airline_key, clean, fiscal_year, load_mapping, reports, write_csv

PAIR_RE = re.compile(r"^([A-Za-z][A-Za-z .+&()'/-]*?)\s*(\*?)\s+(-?\d+(?:\.\d+)?)\s*%?$")
AXIS_RE = re.compile(r"^(?:-?\d+(?:\.\d+)?\s+){3,}-?\d+(?:\.\d+)?$")
NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
LIST_INTRO = r"details\s+(?:of\s+cancellations\s+)?are\s+as\s+follows\s*:?"
SECTIONS = {
    "cancellation_rate_pct": (r"^Cancellations\b", LIST_INTRO),
    "complaints_per_10k": (r"Passenger\W+Complaints\W+during", LIST_INTRO),
    "otp_pct": (r"On\W?\w?Time\W+Performance\W+\(?Scheduled\W+Domestic", r"OTP\s+at\s+\w+\s+\w+\s+Airports"),
}
OTP_SCOPE = {"four metro": 4, "six metro": 6, "ten major": 10}
OVERALL = {
    "overall_cancellation_rate_pct": r"overall\s+cancellation\s+rate.*?has\s+been\s*([\d.]+)\s*%",
    "total_complaints": r"a\s+total\s+of\s*([\d,]+)\s*passenger",
    "complaints_per_10k": r"per\s+10,000\s+passengers.*?has\s+been\s*(?:around\s*)?([\d.]+)",
}
COMPLAINT_CHECK_TOLERANCE = 0.15
COMBINED = {"jet_group": ["jet_airways", "jetlite"]}


def fix_encoding(text):
    # Mar 2020 (revised) uses a font where spaces come out as $ " & ' and hyphens as @
    if text.count("$") > 20:
        text = re.sub(r"[$\"&']", " ", text).replace("@", "-")
    return text


def section_pairs(text, start_re, list_re):
    m = re.search(start_re, text, re.M)
    if not m:
        return None
    rest = text[m.end():]
    intro = re.search(list_re, rest, re.I | re.S)
    if not intro:
        return None
    pairs, names, nums = [], [], []
    for line in (clean(l) for l in rest[intro.end():].split("\n")):
        if not line:
            continue
        if AXIS_RE.match(line) or re.match(r"^(Cancellation\W+Rate|No\.\W+of\W+Complaints|OTP\W+\()", line):
            break
        pm = PAIR_RE.match(line)
        if pm:
            pairs.append((pm.group(1).strip(), pm.group(2) == "*", float(pm.group(3))))
        elif NUM_RE.match(line):
            nums.append(float(line))
        elif re.match(r"^[A-Za-z]", line):
            names.append(line.rstrip("*").strip())
    if not pairs and names and len(names) == len(nums):
        pairs = [(n, False, v) for n, v in zip(names, nums)]
    return pairs


def overall_figures(text):
    flat = clean(text)
    out = {}
    for name, pattern in OVERALL.items():
        m = re.search(pattern, flat, re.I)
        if m:
            out[name] = float(m.group(1).replace(",", "").rstrip("."))
    scope = re.search(r"OTP\s+at\s+(\w+\s+\w+)\s+Airports", flat, re.I)
    out["otp_airports"] = OTP_SCOPE.get(scope.group(1).lower()) if scope else None
    return out


def passengers_by_month():
    with (OUT_DIR / "monthly_airline_passengers.csv").open(encoding="utf-8") as f:
        return {(r["airline"], int(r["year"]), int(r["month"])): float(r["passengers"]) for r in csv.DictReader(f)}


def complaint_check(rows, stated_total, pax):
    implied, missing = 0.0, []
    for r in rows:
        parts = COMBINED.get(r["airline"], [r["airline"]])
        found = [pax[(a, r["year"], r["month"])] for a in parts if (a, r["year"], r["month"]) in pax]
        p = sum(found) if found else None
        if p is None:
            missing.append(r["airline_raw"])
        else:
            implied += r["value"] * p / 10000
    if missing or not stated_total:
        return None, implied
    return abs(implied - stated_total) / stated_total <= COMPLAINT_CHECK_TOLERANCE, implied


def main():
    mapping = load_mapping()
    pax = passengers_by_month()
    rows, market, checks, unmapped = [], [], [], set()
    for report in reports():
        name = report["path"].name
        with pdfplumber.open(report["path"]) as pdf:
            text = fix_encoding("\n".join((p.extract_text() or "") for p in pdf.pages[:12]))
        overall = overall_figures(text)
        problems, report_rows = [], []
        for metric, (start_re, list_re) in SECTIONS.items():
            pairs = section_pairs(text, start_re, list_re)
            if not pairs or len(pairs) < 3:
                problems.append(f"{metric}: {len(pairs or [])} airlines found")
                continue
            for raw, footnote, value in pairs:
                if metric != "complaints_per_10k" and not 0 <= value <= 100:
                    problems.append(f"{metric} {raw}: {value} out of range")
                    continue
                airline = mapping.get(airline_key(raw))
                if airline is None:
                    unmapped.add(raw)
                    airline = airline_key(raw)
                report_rows.append({"airline": airline, "airline_raw": raw, "year": report["year"],
                                    "month": report["month"],
                                    "fiscal_year": fiscal_year(report["year"], report["month"]),
                                    "metric": metric, "value": value, "footnote": footnote,
                                    "otp_airports": overall["otp_airports"] if metric == "otp_pct" else "",
                                    "source_report": name})
        complaints = [r for r in report_rows if r["metric"] == "complaints_per_10k"]
        ok, implied = complaint_check(complaints, overall.get("total_complaints"), pax)
        if ok is False:
            problems.append(f"complaints: rates x passengers imply {implied:.0f}, report states "
                            f"{overall['total_complaints']:.0f}")
        rows += report_rows
        market.append({"year": report["year"], "month": report["month"],
                       "fiscal_year": fiscal_year(report["year"], report["month"]), **overall,
                       "source_report": name})
        checks.append({"report": name, "status": "; ".join(problems) or "ok",
                       "complaint_check": {True: "ok", False: "mismatch", None: "not checked"}[ok]})

    rows.sort(key=lambda r: (r["metric"], r["airline"], r["year"], r["month"]))
    write_csv(OUT_DIR / "monthly_airline_service.csv", rows,
              ["airline", "airline_raw", "year", "month", "fiscal_year", "metric", "value", "footnote",
               "otp_airports", "source_report"])
    write_csv(OUT_DIR / "monthly_market_service.csv", market,
              ["year", "month", "fiscal_year", "overall_cancellation_rate_pct", "total_complaints",
               "complaints_per_10k", "otp_airports", "source_report"])
    write_csv(LOG_DIR / "monthly_service_checks.csv", checks, ["report", "status", "complaint_check"])

    failed = [c for c in checks if c["status"] != "ok"]
    print(f"Reports: {len(checks)}  all sections ok: {len(checks) - len(failed)}")
    for c in failed:
        print(f"  {c['report']}: {c['status']}")
    for metric in SECTIONS:
        n = [r for r in rows if r["metric"] == metric]
        print(f"{metric:24s} rows {len(n):5d}  reports {len({r['source_report'] for r in n})}")
    cc = [c["complaint_check"] for c in checks]
    print(f"Complaint totals check: ok {cc.count('ok')}, mismatch {cc.count('mismatch')}, "
          f"not checked {cc.count('not checked')}")
    scopes = {}
    for m in market:
        scopes.setdefault(m["otp_airports"], []).append(f"{m['year']}-{m['month']:02d}")
    for s, months in scopes.items():
        print(f"OTP scope {s} airports: {months[0]} .. {months[-1]} ({len(months)} reports)")
    print(f"Unmapped names: {sorted(unmapped) or 'none'}")


if __name__ == "__main__":
    main()
