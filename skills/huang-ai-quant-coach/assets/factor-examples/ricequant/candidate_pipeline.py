"""Full DATA/SELECTION candidate. No execution, credentials, or rqdatac.init.

Explicit test choices are in test_case_config.json; final user strategy not assumed.
"""
from pathlib import Path
import json
import pandas as pd
from factor_contract import ContractError,normalize_factor_frame,momentum20,is_month_first,select_targets
from factor_registry import resolve_factor

def price_frame(raw):
    if not isinstance(raw,pd.DataFrame) or not isinstance(raw.index,pd.MultiIndex):
        raise ContractError('price output must be MultiIndex DataFrame')
    names=raw.index.names
    if raw.index.nlevels!=2 or 'order_book_id' not in names or raw.index.has_duplicates:
        raise ContractError('duplicate/ambiguous security-date price axes')
    date_name='datetime' if 'datetime' in names else 'date'
    if set(names)!={'order_book_id',date_name} or 'close' not in raw:
        raise ContractError('price output requires named date/datetime and close')
    x=raw[['close']].copy();x.index=x.index.set_names(['date' if n==date_name else n for n in names])
    return x.reorder_levels(['date','order_book_id'])['close'].unstack('order_book_id').rename_axis('date')

def research_candidate(client,trade_date,config):
    if not config.get('conditions_confirmed_for_test'):
        raise ContractError('exact factor definitions must be confirmed before selection')
    pe=config['pe_field'];roe=config['roe_field']
    for f in [pe,roe]:resolve_factor(f)
    today=pd.Timestamp(trade_date).date()
    asof=client.get_previous_trading_date(today)
    if not is_month_first(today,asof):
        return {'status':'not_month_first','trade_date':str(today),'asof':str(asof),'orders_submitted':0}
    catalog=client.get_all_factor_names()
    for f in [pe,roe]:resolve_factor(f,catalog)
    pool=sorted(client.index_components('000300.XSHG',date=asof))
    if not pool:
        return {'status':'empty_historical_pool','targets':{},'cash_weight':1.,'orders_submitted':0}
    raw=client.get_factor(pool,[pe,roe],start_date=asof,end_date=asof,expect_df=True)
    canonical=normalize_factor_frame(raw,asof=asof,symbols=pool,fields={'pe':pe,'roe_ttm':roe},roe_unit=config['roe_unit'])
    if config['momentum_adjust_type']!='none':
        raise ContractError('this test branch only implements explicitly selected unadjusted closes; research as-of adjustment before adding another branch')
    start=client.get_previous_trading_date(asof,n=20)
    calendar=client.get_trading_dates(start,asof)
    raw_prices=client.get_price(pool,start_date=start,end_date=asof,frequency='1d',fields=['close'],adjust_type='none',skip_suspended=False,expect_df=True)
    prices=price_frame(raw_prices).reindex(columns=pool)
    momentum=momentum20(prices,asof=asof,trading_dates=calendar,approved=config.get('custom_momentum_confirmed_for_test',False))
    selected,cash=select_targets(canonical,momentum,trade_date=today,asof=asof,confirmed=True)
    return {'status':'candidate_selected','scope':config['scope'],'trade_date':str(today),'asof':str(asof),'pool_size':len(pool),'targets':selected.target_weight.to_dict(),'cash_weight':cash,'ranked_rows':selected.reset_index().to_dict('records'),'source':'rqdatac get_factor explicit date + historical index components + unadjusted daily close','pit_evidence':'official documentation, not independent per-record announcement-time verification','orders_submitted':0}

def default_test_config():
    return json.loads((Path(__file__).parent/'test_case_config.json').read_text(encoding='utf-8'))
