# 黄同学｜v7教学走查 / JQ-DEMO-1.2 / 2026-11-05
# 仅聚宽云端策略；规则见02_教学规则卡.md。非实盘脚本。
from jqdata import *
import pandas as pd
import numpy as np
import datetime as dt

VERSION = 'JQ-DEMO-1.2'

def initialize(context):
    # E1/E2：云端、沪深300基准、动态复权、限制未来数据。
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    log.set_level('order', 'error')  # 保留真实错误；自有委托/成交日志仍完整输出。
    # E3：本例2024年；卖出税万五、佣金万三、最低5元。
    set_order_cost(OrderCost(open_tax=0, close_tax=0.0005,
        open_commission=0.0003, close_commission=0.0003,
        close_today_commission=0, min_commission=5), type='stock')
    set_slippage(PriceRelatedSlippage(0.002))
    g.pending_sells = {}
    g.blocked = set()
    g.last_month = None
    g.audit = []
    # R5：分开交易时段执行与盘后检查；日频模拟的实际调度需再验证。
    run_daily(execute, time='09:31')
    run_daily(check_after_close, time='15:30')
    log.info('VERSION %s | 累计净利润同比来自原始财报配对，不用单季indicator替代', VERSION)

def clean_num(x):
    try:
        return np.isfinite(float(x))
    except (ValueError, TypeError):
        return False

def cumulative_growth(codes, asof):
    """R2：只看asof前已公告的最新累计报表，与同一公告的上年同期对比数配对。"""
    table = finance.STK_INCOME_STATEMENT
    parts = []
    # 小批次避免run_query单次3000条上限导致静默截断。
    for start in range(0, len(codes), 40):
        batch = codes[start:start+40]
        q = query(table.id, table.code, table.pub_date, table.start_date,
                  table.end_date, table.report_date, table.report_type,
                  table.net_profit).filter(
            table.code.in_(batch), table.pub_date <= asof,
            table.end_date <= asof,
            table.start_date >= dt.date(asof.year-2,1,1),
            table.report_type.in_([0,1])
        ).order_by(table.pub_date.desc()).limit(3000)
        frame = finance.run_query(q)
        if len(frame) >= 3000:
            raise RuntimeError('财务查询触及3000条上限，须缩小批次，不可使用截断结果')
        if not frame.empty:
            parts.append(frame)
    if not parts:
        return {}
    data = pd.concat(parts, ignore_index=True)
    for col in ['pub_date','start_date','end_date','report_date']:
        data[col] = pd.to_datetime(data[col])
    result = {}
    for code, frame in data.groupby('code'):
        current = frame[(frame.report_type == 0)
            & (frame.start_date.dt.month == 1)
            & (frame.start_date.dt.day == 1)
            & (frame.start_date.dt.year == frame.end_date.dt.year)]
        if current.empty:
            continue
        current = current.sort_values(['end_date','pub_date','id'], ascending=[False,False,False])
        r = current.iloc[0]
        previous_end = r.end_date - pd.DateOffset(years=1)
        prior = frame[(frame.report_type == 1)
            & (frame.pub_date == r.pub_date)
            & (frame.report_date == r.report_date)
            & (frame.end_date == previous_end)
            & (frame.start_date.dt.month == 1)
            & (frame.start_date.dt.day == 1)]
        if prior.empty:
            log.info('DATA_SKIP code=%s reason=同期累计数未配对 report=%s', code,r.end_date.date())
            continue
        p = prior.sort_values('id',ascending=False).iloc[0]
        now, old = r.net_profit, p.net_profit
        if not clean_num(now) or not clean_num(old) or old == 0:
            continue
        growth = (float(now)-float(old))/abs(float(old))*100.0
        result[code] = dict(growth=growth, current=float(now), prior=float(old),
            report=str(r.end_date.date()), pub=str(r.pub_date.date()))
    return result

def select_targets(context):
    # R1/R2：历史成分与估值为上一交易日已知信息，缺失跳过、PE同分按代码排。
    asof = context.previous_date
    pool = get_index_stocks('000300.XSHG', date=asof)
    q = query(valuation.code, valuation.pe_ratio).filter(
        valuation.code.in_(pool),valuation.pe_ratio>0,valuation.pe_ratio<20)
    vals = get_fundamentals(q,date=asof).dropna(subset=['code','pe_ratio'])
    vals = vals.sort_values(['pe_ratio','code'])
    if vals.empty:
        return [],{}
    finances = cumulative_growth(vals.code.tolist(),asof)
    # 停牌过滤使用asof历史值；执行时仍检查当天真实可交易状态。
    prices = get_price(vals.code.tolist(),end_date=asof,count=1,
        frequency='daily',fields=['paused'],panel=False)
    paused = dict(zip(prices.code,prices.paused)) if not prices.empty else {}
    selected=[]; details={}
    for row in vals.itertuples():
        code=row.code
        if code not in finances or finances[code]['growth'] <= 0:
            continue
        if code not in paused or paused[code] != 0:
            continue
        selected.append(code)
        details[code]=dict(finances[code],pe=float(row.pe_ratio))
        if len(selected)==10:
            break
    log.info('REBALANCE signal_asof=%s selected=%s candidate_count=%s',asof,selected,len(selected))
    for code in selected:
        r=details[code]
        log.info('SELECT code=%s PE=%.4f 累计净利同比=%.4f%% 报告期=%s 公告日=%s 累计当期=%.2f 累计上期=%.2f',
            code,r['pe'],r['growth'],r['report'],r['pub'],r['current'],r['prior'])
    return selected,details

def amount(context,code):
    p=context.portfolio.positions[code] if code in context.portfolio.positions else None
    return int(p.total_amount) if p else 0

