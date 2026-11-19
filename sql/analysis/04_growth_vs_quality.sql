CREATE VIEW v_growth_vs_quality AS
SELECT
    g.recon_group,
    g.fiscal_year,
    g.fy_start,
    g.passengers,
    g.market_share_pct,
    g.passenger_yoy_growth_pct,
    g.pax_load_factor_pct AS yearly_pax_load_factor_pct,
    lf.avg_pax_load_factor_pct AS monthly_avg_pax_load_factor_pct,
    canc.weighted_avg AS avg_cancellation_rate_pct,
    comp.weighted_avg AS avg_complaints_per_10k,
    otp.weighted_avg AS avg_otp_pct,
    otp.n_airline_months AS otp_airline_months,
    scope.otp_airport_scopes_seen,
    scope.mixed_scope AS otp_scope_mixed,
    canc.weighted_avg - LAG(canc.weighted_avg) OVER (PARTITION BY g.recon_group ORDER BY g.fiscal_year)
        AS cancellation_rate_change_pts,
    comp.weighted_avg - LAG(comp.weighted_avg) OVER (PARTITION BY g.recon_group ORDER BY g.fiscal_year)
        AS complaints_per_10k_change,
    otp.weighted_avg - LAG(otp.weighted_avg) OVER (PARTITION BY g.recon_group ORDER BY g.fiscal_year)
        AS otp_pct_change_pts
FROM v_airline_year g
LEFT JOIN v_monthly_load_factor_by_fy lf ON lf.recon_group = g.recon_group AND lf.fiscal_year = g.fiscal_year
LEFT JOIN v_monthly_service_by_fy canc
    ON canc.recon_group = g.recon_group AND canc.fiscal_year = g.fiscal_year AND canc.metric = 'cancellation_rate_pct'
LEFT JOIN v_monthly_service_by_fy comp
    ON comp.recon_group = g.recon_group AND comp.fiscal_year = g.fiscal_year AND comp.metric = 'complaints_per_10k'
LEFT JOIN v_monthly_service_by_fy otp
    ON otp.recon_group = g.recon_group AND otp.fiscal_year = g.fiscal_year AND otp.metric = 'otp_pct'
LEFT JOIN v_otp_scope_by_fy scope ON scope.fiscal_year = g.fiscal_year;
