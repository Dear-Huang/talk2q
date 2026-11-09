# Cloud/Plus read-only data probe: no trade functions and no default live activation.
# Paste into a backtest strategy editor / run_file with an authorized data session.
# No order is submitted. This is not the final monthly trading strategy.
import json
from rqalpha.api import *

CANDIDATES=['pe_ratio_ttm','pe_ratio_lyr','return_on_equity_ttm','return_on_equity_diluted_ttm']

def init(context):
    context.probed=False

def before_trading(context):
    if context.probed:return
    context.probed=True
    asof=get_previous_trading_date(context.now)
    pool=index_components('000300.XSHG',date=asof)
    sample=sorted(pool)[:3]
    # Plus is count-based and binds to engine T-1, not local start_date/end_date.
    raw=get_factor(sample,CANDIDATES,count=1,expect_df=True)
    logger.info(json.dumps({'kind':'factor_probe','engine_date':str(context.now),'asof':str(asof),'pool_size':len(pool),'sample':sample,'index_names':list(raw.index.names),'columns':list(raw.columns),'rows':len(raw),'values':raw.reset_index().to_dict('records')},default=str,ensure_ascii=False))
    for symbol in sample:
        bars=history_bars(symbol,21,'1d',['datetime','close'],skip_suspended=False,include_now=False,adjust_type='none')
        logger.info(json.dumps({'kind':'close_probe','symbol':symbol,'asof':str(asof),'count':len(bars),'datetimes':[int(x) for x in bars['datetime']],'closes':[float(x) for x in bars['close']]},default=str))

def handle_bar(context,bar_dict):
    pass
