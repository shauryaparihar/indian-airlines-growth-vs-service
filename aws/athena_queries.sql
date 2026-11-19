-- Reproduction template for a one-off Athena query over the processed yearly airline CSV.
-- Region used: ap-southeast-2 (Sydney).
--
-- This computes airline-level HHI with NO airline-family grouping. It is NOT the
-- family-grouped HHI of the main SQL view (about 2,242 for FY 2013-14 and 4,818 for FY 2024-25).
--
-- Provenance: the logic matches the query Shaurya ran manually in Athena, but this file is a
-- reproduction template, not a byte-for-byte copy of what was executed (for example it adds
-- IF NOT EXISTS). The S3 location below is a placeholder; the original bucket and table were
-- cleaned up and are not published here.
--
-- To re-run: create your own bucket/prefix, upload data/processed/yearly_airline_domestic_history.csv
-- as the ONLY object under the prefix (Athena reads every file under a LOCATION), and make sure an
-- Athena query-results location or workgroup is configured.

CREATE DATABASE IF NOT EXISTS airlines;

-- OpenCSVSerde reads every column as a string, so passengers is cast in the query below.
-- The column list matches the 20 columns of the CSV header, in the same order.
CREATE EXTERNAL TABLE IF NOT EXISTS airlines.yearly_history (
  airline string, fiscal_year string, departures string, hours_flown string,
  km_flown_thousand string, passengers string, rpk_million string, ask_million string,
  pax_load_factor_pct string, freight_tonnes string, mail_tonnes string,
  total_cargo_tonnes string, pax_tonne_km_million string, freight_tonne_km_million string,
  mail_tonne_km_million string, rtk_million string, atk_million string,
  weight_load_factor_pct string, source_edition string, source_file string
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
LOCATION 's3://<your-bucket>/yearly_history/'
TBLPROPERTIES ('skip.header.line.count'='1');

-- No recon_group mapping is applied here. Do not compare these values with
-- the family-grouped main SQL view (2,242 and 4,818).
WITH y AS (
  SELECT fiscal_year, airline, CAST(passengers AS double) AS pax
  FROM airlines.yearly_history
), s AS (
  SELECT fiscal_year, airline,
    100.0 * pax / SUM(pax) OVER (PARTITION BY fiscal_year) AS share
  FROM y
  WHERE pax > 0
)
SELECT fiscal_year, ROUND(SUM(share * share), 1) AS hhi,
  ROUND(MAX(share), 1) AS top_share
FROM s
GROUP BY fiscal_year
ORDER BY fiscal_year;
