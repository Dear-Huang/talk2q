"""Run functions in an ALREADY authenticated RQData session. Never reads credentials.

Standalone execution does dependency inspection only; no rqdatac.init call.
This is a research data probe, not a runnable trading strategy.
"""
from pathlib import Path
import json,importlib.util
import pandas as pd
P=Path(__file__).parent
CANDIDATES=['pe_ratio_ttm','pe_ratio_lyr','return_on_equity_ttm','return_on_equity_diluted_ttm']

def probe(client,asof,output_dir=P):
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    result={'asof':str(asof),'real_data':True,'executed':False,'credentials_read':False}
    try:
        catalog=client.get_all_factor_names()
        (out/'live_factor_catalog.json').write_text(json.dumps(list(catalog),ensure_ascii=False,indent=2),encoding='utf-8')
        missing=sorted(set(CANDIDATES)-set(catalog))
        if missing:raise ValueError('Required candidate fields absent: '+','.join(missing))
        # Historical universe fixed at the same signal date, never today's members.
        pool=client.index_components('000300.XSHG',date=asof)
        (out/'live_historical_pool.json').write_text(json.dumps({'asof':str(asof),'codes':list(pool)},ensure_ascii=False,indent=2),encoding='utf-8')
        sample=sorted(pool)[:3]  # minimal shape probe only; not selecting top 10
        raw=client.get_factor(sample,CANDIDATES,start_date=asof,end_date=asof,expect_df=True)
        if not isinstance(raw,pd.DataFrame):raise TypeError('Expected factor DataFrame')
        raw.to_csv(out/'live_factor_candidates.csv',encoding='utf-8-sig')
        start=client.get_previous_trading_date(asof,n=20)
        calendar=client.get_trading_dates(start,asof)
        # Read raw candidates. Adjusted momentum is not activated before confirmation.
        prices=client.get_price(sample,start_date=start,end_date=asof,frequency='1d',fields=['close'],adjust_type='none',skip_suspended=False,expect_df=True)
        prices.to_csv(out/'live_raw_close.csv',encoding='utf-8-sig')
        result.update(executed=True,rows=len(raw),factor_index_names=list(raw.index.names),factor_columns=list(raw.columns),price_index_names=list(prices.index.names),trading_dates=[str(x) for x in calendar],sample_codes=sample,selection_executed=False,announcement_timestamp_returned='info_date' in raw.columns)
    except Exception as exc:
        # Do not silently replace a missing factor or print authentication messages.
        result.update(error_type=type(exc).__name__,status='data_or_permission_blocked',conditions_preserved=True)
    (out/'live_probe_status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    result={'rqdatac_installed':importlib.util.find_spec('rqdatac') is not None,'financial_query_executed':False,'cloud_plus_executed':False,'reason':'Pass an already authenticated rqdatac client to probe(); credentials are outside this program.'}
    (P/'local_probe_status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
