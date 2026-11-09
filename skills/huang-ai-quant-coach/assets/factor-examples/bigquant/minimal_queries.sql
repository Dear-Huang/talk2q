-- Documentary probes, NOT executed in this task; apply date filters in dai.query.
-- Date is signal-day D; actual execution is first trading day after D.
SELECT date, instrument, member_code
FROM cn_stock_index_component
WHERE instrument = '000300.SH' AND date = '2023-12-29'
ORDER BY member_code LIMIT 5;

SELECT date, instrument, pe_ttm
FROM cn_stock_valuation
WHERE instrument = '000001.SZ' AND date = '2023-12-29' LIMIT 5;

-- date is ANNOUNCEMENT DATE, report_date is report period.
-- This bounded probe alone is insufficient to establish all prior as-of values.
SELECT date, instrument, report_date, shift, roe_avg_ttm
FROM cn_stock_financial_profitability
WHERE instrument = '000001.SZ' AND shift = 0 AND date <= '2023-12-29'
ORDER BY date DESC LIMIT 5;

-- Already backward-adjusted close: do NOT multiply adjust_factor a second time.
SELECT date, instrument, close
FROM cn_stock_bar1d
WHERE instrument = '000001.SZ' AND date <= '2023-12-29'
ORDER BY date DESC LIMIT 21;

SELECT date, market_code FROM all_trading_days
WHERE market_code = 'CN' AND date >= '2023-11-01' AND date <= '2024-02-02'
ORDER BY date;
