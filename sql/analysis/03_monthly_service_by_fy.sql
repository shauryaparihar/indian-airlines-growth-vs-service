-- Passenger-weighted average per (recon_group, fiscal_year, metric). Weighting only changes the
-- result for groups with more than one airline_code (air_india_family, jet_group); every other
-- group has exactly one code, so the weighted and simple average are the same there.
-- jet_group's own combined rows (complaints/OTP reported as "Jet Airways + JetLite") are weighted
-- by that month's Jet Airways + JetLite passengers combined, since there is no separate
-- passengers row for the pseudo-code itself.
CREATE VIEW v_monthly_service_by_fy AS
WITH weighted AS (
    SELECT
        a.recon_group,
        s.fiscal_year,
        s.metric,
        s.value,
        COALESCE(
            (SELECT p.passengers FROM fact_monthly_passengers p
             WHERE p.airline_code = s.airline_code AND p.year = s.year AND p.month = s.month),
            (SELECT SUM(p.passengers) FROM fact_monthly_passengers p
             WHERE p.airline_code IN ('jet_airways', 'jetlite') AND p.year = s.year AND p.month = s.month
               AND s.airline_code = 'jet_group'),
            0
        ) AS weight
    FROM fact_monthly_service s
    JOIN dim_airline a ON a.airline_code = s.airline_code
)
SELECT
    recon_group,
    fiscal_year,
    LEFT(fiscal_year, 4)::int AS fy_start,
    metric,
    SUM(value * weight) / NULLIF(SUM(weight), 0) AS weighted_avg,
    AVG(value) AS simple_avg,
    COUNT(*) AS n_airline_months
FROM weighted
GROUP BY recon_group, fiscal_year, metric;

CREATE VIEW v_monthly_load_factor_by_fy AS
SELECT
    a.recon_group,
    f.fiscal_year,
    AVG(f.pax_load_factor_pct) AS avg_pax_load_factor_pct,
    COUNT(*) AS n_airline_months
FROM fact_monthly_load_factor f
JOIN dim_airline a ON a.airline_code = f.airline_code
GROUP BY a.recon_group, f.fiscal_year;

CREATE VIEW v_otp_scope_by_fy AS
SELECT
    fiscal_year,
    LEFT(fiscal_year, 4)::int AS fy_start,
    ARRAY_AGG(DISTINCT otp_airports ORDER BY otp_airports) AS otp_airport_scopes_seen,
    ARRAY_TO_STRING(ARRAY_AGG(DISTINCT otp_airports ORDER BY otp_airports), ' + ') || ' airports' AS scope_label,
    COUNT(DISTINCT otp_airports) > 1 AS mixed_scope
FROM fact_monthly_market_service
WHERE otp_airports IS NOT NULL
GROUP BY fiscal_year;

-- Market-wide cancellation and complaints per fiscal year: plain average of the monthly figures,
-- since DGCA prints only the monthly rates (no passenger base to weight by).
CREATE VIEW v_market_service_by_fy AS
SELECT
    fiscal_year,
    LEFT(fiscal_year, 4)::int AS fy_start,
    AVG(overall_cancellation_rate_pct) AS avg_cancellation_rate_pct,
    AVG(complaints_per_10k) AS avg_complaints_per_10k,
    SUM(total_complaints) AS total_complaints,
    COUNT(*) AS n_months
FROM fact_monthly_market_service
GROUP BY fiscal_year;
