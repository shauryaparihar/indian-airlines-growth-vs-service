"""(Re)build every analysis view in sql/analysis/ against the already-loaded database."""

from pathlib import Path

import psycopg

from load_postgres import DATABASE_URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = PROJECT_ROOT / "sql" / "analysis"

DROP_ALL = """
DROP TABLE IF EXISTS known_merger CASCADE;
DROP VIEW IF EXISTS v_market_events, v_market_service_by_fy, v_covid_recovery, v_airline_lifecycle, v_growth_vs_quality, v_otp_scope_by_fy,
    v_monthly_load_factor_by_fy, v_monthly_service_by_fy, v_market_concentration, v_airline_year CASCADE;
"""


def main():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(DROP_ALL)
        for path in sorted(ANALYSIS_DIR.glob("*.sql")):
            conn.execute(path.read_text(encoding="utf-8"))
            print(f"applied {path.name}")


if __name__ == "__main__":
    main()
