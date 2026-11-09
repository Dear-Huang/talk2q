"""Non-final factor candidate. No engine execution, no guessed vendor fields.

PE basis and ROE denominator are explicit parameters because Chinese names alone
do not determine them. Official roe_avg_ttm is average-equity, not period-end ROE.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class FactorDefinition:
    pe_basis: str
    roe_basis: str
    price_basis: str

    def validate(self):
        if self.pe_basis != "pe_ttm":
            raise ContractError("This adapter only maps official PE TTM, not generic/static/dynamic PE")
        if self.roe_basis != "roe_avg_ttm":
            raise ContractError("This adapter only maps announced average-equity TTM ROE; no implicit equivalence")
        if self.price_basis != "cn_stock_bar1d_backward_adjusted":
            raise ContractError("Select and document the price adjustment basis before ranking")


def require(frame, fields, name):
    missing = set(fields) - set(frame.columns)
    if missing:
        raise ContractError(f"{name}: missing fields {sorted(missing)}; factor not removed")
    if frame.empty:
        raise ContractError(f"{name}: empty dataset, not an empty selection")


def dates(frame, columns):
    frame = frame.copy()
    for col in columns:
        frame[col] = pd.to_datetime(frame[col], errors="raise").dt.normalize()
        if frame[col].isna().any():
            raise ContractError(f"Invalid/null date in {col}")
    return frame


def unique(frame, keys, name):
    if frame.duplicated(keys).any():
        raise ContractError(f"{name}: duplicate keys {keys}; version resolution required")


def select(execution_date, calendar, members, valuation, financial, bars, definition):
    """Return ranked factor evidence and fixed weights; missing values stay excluded.

    DataFrame columns below mirror official tables. Calendar may extend beyond the
    current date for scheduling only. All factor and membership reads stop at the
    previous trading day; no global latest-report shortcut is permitted.
    """
    definition.validate()
    for frame, fields, name in [
        (calendar, ["date", "market_code"], "calendar"),
        (members, ["date", "instrument", "member_code"], "members"),
        (valuation, ["date", "instrument", "pe_ttm"], "valuation"),
        (financial, ["date", "instrument", "report_date", "shift", "roe_avg_ttm"], "financial"),
        (bars, ["date", "instrument", "close"], "bars"),
    ]: require(frame, fields, name)
    calendar = dates(calendar, ["date"])
    trading = pd.DatetimeIndex(calendar.loc[calendar.market_code == "CN", "date"].sort_values().unique())
    execution_date = pd.Timestamp(execution_date).normalize()
    if execution_date not in trading:
        raise ContractError("execution_date is not a verified CN trading day")
    previous = trading[trading < execution_date]
    if len(previous) == 0:
        raise ContractError("Calendar lacks previous trading day")
    asof = previous[-1]
    if asof.to_period("M") == execution_date.to_period("M"):
        return {"status": "not_month_first", "execution_date": str(execution_date.date()), "signal_date": str(asof.date()), "targets": {}, "cash_target": 1.0, "evidence": []}
    members, valuation, financial, bars = [dates(f, ["date"]) for f in [members, valuation, financial, bars]]
    financial = dates(financial, ["report_date"])
    unique(members, ["date", "instrument", "member_code"], "members")
    unique(valuation, ["date", "instrument"], "valuation")
    unique(bars, ["date", "instrument"], "bars")
    # The official component table's instrument is the INDEX, not the security.
    pool = members[(members.date == asof) & (members.instrument == "000300.SH")]
    if pool.empty:
        raise ContractError("Historical CSI300 pool absent on signal date; current pool cannot substitute")
    pool_codes = sorted(set(pool.member_code))
    day_values = valuation[(valuation.date == asof) & valuation.instrument.isin(pool_codes)]
    if day_values.empty:
        raise ContractError("No signal-date valuation data; never forward/backfill PE")
    # shift=0 already means latest report as known ON THAT ANNOUNCEMENT DATE.
    known = financial[(financial.date <= asof) & (financial["shift"] == 0) & financial.instrument.isin(pool_codes)].copy()
    if (known.report_date > known.date).any():
        raise ContractError("Report period is later than its announcement date")
    unique(known, ["date", "instrument", "shift"], "known financial snapshots")
    if known.empty:
        raise ContractError("No announced TTM ROE available; keep ROE condition and supply data")
    known = known.sort_values(["instrument", "date", "report_date"]).drop_duplicates("instrument", keep="last")
    known = known.rename(columns={"date": "roe_available_date", "report_date": "roe_report_date"})
    joined = pd.DataFrame({"instrument": pool_codes}).merge(day_values[["instrument", "pe_ttm"]], on="instrument", how="left")
    joined = joined.merge(known[["instrument", "roe_avg_ttm", "roe_available_date", "roe_report_date"]], on="instrument", how="left")
    trailing = previous[-21:]
    momenta = []
    for code in pool_codes:
        history = bars[(bars.instrument == code) & (bars.date <= asof)].set_index("date").reindex(trailing)
        values = pd.to_numeric(history.close, errors="raise")
        enough = len(trailing) == 21 and len(values) == 21 and np.isfinite(values).all() and (values > 0).all()
        momenta.append({"instrument": code, "momentum20": float(values.iloc[-1] / values.iloc[0] - 1) if enough else np.nan})
    joined = joined.merge(pd.DataFrame(momenta), on="instrument", how="left")
    for column in ["pe_ttm", "roe_avg_ttm", "momentum20"]:
        joined[column] = pd.to_numeric(joined[column], errors="raise")
    eligible = joined[(joined.pe_ttm > 0) & (joined.pe_ttm < 20) & np.isfinite(joined.roe_avg_ttm) & np.isfinite(joined.momentum20)]
    ranked = eligible.sort_values(["roe_avg_ttm", "momentum20", "instrument"], ascending=[False, False, True], kind="stable").head(10)
    targets = {code: 0.08 for code in ranked.instrument}
    evidence = ranked.to_dict("records")
    excluded = joined[~joined.instrument.isin(ranked.instrument)].to_dict("records")
    return {"status": "planned_not_ordered", "execution_date": str(execution_date.date()), "signal_date": str(asof.date()),
            "targets": targets, "cash_target": round(1 - sum(targets.values()), 10),
            "evidence": evidence, "excluded_or_below_rank": excluded,
            "definition": definition.__dict__, "real_engine_backtest": False}


def custom_roe_from_components(frame, denominator_basis):
    """Fallback for user-supplied PIT components, never an automatic ROE substitution.

    Component names are our LOCAL contract, not claimed BigQuant vendor columns.
    An average denominator must have been computed with an approved exact formula.
    """
    require(frame, ["available_date", "report_date", "instrument", "profit_parent_ttm", "equity_denominator"], "custom PIT components")
    if denominator_basis not in {"approved_average_parent_equity", "approved_ending_parent_equity"}:
        raise ContractError("Exact denominator formula and unit must be supplied")
    result = frame.copy()
    result["custom_roe_ttm"] = np.where(result.equity_denominator > 0,
                                         result.profit_parent_ttm / result.equity_denominator, np.nan)
    return result
