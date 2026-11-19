"""Synthetic-data unit tests for the Spark transformations and validation rules."""
import pytest

import airlines_spark as a

AGG = "all_scheduled_indian_airlines"


def hist(spark, rows):
    return spark.createDataFrame(rows, ["airline", "fiscal_year", "passengers"])


def mapping(spark, rows):
    return spark.createDataFrame(rows, ["source", "source_key", "airline", "recon_group"])


def simple_map(spark, *pairs):
    return mapping(spark, [("yearly", n, n, g) for n, g in pairs])


# ---- shares and HHI ------------------------------------------------------- #
def test_shares_sum_to_100_for_every_valid_year(spark):
    h = hist(spark, [("a", "2020-21", 10), ("b", "2020-21", 30), ("a", "2021-22", 5), ("b", "2021-22", 95)])
    m = simple_map(spark, ("a", "a"), ("b", "b"))
    shares = a.run_analysis(h, hist(spark, [(AGG, "2020-21", 40)]), m)["shares"]
    sums = {r["fiscal_year"]: r["s"] for r in shares.groupBy("fiscal_year").sum("share_pct")
            .withColumnRenamed("sum(share_pct)", "s").collect()}
    assert sums == {"2020-21": pytest.approx(100.0), "2021-22": pytest.approx(100.0)}


def test_hhi_known_values_per_year_and_top_share(spark):
    # 2020-21: 50/50 -> 5000. 2021-22: 100% one airline -> 10000.
    h = hist(spark, [("a", "2020-21", 50), ("b", "2020-21", 50), ("a", "2021-22", 70), ("b", "2021-22", 0)])
    m = simple_map(spark, ("a", "a"), ("b", "b"))
    conc = {r["fiscal_year"]: r for r in a.run_analysis(h, hist(spark, [(AGG, "2020-21", 100)]), m)["concentration"].collect()}
    assert conc["2020-21"]["hhi"] == pytest.approx(5000.0)
    assert conc["2021-22"]["hhi"] == pytest.approx(10000.0)
    assert conc["2021-22"]["active_groups"] == 1          # zero-passenger airline excluded, as in SQL
    assert conc["2021-22"]["top_share_pct"] == pytest.approx(100.0)


def test_fiscal_years_are_isolated(spark):
    # Huge 2021-22 traffic must not change 2020-21 shares.
    base = [("a", "2020-21", 20), ("b", "2020-21", 80)]
    m = simple_map(spark, ("a", "a"), ("b", "b"))
    agg = hist(spark, [(AGG, "2020-21", 100)])
    alone = a.run_analysis(hist(spark, base), agg, m)["concentration"].filter("fiscal_year='2020-21'").collect()[0]["hhi"]
    both = a.run_analysis(hist(spark, base + [("a", "2021-22", 10**9)]), agg, m)["concentration"] \
        .filter("fiscal_year='2020-21'").collect()[0]["hhi"]
    assert alone == pytest.approx(both) == pytest.approx(20**2 + 80**2)


def test_several_source_keys_for_one_canonical_airline_do_not_multiply_rows(spark):
    # Mirrors go_air/go_first: two mapping rows, one canonical airline, one history row.
    m = mapping(spark, [("yearly", "go_air", "go_first", "go_first"), ("yearly", "go_first", "go_first", "go_first"),
                        ("monthly", "goair", "go_first", "go_first")])
    out = a.run_analysis(hist(spark, [("go_first", "2020-21", 40)]), hist(spark, [(AGG, "2020-21", 40)]), m)
    assert out["concentration"].collect()[0]["total_passengers"] == 40


def test_grouping_ties_are_deterministic(spark):
    h = hist(spark, [("b", "2020-21", 50), ("a", "2020-21", 50)])
    conc = a.run_analysis(h, hist(spark, [(AGG, "2020-21", 100)]), simple_map(spark, ("a", "a"), ("b", "b")))
    assert conc["concentration"].collect()[0]["top_group"] == "a"   # tie broken alphabetically


# ---- validation ----------------------------------------------------------- #
@pytest.mark.parametrize("bad", [None, -1.0, "abc", "", float("nan"), "-5", "inf"])
def test_invalid_passenger_values_fail(spark, bad):
    df = spark.createDataFrame([("a", "2020-21", bad)], "airline string, fiscal_year string, passengers string"
                               if isinstance(bad, (str, type(None))) else
                               "airline string, fiscal_year string, passengers double")
    with pytest.raises(a.DataValidationError, match="invalid passenger"):
        a.validate_passengers(df, "t")


@pytest.mark.parametrize("year", [None, "", "2020", "FY2020-21"])
def test_bad_fiscal_year_fails(spark, year):
    df = spark.createDataFrame([("a", year, 5)], "airline string, fiscal_year string, passengers int")
    with pytest.raises(a.DataValidationError, match="fiscal_year"):
        a.validate_passengers(df, "t")


def test_duplicate_airline_year_fails(spark):
    with pytest.raises(a.DataValidationError, match="duplicate"):
        a.validate_passengers(hist(spark, [("a", "2020-21", 1), ("a", "2020-21", 2)]), "t")


def test_whitespace_is_trimmed_before_duplicate_detection(spark):
    with pytest.raises(a.DataValidationError, match="duplicate"):
        a.validate_passengers(hist(spark, [("a", "2020-21", 1), (" a ", "2020-21 ", 2)]), "t")


