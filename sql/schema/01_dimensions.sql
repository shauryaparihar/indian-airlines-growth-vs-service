CREATE TABLE dim_airline (
    airline_code text PRIMARY KEY,
    airline_name text NOT NULL,
    recon_group text NOT NULL,
    is_combined_entity boolean NOT NULL DEFAULT false
);

CREATE TABLE dim_month (
    year int NOT NULL,
    month int NOT NULL CHECK (month BETWEEN 1 AND 12),
    fiscal_year text NOT NULL,
    calendar_date date NOT NULL,
    month_name text NOT NULL,
    PRIMARY KEY (year, month)
);

CREATE TABLE airline_mapping (
    source text NOT NULL,
    source_key text NOT NULL,
    airline_code text NOT NULL REFERENCES dim_airline (airline_code),
    airline_name text NOT NULL,
    recon_group text NOT NULL,
    notes text,
    PRIMARY KEY (source, source_key)
);

-- airline_code here may be an airline_code, a recon_group, or NULL: this is a free-text audit
-- log of findings from the parsers/validators, not a dimensional fact table, so it has no FK.
CREATE TABLE data_issue (
    id serial PRIMARY KEY,
    source_log text NOT NULL,
    category text NOT NULL,
    airline_code text,
    fiscal_year text,
    year int,
    month int,
    detail text NOT NULL
);
