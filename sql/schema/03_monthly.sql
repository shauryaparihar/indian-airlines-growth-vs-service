CREATE TABLE fact_monthly_passengers (
    airline_code text NOT NULL REFERENCES dim_airline (airline_code),
    year int NOT NULL,
    month int NOT NULL,
    fiscal_year text NOT NULL,
    pax_lakh numeric NOT NULL,
    passengers bigint NOT NULL,
    source_report text NOT NULL,
    PRIMARY KEY (airline_code, year, month),
    FOREIGN KEY (year, month) REFERENCES dim_month (year, month)
);

CREATE TABLE fact_monthly_load_factor (
    airline_code text NOT NULL REFERENCES dim_airline (airline_code),
    year int NOT NULL,
    month int NOT NULL,
    fiscal_year text NOT NULL,
    pax_load_factor_pct numeric NOT NULL,
    source_report text NOT NULL,
    PRIMARY KEY (airline_code, year, month),
    FOREIGN KEY (year, month) REFERENCES dim_month (year, month)
);

CREATE TABLE fact_monthly_service (
    airline_code text NOT NULL REFERENCES dim_airline (airline_code),
    year int NOT NULL,
    month int NOT NULL,
    fiscal_year text NOT NULL,
    metric text NOT NULL CHECK (metric IN ('cancellation_rate_pct', 'complaints_per_10k', 'otp_pct')),
    value numeric NOT NULL,
    footnote boolean NOT NULL DEFAULT false,
    otp_airports int,
    source_report text NOT NULL,
    PRIMARY KEY (airline_code, year, month, metric),
    FOREIGN KEY (year, month) REFERENCES dim_month (year, month)
);

CREATE TABLE fact_monthly_market_service (
    year int NOT NULL,
    month int NOT NULL,
    fiscal_year text NOT NULL,
    overall_cancellation_rate_pct numeric,
    total_complaints numeric,
    complaints_per_10k numeric,
    otp_airports int,
    source_report text NOT NULL,
    PRIMARY KEY (year, month),
    FOREIGN KEY (year, month) REFERENCES dim_month (year, month)
);