def test_conflicting_mapping_fails(spark):
    m = mapping(spark, [("yearly", "x", "x", "g1"), ("yearly", "x2", "x", "g2")])
    with pytest.raises(a.DataValidationError, match="more than one recon_group"):
        a.build_mapping_lookup(m)


def test_blank_group_in_mapping_fails(spark):
    with pytest.raises(a.DataValidationError, match="blank"):
        a.build_mapping_lookup(mapping(spark, [("yearly", "x", "x", "")]))


def test_unmapped_airline_names_are_reported(spark):
    lookup = a.build_mapping_lookup(simple_map(spark, ("a", "a")))
    with pytest.raises(a.DataValidationError, match="ghost"):
        a.build_group_year(a.validate_passengers(hist(spark, [("ghost", "2020-21", 1)]), "t"), lookup)


def test_only_yearly_mapping_rows_are_used(spark):
    m = mapping(spark, [("monthly", "x", "x", "wrong"), ("yearly", "x", "x", "right")])
    assert [r["recon_group"] for r in a.build_mapping_lookup(m).collect()] == ["right"]


def test_zero_total_year_is_excluded_and_reported_not_divided(spark):
    h = hist(spark, [("a", "2020-21", 0), ("b", "2020-21", 0), ("a", "2021-22", 10)])
    out = a.run_analysis(h, hist(spark, [(AGG, "2021-22", 10)]), simple_map(spark, ("a", "a"), ("b", "b")))
    assert [r["fiscal_year"] for r in out["concentration"].collect()] == ["2021-22"]
    assert [r["fiscal_year"] for r in out["zero_total_years"].collect()] == ["2020-21"]


def test_duplicate_aggregate_years_fail(spark):
    with pytest.raises(a.DataValidationError, match="duplicate"):
        a.validate_passengers(hist(spark, [(AGG, "2020-21", 1), (AGG, "2020-21", 1)]), "agg", allow_null=True)


# ---- reconciliation ------------------------------------------------------- #
def test_pct_difference_is_signed_and_correct(spark):
    totals = spark.createDataFrame([("2020-21", 90.0), ("2021-22", 110.0)], ["fiscal_year", "spark_passengers"])
    agg = a.validate_passengers(hist(spark, [(AGG, "2020-21", 100), (AGG, "2021-22", 100)]), "agg")
    rows = {r["fiscal_year"]: r for r in a.reconcile_with_aggregate(totals, agg, 1.0).collect()}
    assert rows["2020-21"]["diff_pct"] == pytest.approx(-10.0)
    assert rows["2021-22"]["diff_pct"] == pytest.approx(10.0)
    assert rows["2020-21"]["status"] == rows["2021-22"]["status"] == "outside_tolerance"


def test_tolerance_boundary_and_other_series_are_ignored(spark):
    totals = spark.createDataFrame([("2020-21", 99.0)], ["fiscal_year", "spark_passengers"])
    agg = a.validate_passengers(hist(spark, [(AGG, "2020-21", 100), ("scheduled_private_airlines", "2020-21", 1)]), "agg")
    row = a.reconcile_with_aggregate(totals, agg, 1.0).collect()[0]
    assert row["aggregate_passengers"] == 100 and row["status"] == "within_tolerance"


def test_full_outer_join_keeps_years_missing_on_either_side(spark):
    totals = spark.createDataFrame([("2019-20", 5.0), ("2020-21", 5.0)], ["fiscal_year", "spark_passengers"])
    agg = a.validate_passengers(hist(spark, [(AGG, "2020-21", 5), (AGG, "2018-19", 7)]), "agg")
    st = {r["fiscal_year"]: r["status"] for r in a.reconcile_with_aggregate(totals, agg).collect()}
    assert st == {"2018-19": "missing_in_airline_data", "2019-20": "missing_in_aggregate", "2020-21": "within_tolerance"}


def test_zero_or_null_aggregate_does_not_divide(spark):
    totals = spark.createDataFrame([("2020-21", 5.0), ("2021-22", 5.0)], ["fiscal_year", "spark_passengers"])
    agg = a.validate_passengers(
        spark.createDataFrame([(AGG, "2020-21", "0"), (AGG, "2021-22", None)], "airline string, fiscal_year string, passengers string"),
        "agg", allow_null=True)
    rows = {r["fiscal_year"]: r for r in a.reconcile_with_aggregate(totals, agg).collect()}
    assert rows["2020-21"]["status"] == "zero_aggregate" and rows["2020-21"]["diff_pct"] is None
    assert rows["2021-22"]["status"] == "missing_in_aggregate"


def test_rerun_gives_identical_results(spark):
    h = hist(spark, [("a", "2020-21", 30), ("b", "2020-21", 70), ("a", "2021-22", 1), ("b", "2021-22", 2)])
    m, g = simple_map(spark, ("a", "a"), ("b", "b")), hist(spark, [(AGG, "2020-21", 100)])
    first = [a.run_analysis(h, g, m)[k].collect() for k in ("concentration", "reconciliation")]
    second = [a.run_analysis(h, g, m)[k].collect() for k in ("concentration", "reconciliation")]
    assert first == second
