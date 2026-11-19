CREATE VIEW v_covid_recovery AS
WITH baseline AS (
    SELECT recon_group, passengers AS baseline_passengers
    FROM v_airline_year WHERE fiscal_year = '2019-20'
)
SELECT
    g.recon_group,
    g.fiscal_year,
    g.fy_start,
    g.passengers,
    b.baseline_passengers,
    g.passengers::numeric / NULLIF(b.baseline_passengers, 0) * 100 AS pct_of_pre_covid_baseline,
    MIN(g.fiscal_year) FILTER (WHERE g.passengers >= b.baseline_passengers AND g.fiscal_year > '2019-20')
        OVER (PARTITION BY g.recon_group) AS first_fy_at_or_above_baseline
FROM v_airline_year g
JOIN baseline b ON b.recon_group = g.recon_group
WHERE g.fiscal_year >= '2019-20';
