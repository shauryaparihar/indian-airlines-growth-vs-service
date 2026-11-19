CREATE INDEX ix_yearly_airline_fy ON fact_yearly_airline (fiscal_year);
CREATE INDEX ix_monthly_passengers_fy ON fact_monthly_passengers (fiscal_year);
CREATE INDEX ix_monthly_load_factor_fy ON fact_monthly_load_factor (fiscal_year);
CREATE INDEX ix_monthly_service_fy_metric ON fact_monthly_service (fiscal_year, metric);
CREATE INDEX ix_dim_airline_recon_group ON dim_airline (recon_group);
CREATE INDEX ix_data_issue_category ON data_issue (category);
