CREATE VIEW v_airline_lifecycle AS
WITH yearly_span AS (
    SELECT airline_code, MIN(fiscal_year) AS first_fy, MAX(fiscal_year) AS last_fy, COUNT(*) AS n_years
    FROM fact_yearly_airline GROUP BY airline_code
),
monthly_span AS (
    SELECT airline_code, MIN(year * 100 + month) AS first_ym, MAX(year * 100 + month) AS last_ym
    FROM fact_monthly_passengers GROUP BY airline_code
)
SELECT
    a.airline_code,
    a.airline_name,
    a.recon_group,
    y.first_fy,
    y.last_fy,
    y.n_years,
    m.first_ym / 100 || '-' || LPAD((m.first_ym % 100)::text, 2, '0') AS first_month,
    m.last_ym / 100 || '-' || LPAD((m.last_ym % 100)::text, 2, '0') AS last_month,
    y.last_fy < (SELECT MAX(fiscal_year) FROM fact_yearly_airline) AS looks_exited
FROM dim_airline a
LEFT JOIN yearly_span y ON y.airline_code = a.airline_code
LEFT JOIN monthly_span m ON m.airline_code = a.airline_code
WHERE a.airline_code <> 'jet_group';

-- Known mergers (DGCA keeps the merged airline's own historical rows under its own code, so this
-- is background for the dashboard, not something derivable from the fact tables alone).
CREATE TABLE known_merger (
    airline_code text PRIMARY KEY REFERENCES dim_airline (airline_code),
    merged_into text NOT NULL REFERENCES dim_airline (airline_code),
    merger_fiscal_year text NOT NULL,
    notes text
);
INSERT INTO known_merger VALUES
    ('vistara', 'air_india', '2024-25', 'Merged into Air India, Nov 2024'),
    ('aix_connect', 'air_india_express', '2024-25', 'Merged into Air India Express, Oct 2024');
