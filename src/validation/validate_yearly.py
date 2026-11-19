"""Recompute the Table 1.07 ratios from Table 1.04 raw columns and compare to DGCA's printed values."""

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
LOG_DIR = PROJECT_ROOT / "logs"
TOLERANCE = 0.005


def recompute(r):
    departures, hours, km = float(r["departures"]), float(r["hours_flown"]), float(r["km_flown_thousand"])
    passengers, rpk, ask = float(r["passengers"]), float(r["rpk_million"]), float(r["ask_million"])
    rtk, atk = float(r["rtk_million"]), float(r["atk_million"])
    out = {}
    if ask:
        out["pax_load_factor_pct"] = rpk / ask * 100
    if atk:
        out["weight_load_factor_pct"] = rtk / atk * 100
    if hours:
        out["avg_speed_kmh"] = km * 1000 / hours
    if departures:
        out["avg_stage_distance_km"] = km * 1000 / departures
        out["avg_pax_per_departure"] = passengers / departures
    if passengers:
        out["avg_distance_per_pax_km000"] = rpk * 1000 / passengers
    return out


def compare(key, computed, printed, source, mismatches):
    for metric, dgca_value in printed.items():
        value = computed.get(metric)
        dgca_value = float(dgca_value)
        if value is None or not dgca_value:
            continue
        diff = abs(value - dgca_value) / abs(dgca_value)
        if diff > TOLERANCE:
            mismatches.append({**key, "metric": metric, "source": source,
                               "computed": value, "dgca_printed": dgca_value, "pct_diff": diff * 100})


def main():
    history = list(csv.DictReader(open(PROCESSED / "yearly_airline_domestic_history.csv", encoding="utf-8")))
    coefficients = {(r["airline"], r["fiscal_year"]): r
                    for r in csv.DictReader(open(PROCESSED / "yearly_airline_coefficients.csv", encoding="utf-8"))}

    mismatches = []
    for r in history:
        key = {"airline": r["airline"], "fiscal_year": r["fiscal_year"]}
        computed = recompute(r)
        compare(key, computed, {"pax_load_factor_pct": r["pax_load_factor_pct"],
                                "weight_load_factor_pct": r["weight_load_factor_pct"]},
                "domestic_history_own_ratio", mismatches)
        coeff = coefficients.get((r["airline"], r["fiscal_year"]))
        if coeff:
            compare(key, computed,
                    {m: coeff[m] for m in ("pax_load_factor_pct", "weight_load_factor_pct", "avg_speed_kmh",
                                           "avg_stage_distance_km", "avg_pax_per_departure",
                                           "avg_distance_per_pax_km000")},
                    "coefficients_table", mismatches)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = LOG_DIR / "yearly_validation_mismatches.csv"
    if mismatches:
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["airline", "fiscal_year", "metric", "source",
                                                    "computed", "dgca_printed", "pct_diff"])
            writer.writeheader()
            writer.writerows(sorted(mismatches, key=lambda m: -m["pct_diff"]))

    print(f"Rows checked: {len(history)}")
    print(f"Mismatches beyond {TOLERANCE * 100:.1f}%: {len(mismatches)}"
          + (f" -> logs/{out_path.name}" if mismatches else ""))
    by_airline = {}
    for m in mismatches:
        by_airline.setdefault(m["airline"], 0)
        by_airline[m["airline"]] += 1
    for airline, count in sorted(by_airline.items(), key=lambda kv: -kv[1]):
        print(f"  {airline:28s} {count}")


if __name__ == "__main__":
    main()
