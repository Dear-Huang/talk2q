# 只取数探针：不下单，不是多因子投资策略。
from jqdata import *
from jqfactor import get_all_factors, get_factor_values
import builtins
import json
import math


def emit(event, **kw):
    kw['event'] = event
    log.info(json.dumps(kw, ensure_ascii=False, default=str, sort_keys=True))


def initialize(context):
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    set_benchmark('000300.XSHG')
    run_daily(probe, time='09:30')


def probe(context):
    asof = context.previous_date
    pool = sorted(get_index_stocks('000300.XSHG', date=asof))
    sample = pool[:3]
    emit('historical_pool', time=context.current_dt, asof=asof,
         size=len(pool), sample=sample, selection='lexicographic first three; test only')
    try:
        catalog = get_all_factors()
        selected = catalog[catalog['factor'].isin(['roe_ttm', 'momentum', 'skill_custom_mom20'])]
        emit('factor_catalog', columns=list(catalog.columns), rows=selected.to_dict('records'),
             custom_registered=bool((catalog['factor'] == 'skill_custom_mom20').any()))
        if 'roe_ttm' not in list(catalog['factor']):
            emit('missing_factor', factor='roe_ttm')
            return
        values = get_factor_values(securities=sample, factors=['roe_ttm'], end_date=asof, count=2)
        emit('factor_container', type=str(type(values)), keys=list(values.keys()))
        for name, frame in values.items():
            emit('factor_frame', factor=name, type=str(type(frame)), shape=list(frame.shape),
                 dates=list(frame.index), columns=list(frame.columns), values=[{'date': str(dt), 'security': str(code), 'value': float(frame.loc[dt, code])} for dt in frame.index for code in frame.columns])
    except Exception as exc:
        emit('factor_error', error_type=type(exc).__name__, message=str(exc))
    try:
        frame = get_fundamentals(query(valuation.code, valuation.pe_ratio).filter(
            valuation.code.in_(sample)), date=asof)
        emit('valuation_pe', asof=asof, type=str(type(frame)), columns=list(frame.columns),
             rows=frame.to_dict('records'), definition='valuation.pe_ratio PE TTM')
    except Exception as exc:
        emit('valuation_error', error_type=type(exc).__name__, message=str(exc))
    for security in sample:
        try:
            frame = get_price(security, end_date=asof, count=21, frequency='daily',
                              fields=['close'], skip_paused=False, fq='pre')
            closes = [float(x) for x in frame['close'].values]
            if len(closes) != 21 or builtins.any(not math.isfinite(x) or x <= 0 for x in closes):
                emit('momentum_missing', security=security, rows=len(closes))
                continue
            mom20 = closes[-1] / closes[-21] - 1.0
            mom5 = closes[-1] / closes[-6] - 1.0
            custom = mom20 - 0.5 * mom5
            emit('custom_momentum', security=security, asof=asof, first_time=frame.index[0],
                 last_time=frame.index[-1], close_t=closes[-1], close_t_minus20=closes[-21],
                 close_t_minus5=closes[-6], mom20=mom20, mom5=mom5,
                 custom_name='skill_custom_mom20', custom_value=custom,
                 formula='(P_t/P_t-20-1)-0.5*(P_t/P_t-5-1)',
                 price_basis='dynamic pre-adjusted as of callback day; 21 exchange trading dates')
        except Exception as exc:
            emit('momentum_error', security=security, error_type=type(exc).__name__, message=str(exc))
