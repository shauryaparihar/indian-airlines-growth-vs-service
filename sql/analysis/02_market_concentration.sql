-- HHI uses market share as a 0-100 number (not a 0-1 fraction), so it ranges 0-10,000.
-- US DOJ bands (adapted): <1,500 unconcentrated, 1,500-2,500 moderate, >2,500 highly concentrated.
CREATE VIEW v_market_concentration AS
WITH ranked AS (
    SELECT fiscal_year, recon_group, passengers, market_share_pct,
           ROW_NUMBER() OVER (PARTITION BY fiscal_year ORDER BY market_share_pct DESC) AS rnk
    FROM v_airline_year
    WHERE passengers > 0
)
SELECT
    fiscal_year,
    LEFT(fiscal_year, 4)::int AS fy_start,
    SUM(passengers) AS total_passengers,
    COUNT(*) AS active_airlines,
    MAX(market_share_pct) AS top_airline_share_pct,
    SUM(market_share_pct) FILTER (WHERE rnk <= 3) AS top3_share_pct,
    SUM(market_share_pct ^ 2) AS hhi
FROM ranked
GROUP BY fiscal_year;
