"""BigQuant cloud 0.1.11 complete research example. Teaching assumptions, no live mode.
Upload the generated Notebook, select Python 3.11.8, then Run All.
"""
import sys
import json
import math
import inspect
import importlib.metadata as metadata
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import dai
from bigquant import bigtrader

# R1-R9: These are TEST teaching assumptions, not a real user's approved allocation.
CFG = dict(rule_version='bigquant-complete-teaching-v3', instrument='510300.SH',
           start_date='2024-01-02', end_date='2024-06-28', warmup_start='2023-11-01',
           capital=100000.0, target_weight=0.8, ma_window=20, lot_size=100,
           commission=0.0003, minimum_commission=5.0, tax=0.0, slippage=0.0,
           benchmark='000300.SH')
OUT = Path.cwd() / ('Skill_完整回测_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
OUT.mkdir(exist_ok=False)
EVENTS = []

def emit(event, **fields):
    row=dict(event=event, **fields)
    EVENTS.append(row)
    # Print only decisions/fills/skips, keeping daily details in exported files.
    if event != 'signal':
        print('AUDIT', json.dumps(row, ensure_ascii=False, default=str), flush=True)

def prepare_signals(prices):
    required={'date','instrument','open','close','adjust_factor','volume'}
    if not required.issubset(prices.columns):
        raise ValueError('数据字段缺失: ' + str(sorted(required-set(prices.columns))))
    df=prices.copy()
    df['date']=pd.to_datetime(df['date']).dt.normalize()
    if df.duplicated(['instrument','date']).any():
        raise ValueError('行情日期重复，停止，不能静默取最后一条')
    if set(df['instrument']) != {CFG['instrument']}:
        raise ValueError('行情标的与规则不符')
    df=df.sort_values('date').reset_index(drop=True)
    values=df[['open','close','adjust_factor','volume']].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (df[['open','close','adjust_factor']]<=0).any().any() or (df['volume']<0).any():
        raise ValueError('行情含无效价格/复权因子/成交量，停止')
    # R2: DAI close is already adjusted. Do NOT multiply adjust_factor again.
    df['ma20']=df['close'].rolling(CFG['ma_window'],min_periods=CFG['ma_window']).mean()
    df['raw_open']=df['open']/df['adjust_factor']
    df['raw_close']=df['close']/df['adjust_factor']
    return df

def preflight():
    # Never read credentials or configure a local SDK inside a cloud Notebook.
    print('ENVIRONMENT',sys.version.split()[0],metadata.version('bigquant'))
    if metadata.version('bigquant') != '0.1.11':
        raise RuntimeError('本例验证的是云端bigquant 0.1.11；版本变化时请先重新核验接口')
    params=inspect.signature(bigtrader.run).parameters
    if not {'backtest_only','render','report_output_path'}.issubset(params):
        raise RuntimeError('启动参数与已验证入口不符')
    assert CFG['warmup_start']<CFG['start_date']<=CFG['end_date']
    assert 0<CFG['target_weight']<1 and CFG['capital']>0
    sql="SELECT date,instrument,open,close,adjust_factor,volume FROM cn_fund_bar1d WHERE instrument='510300.SH' ORDER BY date"
    try:
        prices=dai.query(sql,filters={'date':[CFG['warmup_start'],CFG['end_date']]}).df()
    except Exception as exc:
        raise RuntimeError('BigQuant官方行情取数失败；检查登录/数据权限。未用演示数据替代。') from exc
    if prices.empty:
        raise RuntimeError('行情为空，不能按零收益通过')
    signals=prepare_signals(prices)
    selected=signals.loc[signals['date'].between(CFG['start_date'],CFG['end_date'])]
    if selected.empty or selected['ma20'].isna().any():
        raise RuntimeError('回测样本为空或预热不足；检查真实交易日覆盖')
    if str(selected.iloc[0]['date'].date())!=CFG['start_date'] or str(selected.iloc[-1]['date'].date())!=CFG['end_date']:
        raise RuntimeError('样本首尾缺行情；核对交易日与数据权限')
    signals.to_csv(OUT/'signals.csv',index=False)
    (OUT/'config.json').write_text(json.dumps(CFG,ensure_ascii=False,indent=2),'utf-8')
    print('DATA_OK',len(signals),'rows',len(selected),'backtest_days',str(signals.iloc[0]['date']),str(signals.iloc[-1]['date']))
    return signals

SIGNALS=preflight()
BY_DATE=SIGNALS.set_index('date')

def initialize(context):
    # R6: This cloud entry uses PerOrder; the local 6.0.3 scalar API is different.
    context.set_commission(bigtrader.PerOrder(buy_cost=CFG['commission'],sell_cost=CFG['commission'],
                                             min_cost=CFG['minimum_commission'],tax_ratio=CFG['tax']))
    context.set_slippage_value(slippage_type=1,slippage_value=CFG['slippage'])
    context.next_plan=None
    emit('initialize',config=CFG)

def handle_data(context,data):
    # R2/R5: Today's completed close creates a signal for NEXT trading day's open.
    day=pd.Timestamp(data.current_dt).normalize()
    if day not in BY_DATE.index:
        raise RuntimeError('引擎交易日缺少对应DAI行情: '+str(day))
    row=BY_DATE.loc[day]
    raw_close=float(data.current(CFG['instrument'],'close'))
    if not math.isfinite(raw_close) or raw_close<=0:
        emit('skip',day=str(day.date()),reason='invalid_engine_close')
        return
    # R2/R3: adjusted signal and unadjusted sizing must agree with factor mapping.
    if not math.isclose(raw_close,float(row.raw_close),rel_tol=1e-6,abs_tol=1e-6):
        raise RuntimeError('DAI与引擎价格口径不一致，停止而非自动切换复权')
    position=context.get_position(CFG['instrument'])
    qty=int(position.current_qty)
    bullish=float(row.close)>float(row.ma20)
    emit('signal',day=str(day.date()),adjusted_close=float(row.close),ma20=float(row.ma20),
         raw_close=raw_close,qty=qty,bullish=bullish)
    # R8: End-of-test does not invent an extra next day or force a liquidation.
    if day==pd.Timestamp(CFG['end_date']):
        emit('sample_end',day=str(day.date()),qty=qty,reason='no_next_bar_in_sample')
        return
    if bullish and qty==0:
        cash=float(context.get_available_cash())
        equity=float(context.get_portfolio_value())
        target=min(equity*CFG['target_weight'],cash)
        amount=math.floor(target/raw_close/CFG['lot_size'])*CFG['lot_size']
        while amount>0 and amount*raw_close+max(CFG['minimum_commission'],amount*raw_close*CFG['commission'])>cash:
            amount-=CFG['lot_size']
        if amount<=0:
            emit('skip',day=str(day.date()),reason='insufficient_cash_for_one_lot',cash=cash)
            return
        reason='close_above_ma20_empty_position'
    elif not bullish and qty>0:
        # R4/R8: only sell actually available holdings; preserve residuals.
        # Tomorrow's sellability is checked in before_trading_start, after T+1 settlement.
        available=qty
        amount=-(qty//CFG['lot_size']*CFG['lot_size'])
        if not amount:
            emit('skip',day=str(day.date()),reason='no_sellable_quantity',qty=qty,available=available)
            return
        reason='close_at_or_below_ma20'
    else:
        return
    # R3: quantity fixed from signal-day close, indicative 80%, not next-open exact 80%.
    context.next_plan=dict(signal_day=str(day.date()),qty=int(amount),sizing_price=raw_close,reason=reason)
    emit('plan',**context.next_plan)

def before_trading_start(context,data):
    # R4/R5: D close freezes the plan. D+1 08:30 uses settled sellable quantity;
    # observed cloud engine matches these orders at D+1 open, not D+2.
    plan=context.next_plan
    context.next_plan=None
    if plan is None:
        return
    amount=plan['qty']
    position=context.get_position(CFG['instrument'])
    if amount<0:
        available=int(position.avail_qty)
        amount=-(min(-amount,available)//CFG['lot_size']*CFG['lot_size'])
    elif int(position.current_qty)>0:
        emit('skip',day=str(data.current_dt),reason='already_held_before_open')
        return
    if amount==0:
        emit('skip',day=str(data.current_dt),reason='no_settled_sellable_quantity',plan=plan)
        return
    rv=context.order(CFG['instrument'],int(amount))
    emit('submission',**{**plan,'qty':int(amount)},execution_day=str(pd.Timestamp(data.current_dt).date()),
         instrument=CFG['instrument'],return_value=rv,accepted_is_not_filled=True)
    if rv<0:
        emit('rejected',signal_day=plan['signal_day'],return_value=rv)

def handle_trade(context,trade):
    # R8: These fields have been observed on real cloud fills.
    emit('trade',day=str(trade.trading_day),instrument=trade.instrument,
         order_key=trade.order_key,direction=str(trade.direction),qty=int(trade.filled_qty),
         price=float(trade.filled_price),money=float(trade.filled_money),commission=float(trade.commission))

def handle_order(context,order):
    # A real order snapshot is diagnostic; it never substitutes for a trade.
    emit('order',snapshot=str(order))

def after_trading(context,data):
    p=context.get_position(CFG['instrument'])
    EVENTS.append(dict(event='account',day=str(pd.Timestamp(data.current_dt).date()),
                       cash=float(context.get_available_cash()),equity=float(context.get_portfolio_value()),
                       qty=int(p.current_qty),available=int(p.avail_qty)))

def export_result(performance):
    raw=performance.raw_perf.copy()
    if raw.empty:
        raise RuntimeError('引擎没有绩效行，不能按零收益通过')
    raw.to_json(OUT/'performance.json',orient='records',date_format='iso',force_ascii=False,indent=2,double_precision=15)
    raw.to_csv(OUT/'performance.csv',index=False)
    (OUT/'events.json').write_text(json.dumps(EVENTS,ensure_ascii=False,indent=2,default=str),'utf-8')
    flat_trades=[dict(day=str(row['date']),**trade) for _,row in raw.iterrows() for trade in row['transactions']]
    pd.DataFrame(flat_trades).to_csv(OUT/'trades.csv',index=False)
    report=dict(status='backtest_executed_pending_independent_reconciliation',
                daily_rows=len(raw),trade_count=len(flat_trades),stats=performance.get_stats(),
                final_equity=float(raw.iloc[-1]['portfolio_value']),output_dir=str(OUT),
                benchmark='沪深300指数；非同ETF扣费买入持有账户',
                sizing='信号日收盘折算80%目标数量，次日开盘实际权重会随跳空变化',
                ending='期末按市值计价，不强制清仓；没有样本外成交')
    (OUT/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),'utf-8')
    print('RESULT_SUMMARY',json.dumps(report,ensure_ascii=False,default=str))
    # Readable plot and artifacts; chart creation never changes trade rules.
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,4))
    nav=raw['portfolio_value']/CFG['capital']
    ax.plot(pd.to_datetime(raw['date']),nav,label='Strategy after costs')
    ax.plot(pd.to_datetime(raw['date']),1+raw['benchmark_period_return'],label='CSI 300 index')
    ax.set(title='ETF MA20 | historical backtest',ylabel='Net asset value')
    ax.grid(alpha=.2);ax.legend();fig.tight_layout()
    fig.savefig(OUT/'equity.png',dpi=140)
    plt.show()
    print('OUTPUT_FILES',', '.join(p.name for p in OUT.iterdir()))
    return report

# R9: explicitly backtest-only; no deployment, scheduler, broker or live mode.
performance=bigtrader.run(market=bigtrader.Market.CN_FUND,frequency='1d',
    instruments=[CFG['instrument']],start_date=CFG['start_date'],end_date=CFG['end_date'],
    capital_base=CFG['capital'],initialize=initialize,before_trading_start=before_trading_start,handle_data=handle_data,
    handle_trade=handle_trade,handle_order=handle_order,after_trading=after_trading,
    benchmark=CFG['benchmark'],before_start_days=0,volume_limit=1,
    order_price_field_buy='open',order_price_field_sell='open',
    backtest_only=True,render=None,report_output_path=False)
SUMMARY=export_result(performance)
print('COMPLETE_BACKTEST_FINISHED')
