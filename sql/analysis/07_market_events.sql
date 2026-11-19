-- Mergers (hand-entered in known_merger) and exits of airlines with at least 5 years of yearly data.
-- JetLite is left out because it is reported together with Jet Airways.
CREATE VIEW v_market_events AS
SELECT
    CASE WHEN m.merger_fiscal_year IS NOT NULL THEN 'Merger' END AS event_type,
    a.airline_name,
    m.merger_fiscal_year AS event_fiscal_year,
    LEFT(m.merger_fiscal_year, 4)::int AS fy_start,
    'Merged into ' || t.airline_name AS detail
FROM known_merger m
JOIN dim_airline a ON a.airline_code = m.airline_code
JOIN dim_airline t ON t.airline_code = m.merged_into
UNION ALL
SELECT
    'Exit',
    l.airline_name,
    l.last_fy,
    LEFT(l.last_fy, 4)::int,
    'Last fiscal year with yearly data: ' || l.last_fy
FROM v_airline_lifecycle l
WHERE l.looks_exited AND l.n_years >= 5 AND l.airline_code <> 'jetlite';
