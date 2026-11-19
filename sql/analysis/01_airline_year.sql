-- One row per (recon_group, fiscal_year). Raw columns are summed across the group's airline_codes
-- first, then ratios are computed from the sums — averaging the per-code ratios would be wrong
-- whenever a group has more than one member (air_india_family, jet_group).
CREATE VIEW v_airline_year AS
WITH grouped AS (
    SELECT
        a.recon_group,
        y.fiscal_year,
        SUM(y.departures) AS departures,
        SUM(y.passengers) AS passengers,
        SUM(y.rpk_million) AS rpk_million,
        SUM(y.ask_million) AS ask_million,
        SUM(y.rtk_million) AS rtk_million,
        SUM(y.atk_million) AS atk_million,
        SUM(y.hours_flown) AS hours_flown,
        SUM(y.km_flown_thousand) AS km_flown_thousand
    FROM fact_yearly_airline y
    JOIN dim_airline a ON a.airline_code = y.airline_code
    GROUP BY a.recon_group, y.fiscal_year
)
SELECT
    recon_group,
    fiscal_year,
    LEFT(fiscal_year, 4)::int AS fy_start,
    departures,
    passengers,
    rpk_million,
    ask_million,
    passengers::numeric / NULLIF(SUM(passengers) OVER (PARTITION BY fiscal_year), 0) * 100 AS market_share_pct,
    rpk_million / NULLIF(ask_million, 0) * 100 AS pax_load_factor_pct,
    rtk_million / NULLIF(atk_million, 0) * 100 AS weight_load_factor_pct,
    km_flown_thousand * 1000 / NULLIF(hours_flown, 0) AS avg_speed_kmh,
    km_flown_thousand * 1000 / NULLIF(departures, 0) AS avg_stage_distance_km,
    LAG(passengers) OVER (PARTITION BY recon_group ORDER BY fiscal_year) AS passengers_prior_year,
    (passengers::numeric / NULLIF(LAG(passengers) OVER (PARTITION BY recon_group ORDER BY fiscal_year), 0) - 1)
        * 100 AS passenger_yoy_growth_pct,
    (rpk_million / NULLIF(LAG(rpk_million) OVER (PARTITION BY recon_group ORDER BY fiscal_year), 0) - 1)
        * 100 AS rpk_yoy_growth_pct
FROM grouped;
