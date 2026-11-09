"""Official-field query builders. Import/build are offline; execute requires explicit call.

These SQL contracts were NOT executed against authenticated DAI in this task.
Financial lower bound must include pre-existing announcement snapshots, not only
the target backtest start. Missing first as-of financial record must remain missing.
"""
import inspect
from bigquant import dai


def query_specs(start, end, financial_start):
    return {
        "calendar": ("SELECT date, market_code FROM all_trading_days WHERE market_code = 'CN' ORDER BY date", {"date": [start, end]}),
        "members": ("SELECT date, instrument, member_code FROM cn_stock_index_component WHERE instrument = '000300.SH' ORDER BY date, member_code", {"date": [start, end], "instrument": ["000300.SH"]}),
        "valuation": ("SELECT date, instrument, pe_ttm FROM cn_stock_valuation ORDER BY date, instrument", {"date": [start, end]}),
        "financial": ("SELECT date, instrument, report_date, shift, roe_avg_ttm FROM cn_stock_financial_profitability WHERE shift = 0 ORDER BY date, instrument, report_date", {"date": [financial_start, end]}),
        # Official adjusted close is already raw close * adjust_factor: do not multiply twice.
        "bars": ("SELECT date, instrument, close FROM cn_stock_bar1d ORDER BY date, instrument", {"date": [start, end]}),
    }


def validate_query_calls(start, end, financial_start):
    specs = query_specs(start, end, financial_start)
    for sql, filters in specs.values():
        inspect.signature(dai.query).bind(sql, filters=filters)
    return specs


def execute_authorized_queries(start, end, financial_start, output):
    # No retry, no credentials loaded by this script; account authentication is platform-owned.
    from pathlib import Path
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frames = {}
    for name, (sql, filters) in validate_query_calls(start, end, financial_start).items():
        frame = dai.query(sql, filters=filters).df()
        if frame.empty:
            raise ValueError(f"{name} empty; stop without dropping any factor")
        frame.to_csv(output / f"{name}.csv", index=False)
        frames[name] = frame
    return frames
