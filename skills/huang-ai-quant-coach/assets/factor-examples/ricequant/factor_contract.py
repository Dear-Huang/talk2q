"""Provider-independent factor contract. No credentials, network or trade API."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

class ContractError(ValueError):
    pass

def normalize_factor_frame(raw, *, asof, symbols, fields, roe_unit, available_at=None):
    """fields maps canonical pe/roe_ttm to the exact confirmed provider field."""
    if roe_unit not in {'fraction','percent'}:
        raise ContractError('ROE unit must be explicitly fraction or percent')
    if not isinstance(raw,pd.DataFrame) or not isinstance(raw.index,pd.MultiIndex):
        raise ContractError('expected MultiIndex DataFrame, never guess axes')
    if raw.index.nlevels!=2 or set(raw.index.names)!={'date','order_book_id'}:
        raise ContractError('index names must be date and order_book_id')
    if raw.index.has_duplicates:
        raise ContractError('duplicate security/date rows')
    x=raw.reorder_levels(['date','order_book_id']).copy()
    dates=pd.to_datetime(x.index.get_level_values('date')).normalize()
    day=pd.Timestamp(asof).normalize()
    if len(dates) and not (dates==day).all():
        raise ContractError('factor snapshot must be exactly asof: future and stale rows rejected')
    if len(set(symbols))!=len(symbols):
        raise ContractError('duplicate universe code')
    if not set(x.index.get_level_values('order_book_id')).issubset(set(symbols)):
        raise ContractError('provider row outside historical universe')
    if set(fields)!={'pe','roe_ttm'} or not set(fields.values()).issubset(x.columns):
        raise ContractError('exact confirmed PE and ROE fields required')
    x=x.rename(columns={v:k for k,v in fields.items()})[['pe','roe_ttm']]
    x.index=pd.MultiIndex.from_arrays([dates,x.index.get_level_values('order_book_id')],names=['date','order_book_id'])
    target=pd.MultiIndex.from_product([[day],list(symbols)],names=['date','order_book_id'])
    x=x.reindex(target).apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan)
    if roe_unit=='percent':x['roe_ttm']/=100.
    # Optional exact release timestamp from an authorized PIT export. Never synthesize it.
    if available_at is not None:
        if not isinstance(available_at,pd.Series):raise ContractError('available_at must be indexed Series')
        time=pd.to_datetime(available_at.reorder_levels(['date','order_book_id']).reindex(target))
        if not isinstance(time.dtype,pd.DatetimeTZDtype):
            raise ContractError('availability timestamps need explicit timezone, never guess UTC')
        time=time.dt.tz_convert('UTC')
        cutoff=day.tz_localize('Asia/Shanghai').tz_convert('UTC')+pd.Timedelta(days=1)-pd.Timedelta(nanoseconds=1)
        if time.isna().any() or (time>cutoff).any():
            raise ContractError('missing/future availability timestamp')
    return x.sort_index()

def momentum20(prices, *, asof, trading_dates, approved=False):
    """Candidate custom factor: C(asof)/C(asof-20 trading days)-1, fraction.

    Prices must already use ONE approved as-of adjustment basis. 21 required prices,
    no suspension-day skipping, no filling, no selecting future adjustment factors.
    """
    if not approved:raise ContractError('custom momentum definition/adjustment needs confirmation')
    if not isinstance(prices,pd.DataFrame) or isinstance(prices.columns,pd.MultiIndex):
        raise ContractError('prices must be date-indexed rows and security columns')
    if prices.index.name!='date' or prices.index.has_duplicates or prices.columns.has_duplicates:
        raise ContractError('ambiguous or duplicate price axes')
    dates=pd.DatetimeIndex(pd.to_datetime(trading_dates)).normalize()
    day=pd.Timestamp(asof).normalize()
    if dates.has_duplicates or not dates.is_monotonic_increasing or len(dates)==0 or dates[-1]!=day:
        raise ContractError('calendar must be sorted unique and end exactly at asof')
    ix=pd.DatetimeIndex(pd.to_datetime(prices.index)).normalize()
    if ix.has_duplicates or (ix>day).any():raise ContractError('future or duplicate prices')
    if not ix.isin(dates).all():raise ContractError('price date outside supplied real calendar')
    x=prices.copy();x.index=ix
    if len(dates)<21:return pd.Series(np.nan,index=prices.columns,name='momentum20')
    x=x.reindex(dates[-21:]).apply(pd.to_numeric,errors='coerce')
    valid=np.isfinite(x).all(axis=0)&(x>0).all(axis=0)
    result=(x.iloc[-1]/x.iloc[0]-1).where(valid)
    result.name='momentum20'
    return result

def is_month_first(trade_date,previous_trade_date):
    t,p=pd.Timestamp(trade_date),pd.Timestamp(previous_trade_date)
    if p>=t:raise ContractError('previous trade date must precede execution')
    return (p.year,p.month)!=(t.year,t.month)

def select_targets(snapshot,momentum,*,trade_date,asof,confirmed=False):
    if not confirmed:raise ContractError('PE basis, ROE denominator and custom momentum need confirmation')
    t,d=pd.Timestamp(trade_date).normalize(),pd.Timestamp(asof).normalize()
    if d>=t:raise ContractError('signal must precede execution date')
    if snapshot.index.names!=['date','order_book_id'] or snapshot.index.has_duplicates:
        raise ContractError('invalid canonical factor axes')
    if len(snapshot) and not (pd.DatetimeIndex(snapshot.index.get_level_values('date'))==d).all():
        raise ContractError('mixed/future signal dates')
    if momentum.index.has_duplicates:raise ContractError('duplicate momentum code')
    x=snapshot.xs(d,level='date').copy()
    x['momentum20']=momentum.reindex(x.index)
    x=x.replace([np.inf,-np.inf],np.nan).dropna(subset=['pe','roe_ttm','momentum20'])
    x=x.loc[(x.pe>0)&(x.pe<20)].reset_index()
    x=x.sort_values(['roe_ttm','momentum20','order_book_id'],ascending=[False,False,True],kind='mergesort').head(10)
    x['target_weight']=.08
    return x.set_index('order_book_id'),1-.08*len(x)

def custom_roe_ttm(profit_quarters,equity_quarters,*,approved=False):
    """Only an offline candidate; not a substitute for provider ROE field.

    TTM profit sum / mean of four quarter-end parent equity. This is a distinct
    formula from provider return_on_equity_ttm and needs specific user confirmation.
    """
    if not approved:raise ContractError('custom ROE requires explicit formula confirmation')
    a=np.asarray(profit_quarters,dtype=float);b=np.asarray(equity_quarters,dtype=float)
    if a.shape!=(4,) or b.shape!=(4,):raise ContractError('four available single-quarter profits and quarter-end equities required')
    if not np.isfinite(a).all() or not np.isfinite(b).all():return np.nan
    denominator=b.mean()
    if denominator==0:return np.nan
    return a.sum()/denominator
