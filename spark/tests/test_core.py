"""Starter tests (Phase 1). Phase 2 expands these."""
import pytest

import airlines_spark as a


def _hist(spark, rows):
    return spark.createDataFrame(rows, ["airline", "fiscal_year", "passengers"])


def _mapping(spark, rows):
    return spark.createDataFrame(rows, ["source", "source_key", "airline", "recon_group"])


def test_family_grouping_changes_hhi_with_known_arithmetic(spark):
    # a1+a2 are one family (60% share), b is 40%. Grouped HHI = 60^2 + 40^2 = 5200.
    # Ungrouped shares are 30/30/40 -> 900 + 900 + 1600 = 3400.
    hist = _hist(spark, [("a1", "2020-21", 30), ("a2", "2020-21", 30), ("b", "2020-21", 40)])
    mapping = _mapping(spark, [("yearly", "a1", "a1", "fam"), ("yearly", "a2", "a2", "fam"),
                               ("yearly", "b", "b", "b")])
    agg = _hist(spark, [("all_scheduled_indian_airlines", "2020-21", 100)])
    out = a.run_analysis(hist, agg, mapping)
    grouped = out["concentration"].collect()[0]
    assert grouped["hhi"] == pytest.approx(5200.0)
    assert out["ungrouped"].collect()[0]["ungrouped_airline_hhi"] == pytest.approx(3400.0)
    assert out["reconciliation"].collect()[0]["status"] == "within_tolerance"


def test_negative_passengers_fail_loudly(spark):
    hist = _hist(spark, [("a", "2020-21", -5)])
    with pytest.raises(a.DataValidationError, match="negative or invalid"):
        a.validate_passengers(hist, "test")


def test_unmapped_airline_fails(spark):
    hist = _hist(spark, [("ghost", "2020-21", 5)])
    lookup = a.build_mapping_lookup(_mapping(spark, [("yearly", "a", "a", "a")]))
    with pytest.raises(a.DataValidationError, match="no yearly mapping"):
        a.build_group_year(a.validate_passengers(hist, "t"), lookup)


def test_cli_runs_on_committed_data(spark, capsys):
    assert a.main([], spark=spark) == 0
    assert "Concentration by fiscal year" in capsys.readouterr().out
