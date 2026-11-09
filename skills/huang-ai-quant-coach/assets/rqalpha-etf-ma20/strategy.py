# 规则卡 V1 / 技术修复 V2：已确认。目标米筐云端/RQAlpha Plus；本地开源兼容结果单列。
import math
import json
from rqalpha.api import *

def _log(context, kind, **values):
    row = dict(kind=kind, now=str(context.now), symbol=context.symbol, **values)
    logger.info(json.dumps(row, ensure_ascii=False, default=str))

def init(context):
    # R1 单标的；R3 仅空仓买入80%，持仓不再平衡。
    context.symbol = '510300.XSHG'
    context.signal = None
    context.orders_today = []
    update_universe(context.symbol)

def before_trading(context):
    # R2/R5 前一交易日收盘与包括该日在内20交易日均线，盘前仅T-1。
    context.signal = None
    context.orders_today = []
    bars = history_bars(context.symbol, 20, '1d', ['datetime', 'close'],
                        skip_suspended=False, include_now=False, adjust_type='none')
    if bars is None or len(bars) < 20:
        _log(context, 'signal_skip', reason='fewer_than_20', count=0 if bars is None else len(bars))
        return
    closes = bars['close']
    if not all(math.isfinite(float(x)) and x > 0 for x in closes):
        _log(context, 'signal_skip', reason='invalid_close')
        return
    ma = sum(float(x) for x in closes) / 20
    context.signal = float(closes[-1]) > ma
    _log(context, 'signal', data_time=int(bars['datetime'][-1]),
         close=float(closes[-1]), ma20=ma, buy=context.signal, count=len(bars))

def open_auction(context, bar_dict):
    # R5 今日开盘尝试，委托与成交分开；不在handle_bar补单。
    if context.signal is None:
        return
    pos = get_position(context.symbol)
    qty = int(pos.quantity)
    bar = bar_dict[context.symbol]
    price = float(bar.open)
    if not math.isfinite(price) or price <= 0:
        _log(context, 'skip', reason='invalid_open')
        return
    if context.signal and qty == 0:
        # R3/R6 目标市值不超过80%净值，100股整手且保留真实佣金。
        target = context.portfolio.total_value * 0.8
        shares = int(target / price / 100) * 100
        cash = float(context.portfolio.cash)
        while shares > 0 and shares * price + max(5.0, shares * price * 0.0003) > cash:
            shares -= 100
        if shares <= 0:
            _log(context, 'skip', reason='less_than_one_lot_after_fee', cash=cash, open=price)
            return
        if price >= float(bar.limit_up):
            _log(context, 'skip', reason='limit_up', open=price)
            return
        order = order_shares(context.symbol, shares)
        _record_order(context, order, 'buy', shares, price)
    elif not context.signal and qty > 0:
        # R4 前日收盘<=均线清仓；T+1/停牌/涨跌停仍由真实引擎约束。
        if price <= float(bar.limit_down):
            _log(context, 'skip', reason='limit_down', open=price)
            return
        shares = int(pos.closable)
        if shares > 0:
            order = order_shares(context.symbol, -shares)
            _record_order(context, order, 'sell', shares, price)

def _record_order(context, order, side, shares, price):
    if order is not None:
        context.orders_today.append(order)
    _log(context, 'order_submit', side=side, requested=shares, open=price,
         order_id=None if order is None else order.order_id,
         status=None if order is None else str(order.status),
         filled=None if order is None else order.filled_quantity)

def handle_bar(context, bar_dict):
    pass

def after_trading(context):
    # R6 日内残单撤销，次日重算；不把提交订单当作成交。
    for order in context.orders_today:
        _log(context, 'order_end', order_id=order.order_id, status=str(order.status),
             filled=order.filled_quantity, quantity=order.quantity)
    for order in get_open_orders():
        cancel_order(order)
    pos = get_position(context.symbol)
    _log(context, 'account', quantity=int(pos.quantity), cash=float(context.portfolio.cash),
         total_value=float(context.portfolio.total_value))
