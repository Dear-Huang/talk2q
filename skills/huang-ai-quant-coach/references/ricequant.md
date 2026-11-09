# 米筐｜云端、Plus、开源分开适配

先识别米筐云端、RQAlpha Plus本地、开源RQAlpha；RQData是数据服务，不自动提供回测引擎和全部财务权限。依据2026-11-04官方文档；当前产品/版本还须核对。

- Plus常见`init(context)`、`handle_bar(context, bar_dict)`，不能用聚宽`initialize`顶替。`order_target_percent(id_or_ins, percent, ...)`为目标权重，证券代码以元数据为准。
- `history_bars`的`fields`、`include_now`、`skip_suspended`、`adjust_type`、返回数组形状按当前API核实；多个字段不要默认当DataFrame。
- 文档区分日频盘前的T−1日线与日频`handle_bar`的T日线；“不含当前bar”不能代替可得时点检查。财务因子需核对具体目录、权限和公告日。
- 盘前/盘后是否可下单、撮合模式由实际产品核实。项目中曾在开源6.4.2观察到日频`next_bar`退化为当bar收盘；不能推断Plus相同，也不能因参数被接受就说实现次日开盘。
- 集合竞价路径是否应用滑点需用真实成交核对；不能把“配置有滑点”当作成交已计滑点。
- 输出策略、产品对应配置、数据依赖与启动方法。费用、撮合、信号/成交时间、首日调仓、未成交余量均对账；无基本面权限时不删除选股条件。

官方：[回调](https://www.ricequant.com/doc/rqalpha-plus/api/callback)、[订单](https://www.ricequant.com/doc/rqalpha-plus/api/order-api)、[数据](https://www.ricequant.com/doc/rqalpha-plus/api/data-api)、[开源API](https://rqalpha.readthedocs.io/zh-cn/latest/api/base_api.html)。

## 2026-11-09 开源6.4.2实际运行补充

本节来自真实开源引擎处理合成行情，不是米筐云端/Plus执行证明，也不是历史收益。

|访问路径|6.4.2实际对象|数量/可卖字段|
|---|---|---|
|`get_position(symbol)`|`Position`|`quantity` / `closable`|
|`context.portfolio.positions[symbol]`|旧`StockPositionProxy`|`quantity` / `sellable`|

两条路径的字段不能混用。本轮初版在卖出分支对旧代理读`closable`触发`AttributeError`；改用`get_position`后完整引擎买卖通过。有限预检可指定`--engine rqalpha642`捕捉直接赋值的此类混用，动态包装仍需运行。

已验证的开盘路径是`before_trading`读取带`datetime/close`的20条日线（T−1截止、`include_now=False`），`open_auction(context, bar_dict)`读取当日`open`尝试交易。竞价bar不提供完整当日close；日频事件时间可显示00:00，验收应同时看事件阶段、数据日期和真实成交价。此处0滑点案例通过，不能推出非零滑点也适用。

费用按实际品种核对。当前开源配置使用`stock_min_commission`；Plus官方配置页列`cn_stock_min_commission`，不可无核验共用。开源默认股票万八基数下乘0.375才是万三；ETF还要核对元数据类型及`etf_commission.default.commission_rate/min_commission`实际生效。至少同时覆盖比例佣金与最低收费、买入与卖出；本例ETF税0不自动套到股票。

卖出成交事件中的现金可能尚未包含应收卖款，不能和结算后现金直接相减。本轮卖出事件先扣费，卖款在结算后体现；独立小账使用`POST_SETTLEMENT`的现金。日志应写清`cash_asof`，并分别检查现金、可用资金和应收款。

最低测试集合：首日已有足够外部前史、历史不足、低资金不足一手加佣金、已有持仓不再平衡、最低佣金、整笔拒绝及部分成交。若规则为“有仓不再平衡”，部分买入后不能次日偷偷补足。停牌或涨跌停未成交要保留实际残余并按规则重算。

只有用户明确采用相同规则和教学假设时，才使用[已测开源ETF均线示例](../assets/rqalpha-etf-ma20/说明.md)，不自动把示例参数套给新用户。

官方配置入口：https://www.ricequant.com/doc/rqalpha-plus/api/config 。Plus和云端仍需在目标环境分别验收。

## 指定因子：2026-11-09接口与目录核验

- 精确字段示例：PE可为`pe_ratio_ttm`或`pe_ratio_lyr`；`return_on_equity_ttm`与`return_on_equity_diluted_ttm`是不同分母定义。中文只说“PE/ROE”时先澄清，不能自动选一个。
- 官方`return_on_equity_ttm`公式为`2*net_profit_parent_company_ttm_0/(equity_parent_company_ttm_0+equity_parent_company_ttm_1)`；资产负债表TTM使用滚动4季平均，不能改成常见期初期末权益后声称等价。`return_on_equity_diluted_ttm`使用单个权益TTM分母。官网公式无乘100，但真实数值尺度未授权取样，设阈值前核对。
- Plus回测`rqalpha.api.get_factor(order_book_ids, factors, count=1, universe=None, expect_df=False)`按引擎T−1截断；RQData本地`rqdatac.get_factor(..., factor, start_date=asof, end_date=asof, expect_df=True)`走显式日期。二者参数不能混用。开源引擎导出了包装函数，也可能因为没有rqdatac或数据权益而失败，本轮未完成真实财务取数。
- `get_all_factor_names()`先核对目标账号可用精确ID；输出通常为`order_book_id/date`多层索引DataFrame，按轴名称重排和连接，不按位置猜。历史指数池先显式`index_components(..., date=asof)`，`get_factor`的`universe`不代替历史成分选择。
- 内置`ROC`默认12日，`MTM`默认14日绝对价差，不等于20日收益动量。用户确认收益公式后，自定义21价`C(D)/C(D-20)-1`并明确复权和停牌计数，不能偷换现成指标。
- 平台PIT说明与逐条公告审计分开。内置因子返回不含逐行原公告时间时，不虚构`info_date`；需独立审计时按当前原始财报目录取有权限PIT数据及公告/修订记录。无权益时保留因子条件，提供官方授权导出或合法用户PIT表契约。

官方：[Plus数据API](https://www.ricequant.com/doc/rqalpha-plus/api/data-api)、[RQData股票与因子目录](https://www.ricequant.com/doc/rqdata/python/stock-mod)。上述定义已查公开文档和本地wrapper，真实因子值/云端/Plus仍未执行。
