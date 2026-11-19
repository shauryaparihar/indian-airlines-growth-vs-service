CREATE TABLE fact_yearly_airline (
    airline_code text NOT NULL REFERENCES dim_airline (airline_code),
    fiscal_year text NOT NULL,
    departures bigint NOT NULL,
    hours_flown numeric NOT NULL,
    km_flown_thousand numeric NOT NULL,
    passengers bigint NOT NULL,
    rpk_million numeric NOT NULL,
    ask_million numeric NOT NULL,
    pax_load_factor_pct_dgca numeric NOT NULL,
    freight_tonnes numeric NOT NULL,
    mail_tonnes numeric NOT NULL,
    total_cargo_tonnes numeric NOT NULL,
    pax_tonne_km_million numeric NOT NULL,
    freight_tonne_km_million numeric NOT NULL,
    mail_tonne_km_million numeric NOT NULL,
    rtk_million numeric NOT NULL,
    atk_million numeric NOT NULL,
    weight_load_factor_pct_dgca numeric NOT NULL,
    source_edition text NOT NULL,
    source_file text NOT NULL,
    -- recomputed from raw columns rather than trusted from DGCA's printed ratio (see docs/data-issues.md, errors 2 and 3)
    pax_load_factor_pct numeric GENERATED ALWAYS AS (rpk_million / NULLIF(ask_million, 0) * 100) STORED,
    weight_load_factor_pct numeric GENERATED ALWAYS AS (rtk_million / NULLIF(atk_million, 0) * 100) STORED,
    avg_speed_kmh numeric GENERATED ALWAYS AS (km_flown_thousand * 1000 / NULLIF(hours_flown, 0)) STORED,
    avg_stage_distance_km numeric GENERATED ALWAYS AS (km_flown_thousand * 1000 / NULLIF(departures, 0)) STORED,
    avg_pax_per_departure numeric GENERATED ALWAYS AS (passengers::numeric / NULLIF(departures, 0)) STORED,
    avg_distance_per_pax_km numeric GENERATED ALWAYS AS (rpk_million * 1000000 / NULLIF(passengers, 0)) STORED,
    PRIMARY KEY (airline_code, fiscal_year)
);

CREATE TABLE fact_yearly_market_aggregate (
    aggregate_group text NOT NULL,
    fiscal_year text NOT NULL,
    departures bigint NOT NULL,
    hours_flown numeric NOT NULL,
    km_flown_thousand numeric NOT NULL,
    passengers bigint NOT NULL,
    rpk_million numeric NOT NULL,
    ask_million numeric NOT NULL,
    pax_load_factor_pct_dgca numeric NOT NULL,
    freight_tonnes numeric NOT NULL,
    mail_tonnes numeric NOT NULL,
    total_cargo_tonnes numeric NOT NULL,
    pax_tonne_km_million numeric NOT NULL,
    freight_tonne_km_million numeric NOT NULL,
    mail_tonne_km_million numeric NOT NULL,
    rtk_million numeric NOT NULL,
    atk_million numeric NOT NULL,
    weight_load_factor_pct_dgca numeric NOT NULL,
    source_edition text NOT NULL,
    source_file text NOT NULL,
    pax_load_factor_pct numeric GENERATED ALWAYS AS (rpk_million / NULLIF(ask_million, 0) * 100) STORED,
    weight_load_factor_pct numeric GENERATED ALWAYS AS (rtk_million / NULLIF(atk_million, 0) * 100) STORED,
    PRIMARY KEY (aggregate_group, fiscal_year)
);

CREATE TABLE fact_yearly_coefficients (
    airline_code text NOT NULL REFERENCES dim_airline (airline_code),
    fiscal_year text NOT NULL,
    pax_load_factor_pct numeric,
    weight_load_factor_pct numeric,
    avg_speed_kmh numeric,
    avg_stage_distance_km numeric,
    avg_pax_per_departure numeric,
    avg_distance_per_pax_km000 numeric,
    source_edition text NOT NULL,
    source_file text NOT NULL,
    PRIMARY KEY (airline_code, fiscal_year)
);

CREATE TABLE fact_yearly_market_aggregate_coefficients (
    aggregate_group text NOT NULL,
    fiscal_year text NOT NULL,
    pax_load_factor_pct numeric,
    weight_load_factor_pct numeric,
    avg_speed_kmh numeric,
    avg_stage_distance_km numeric,
    avg_pax_per_departure numeric,
    avg_distance_per_pax_km000 numeric,
    source_edition text NOT NULL,
    source_file text NOT NULL,
    PRIMARY KEY (aggregate_group, fiscal_year)
);
