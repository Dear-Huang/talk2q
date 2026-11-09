# 规则卡 JQ-MA20-20261109，聚宽网页云端，Python3。
from jqdata import *
import math
import json
import builtins


def initialize(context):
    log.info('runtime namespace ' + json.dumps({name: {'module': str(getattr(globals().get(name, getattr(builtins, name)), '__module__', None)), 'repr': str(globals().get(name, getattr(builtins, name)))} for name in ['any', 'all', 'sum', 'min', 'max']}, sort_keys=True))
    # R1/R6：单只ETF，同标的基准；使用真实价格成交。
    g.security = '510300.XSHG'
    set_benchmark(g.security)
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    # R7：教学费用，基金双边万三，最低5元；不收印花税；滑点0。
    set_order_cost(OrderCost(open_tax=0, close_tax=0,
                            open_commission=0.0003, close_commission=0.0003,
                            close_today_commission=0, min_commission=5), type='fund')
    set_slippage(FixedSlippage(0))
    # R5：仅开盘尝试；不注册其他买卖路径。
    run_daily(at_open, time='09:30', reference_security=g.security)
    run_daily(audit_close, time='15:30', reference_security=g.security)


def emit(event, **values):
    values['event'] = event
    log.info(json.dumps(values, ensure_ascii=False, default=str, sort_keys=True))


def at_open(context):
    # R2：前一交易日结束的20条日线，包含该日；未复权实际收盘。
    asof = context.previous_date
    frame = get_price(g.security, end_date=asof, count=20, frequency='daily',
                      fields=['close'], skip_paused=False, fq=None)
    if frame is None or len(frame) != 20:
        emit('skip_history', time=context.current_dt, asof=asof,
             rows=0 if frame is None else len(frame))
        return
    closes = [float(x) for x in frame['close'].values]
    if builtins.any(not math.isfinite(x) or x <= 0 for x in closes):
        emit('skip_invalid_history', time=context.current_dt, asof=asof)
        return
    # 数据时点独立防线：最后一条必须恰为前一交易日。
    if frame.index[-1].date() != asof:
        emit('skip_history_date', time=context.current_dt, asof=asof,
             last_data_time=frame.index[-1])
        return
    mean20 = builtins.sum(closes) / 20.0
    bullish = closes[-1] > mean20
    position = context.portfolio.positions.get(g.security)
    held = int(position.total_amount) if position is not None else 0
    emit('signal', time=context.current_dt, asof=asof,
         last_data_time=frame.index[-1], close=closes[-1], ma20=mean20,
         bullish=bullish, held=held, cash=context.portfolio.available_cash)
    # R3：任何正持仓均不补仓、不再平衡，含前次部分成交。
    if bullish and held > 0:
        emit('hold_no_rebalance', time=context.current_dt, held=held)
        return
    if not bullish and held == 0:
        return
    current = get_current_data()[g.security]
    price = float(current.day_open)
    # R8：不强制撮合；停牌或开盘价无效不下单。
    if current.paused or not math.isfinite(price) or price <= 0:
        emit('skip_untradable', time=context.current_dt, paused=current.paused, price=price)
        return
    if bullish:
        if price >= current.high_limit:
            emit('skip_limit_up', time=context.current_dt, price=price)
            return
        # R3/R8：最多80%净值对应的整手；现金另外预留最低佣金。
        cash = float(context.portfolio.available_cash)
        target = 0.8 * float(context.portfolio.total_value)
        amount = int(builtins.min(target, builtins.max(0.0, cash - 5.0)) / price / 100) * 100
        while amount > 0 and amount * price + builtins.max(5.0, amount * price * 0.0003) > cash:
            amount -= 100
        if amount < 100:
            emit('skip_less_than_lot', time=context.current_dt, cash=cash, price=price)
            return
        reason = 'previous_close_above_ma20'
    else:
        # R4/R8：失效尝试清仓，保留T+1等实际不可卖余量。
        if price <= current.low_limit:
            emit('skip_limit_down', time=context.current_dt, price=price)
            return
        closeable = int(position.closeable_amount)
        if closeable <= 0:
            emit('skip_no_closeable', time=context.current_dt, held=held)
            return
        amount = -builtins.min(held, closeable)
        reason = 'previous_close_at_or_below_ma20'
    result = order(g.security, amount)
    if result is None:
        emit('order_rejected', time=context.current_dt, amount=amount, reason=reason)
        return
    emit('order_result', time=context.current_dt, reason=reason,
         order_id=result.order_id, amount=result.amount, filled=result.filled,
         price=result.price, status=str(result.status), commission=result.commission)
    # R5/R8：只尝试开盘一次；撤销剩余，下一交易日重新计算信号。
    for pending in get_open_orders().values():
        if pending.security == g.security:
            cancel_order(pending)
            emit('cancel_remainder', time=context.current_dt, order_id=pending.order_id)


def audit_close(context):
    # R9：实际订单、成交与持仓分开记录；Trade不猜佣金字段。
    orders = get_orders()
    trades = get_trades()
    for item in orders.values():
        emit('daily_order', time=context.current_dt, order_id=item.order_id,
             is_buy=item.is_buy, amount=item.amount, filled=item.filled,
             price=item.price, status=str(item.status), commission=item.commission)
    for item in trades.values():
        emit('daily_trade', time=item.time, trade_id=item.trade_id,
             order_id=item.order_id, security=item.security,
             amount=item.amount, price=item.price)
    position = context.portfolio.positions.get(g.security)
    emit('daily_account', time=context.current_dt,
         held=0 if position is None else position.total_amount,
         cash=context.portfolio.available_cash,
         total_value=context.portfolio.total_value)