def place_target(context,code,target_value,reason):
    """E4：目标订单与实际成交分开；只记录平台真实返回。"""
    data=get_current_data()[code]
    before=amount(context,code)
    if data.paused:
        log.info('BLOCK code=%s reason=停牌 action=%s holding=%s',code,reason,before)
        return None
    p=context.portfolio.positions[code] if code in context.portfolio.positions else None
    current=float(p.value) if p else 0.0
    # 小额调仓不足一手时先跳过，避免平台反复报数量小于100。
    # 全部退出不受此门槛限制，零股仍交给平台处理。
    if target_value>0 and abs(target_value-current)<100*float(data.last_price):
        log.info('SKIP_LOT code=%s reason=调仓差额不足100股 holding=%s target=%.2f',code,before,target_value)
        return None
    is_sell=target_value<current
    if (is_sell and data.last_price<=data.low_limit) or (not is_sell and data.last_price>=data.high_limit):
        log.info('BLOCK code=%s reason=涨跌停 action=%s holding=%s',code,reason,before)
        return None
    if is_sell and (not p or p.closeable_amount<=0):
        log.info('BLOCK code=%s reason=无可卖量 action=%s',code,reason)
        return None
    before_cash=float(context.portfolio.available_cash)
    o=order_target_value(code,target_value)
    after=amount(context,code)
    log.info('ORDER code=%s reason=%s target_value=%.2f order_id=%s status=%s filled=%s before=%s after=%s before_cash=%.2f cash=%.2f',
        code,reason,target_value,getattr(o,'order_id',None),getattr(o,'status',None),getattr(o,'filled',None),
        before,after,before_cash,context.portfolio.available_cash)
    g.audit.append(dict(time=str(context.current_dt),code=code,reason=reason,
        target=target_value,before=before,after=after,order_id=str(getattr(o,'order_id',None))))
    return o

def execute(context):
    # R4/R5：严格自然月首个交易日；回测从月中开始不强行首日调仓。
    today=context.current_dt.date()
    first=str(get_trade_days(start_date=today.replace(day=1),end_date=today)[0])[:10]==str(today)
    monthly=first and g.last_month!=(today.year,today.month)
    # 止损卖出先于月度调仓。待卖队列保留，未成交不伪装已退出。
    forced=set(g.pending_sells)
    for code in sorted(forced):
        if amount(context,code)>0:
            place_target(context,code,0,g.pending_sells[code]+'_下一交易时段重试')
        if amount(context,code)==0:
            g.pending_sells.pop(code,None)
    if not monthly:
        return
    g.last_month=(today.year,today.month)
    # 下次月调仓可重入；今天尚处止损队列的股票仍不立即买回。
    g.blocked=set(forced)
    targets,details=select_targets(context)
    targets=[x for x in targets if x not in forced]
    # R4：调仓时未进入前10名者卖出；卖不出继续进入待卖队列。
    for code in list(context.portfolio.positions):
        if code not in targets:
            place_target(context,code,0,'月调仓_不在当前目标前10')
            if amount(context,code)>0:
                g.pending_sells[code]='调仓未完成退出'
    total=float(context.portfolio.total_value)
    target=total*0.10  # R3：每只目标10%；不足10只留现金，不均分满仓。
    # 先减仓，再按实际可用现金加仓。目标仍10%，整手/费用可能略低配。
    for code in targets:
        p=context.portfolio.positions[code] if code in context.portfolio.positions else None
        if p and p.value>target:
            place_target(context,code,target,'月调仓_调整至10%目标')
    for code in targets:
        p=context.portfolio.positions[code] if code in context.portfolio.positions else None
        current=float(p.value) if p else 0.0
        need=target-current
        if need<=0:
            continue
        usable=max(0,(float(context.portfolio.available_cash)-5.0)/1.0013)
        if usable<=0:
            log.info('CASH_SKIP code=%s cash=%.2f',code,context.portfolio.available_cash)
            continue
        place_target(context,code,current+min(need,usable),'月调仓_低PE且累计净利增长_目标10%')

def check_after_close(context):
    # R4：当日盘后收盘价，严格小于持仓动态avg_cost（本例实测不含买佣）的90%才触发。
    # use_real_price令价格与平台除权处理后的持仓avg_cost处于同一时点口径。
    today=context.current_dt.date()
    for code,p in list(context.portfolio.positions.items()):
        prices=get_price(code,end_date=today,count=1,frequency='daily',
            fields=['close','paused'],fq='pre')
        if prices.empty or prices.iloc[-1]['paused']!=0 or p.avg_cost<=0:
            continue
        close=float(prices.iloc[-1]['close'])
        if close<float(p.avg_cost)*0.90 and code not in g.pending_sells:
            g.pending_sells[code]='止损'
            g.blocked.add(code)
            log.info('STOP_SIGNAL code=%s close=%.4f avg_cost=%.4f threshold=%.4f execute=下一交易时段',
                code,close,p.avg_cost,float(p.avg_cost)*0.90)
    for tid,t in get_trades().items():
        log.info('TRADE trade_id=%s order_id=%s code=%s amount=%s price=%s time=%s',
            tid,t.order_id,t.security,t.amount,t.price,t.time)
    log.info('HOLDINGS %s cash=%.2f total=%.2f',
        {code:int(p.total_amount) for code,p in context.portfolio.positions.items()},
        context.portfolio.available_cash,context.portfolio.total_value)
    # 原始小账保留到私有策略文件，供真实运行结束后导出核对。
    write_file('huang_v7_order_audit.json',pd.DataFrame(g.audit).to_json(orient='records',force_ascii=False),append=False)
