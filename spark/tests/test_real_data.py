"""Integration test over the committed CSVs, checked by an independent pure-Python calculation.

The Python reference below shares no code with airlines_spark.py: it reads the CSVs with the
csv module, groups by recon_group, and applies the SQL formulas by hand.
"""
import csv
from collections import defaultdict

import pytest

import airlines_spark as a

DATA = a.DEFAULT_DATA_DIR


def _rows(rel):
    with open(DATA / rel, newline="") as fh:
        return list(csv.DictReader(fh))


def reference_hhi():
    group = {}
    for r in _rows(a.MAPPING_FILE):
        if r["source"] == "yearly":
            group[r["airline"]] = r["recon_group"]
    totals = defaultdict(float)
    for r in _rows(a.HISTORY_FILE):
        totals[(r["fiscal_year"], group[r["airline"]])] += float(r["passengers"])
    years = defaultdict(dict)
    for (y, g), p in totals.items():
        if p > 0:
            years[y][g] = p
    out = {}
    for y, groups in years.items():
        tot = sum(groups.values())
        shares = sorted((100 * p / tot for p in groups.values()), reverse=True)
        out[y] = {"hhi": sum(s * s for s in shares), "top": shares[0], "top3": sum(shares[:3]),
                  "groups": len(shares), "total": tot}
    return out


@pytest.fixture(scope="module")
def result(spark):
    h, g, m = a.read_inputs(spark, DATA)
    return a.run_analysis(h, g, m)


def test_spark_matches_independent_python_for_every_year(result):
    ref = reference_hhi()
    got = {r["fiscal_year"]: r for r in result["concentration"].collect()}
    assert set(got) == set(ref)
    for y, exp in ref.items():
        assert got[y]["hhi"] == pytest.approx(exp["hhi"], rel=1e-9), y
        assert got[y]["top_share_pct"] == pytest.approx(exp["top"], rel=1e-9), y
        assert got[y]["top3_share_pct"] == pytest.approx(exp["top3"], rel=1e-9), y
        assert got[y]["active_groups"] == exp["groups"], y
        assert got[y]["total_passengers"] == pytest.approx(exp["total"]), y


@pytest.mark.parametrize("year,readme_value", [("2013-14", 2242), ("2024-25", 4818)])
def test_readme_hhi_values_reproduced(result, year, readme_value):
    # README prints whole numbers, so the tolerance is the rounding half-width (0.5).
    hhi = {r["fiscal_year"]: r["hhi"] for r in result["concentration"].collect()}[year]
    assert hhi == pytest.approx(readme_value, abs=0.5)


def test_readme_share_claims(result):
    row = {r["fiscal_year"]: r for r in result["concentration"].collect()}["2024-25"]
    assert row["top_group"] == "indigo"
    assert row["top_share_pct"] == pytest.approx(63.0, abs=0.05)
    assert row["top3_share_pct"] == pytest.approx(96.3, abs=0.05)


def test_grouping_matters_on_real_data(result):
    grouped = {r["fiscal_year"]: r["hhi"] for r in result["concentration"].collect()}
    ungrouped = {r["fiscal_year"]: r["ungrouped_airline_hhi"] for r in result["ungrouped"].collect()}
    assert ungrouped["2024-25"] < grouped["2024-25"] - 100   # Air India family merge raises HHI


def test_reconciliation_status_by_period(result):
    rec = {r["fiscal_year"]: r for r in result["reconciliation"].collect()}
    for y in ("2013-14", "2014-15", "2015-16", "2016-17", "2017-18"):
        assert rec[y]["status"] == "within_tolerance" and rec[y]["diff_pct"] == pytest.approx(0.0)
    for y in ("2007-08", "2008-09", "2009-10", "2010-11", "2011-12", "2012-13"):
        assert rec[y]["status"] == "outside_tolerance" and rec[y]["diff_pct"] < 0   # airline file under-covers
    for y in ("2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"):
        assert rec[y]["status"] == "missing_in_aggregate"   # all_scheduled series ends 2017-18


def test_no_zero_total_years_in_committed_data(result):
    assert result["zero_total_years"].count() == 0


def test_spark_matches_postgres_view_snapshot(result):
    """Snapshot of `SELECT ... FROM v_market_concentration` run on PostgreSQL 17 (docker compose)
    after load_postgres.py + build_views.py on 2026-11-20. Regenerate it only by re-running the SQL.
    """
    from pathlib import Path
    snap = Path(__file__).parent / "reference" / "sql_v_market_concentration.csv"
    sql = {r["fiscal_year"]: r for r in csv.DictReader(open(snap, newline=""))}
    got = {r["fiscal_year"]: r for r in result["concentration"].collect()}
    assert set(sql) == set(got) and len(sql) == 18
    for y, s in sql.items():
        assert got[y]["total_passengers"] == pytest.approx(float(s["total_passengers"]), rel=1e-12), y
        assert got[y]["active_groups"] == int(s["active_airlines"]), y
        assert got[y]["top_share_pct"] == pytest.approx(float(s["top_airline_share_pct"]), rel=1e-9), y
        assert got[y]["top3_share_pct"] == pytest.approx(float(s["top3_share_pct"]), rel=1e-9), y
        assert got[y]["hhi"] == pytest.approx(float(s["hhi"]), rel=1e-9), y
