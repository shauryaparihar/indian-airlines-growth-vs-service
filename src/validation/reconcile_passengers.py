"""Compare monthly-report passengers (summed by fiscal year) with the yearly Table 1.04 passengers."""

import csv
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
LOG_DIR = PROJECT_ROOT / "logs"
TOLERANCE = 0.01
NO_OPERATIONS = {"2020-21": 1}


def read(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    group_of = {r["airline"]: r["recon_group"] for r in read(PROJECT_ROOT / "data" / "reference" / "airline_mapping.csv")}

    monthly, months, unmapped = defaultdict(float), defaultdict(set), set()
    for r in read(PROCESSED / "monthly_airline_passengers.csv"):
        group = group_of.get(r["airline"])
        if not group:
            unmapped.add(r["airline_raw"])
            continue
        monthly[(group, r["fiscal_year"])] += float(r["passengers"])
        months[r["fiscal_year"]].add(int(r["month"]))

    yearly = defaultdict(float)
    for r in read(PROCESSED / "yearly_airline_domestic_history.csv"):
        group = group_of.get(r["airline"])
        if not group:
            unmapped.add(r["airline"])
            continue
        yearly[(group, r["fiscal_year"])] += float(r["passengers"])

    rows = []
    for key in sorted(set(monthly) & set(yearly)):
        group, fy = key
        if len(months[fy]) + NO_OPERATIONS.get(fy, 0) < 12:
            continue
        diff = (monthly[key] - yearly[key]) / yearly[key] if yearly[key] else None
        rows.append({"recon_group": group, "fiscal_year": fy, "monthly_passengers": round(monthly[key]),
                     "yearly_passengers": round(yearly[key]),
                     "pct_diff": round(diff * 100, 2) if diff is not None else "",
                     "within_tolerance": diff is not None and abs(diff) <= TOLERANCE})

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "monthly_vs_yearly_passengers.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    big = [r for r in rows if r["yearly_passengers"] >= 1_000_000]
    ok = sum(r["within_tolerance"] for r in big)
    print(f"Unmapped names: {sorted(unmapped) or 'none'}")
    print(f"Airline-years compared: {len(rows)}  (with >= 10 lakh passengers: {len(big)}, within {TOLERANCE:.0%}: {ok})")
    for r in big:
        if not r["within_tolerance"]:
            print(f"  {r['recon_group']:18s} {r['fiscal_year']}  monthly {r['monthly_passengers']:>11,}  "
                  f"yearly {r['yearly_passengers']:>11,}  {r['pct_diff']:+.2f}%")


if __name__ == "__main__":
    main()
