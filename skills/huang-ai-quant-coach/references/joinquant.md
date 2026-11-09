# 聚宽｜云端策略适配规则

适用：聚宽网页云端策略/回测。核对依据为2026-11-04取得的官方API正文；不是平台运行证明。先辨认用户所处入口，不能把本地JQData取数脚本当云端策略。

## 代码契约

| 项 | 本环境规则 | 常见错误 |
|---|---|---|
| 导入 | `from jqdata import *`；因子接口按需从`jqfactor`导入 | 换成本地`jqdatasdk`后仍调用云端下单函数 |
| 初始化 | `initialize(context)` | 套用米筐的`init`或掘金的调度方式 |
| 定时函数 | `run_daily(my_callback, time=...)`注册的函数通常只接`context` | 定义成`my_callback(context, data)`导致缺参数 |
| 逐bar函数 | `handle_data(context, data)`；与定时回调区分 | 为同一交易逻辑同时注册两条路径导致重复下单 |
| 股票代码 | 常见`600000.XSHG`、`000001.XSHE`，以元数据为准 | 直接用BigQuant的`.SH/.SZ` |
| 目标下单 | `order_target_value(code, target_value)`为目标市值；检查返回值与成交 | 把目标市值当成每次新增买入金额 |
| 持仓与现金 | `context.portfolio.positions`、`available_cash`；可卖量核对`closeable_amount` | 发卖单后按理想回款发全部买单 |
| 日内订单/成交 | `get_orders()`、`get_trades()`是当日查询 | 以为能直接查全回测历史；假定Trade有`commission`、`is_buy`字段 |

## 数据与财报

1. 指数池用`get_index_stocks(index_code, date=asof)`，不能把今天的沪深300成分回填全历史。`get_all_securities(..., date=asof)`只解决历史存续池；其最新名称不能直接作历史ST过滤。
2. 历史ST可查`get_extras('is_st', codes, end_date=asof, count=1, df=True)`；停牌过滤与实际可成交检查分开。不能因缺值默默把股票当正常。
3. `get_fundamentals(query_object, date=asof)`按该日可得财务信息查询；`date`和`statDate`不能同时传。`statDate`是报告期查询，不能据此宣称已处理公告时点。核对具体表/字段：估值PE、累计/单季净利润同比、单位与空值政策，不能只凭相似字段名猜。
4. 多证券`get_price(..., panel=False)`先检查返回列`time/code`和字段；不把单证券宽表索引方式直接套多证券长表。空表、停牌、上市不足期要有已确认处理规则。
5. `history/attribute_history`不含当日；盘后需要今天日线时，核对`get_price(end_date=今天, ...)`及可得时点。取数传明确日期，不能用系统真实今天替代回测时间。
6. 因子`get_factor_values(..., end_date=asof, count=1)`返回字典，各因子值为日期×证券的DataFrame；不要当成单张表。百分比字段核对比例/百分数单位。
7. `use_real_price`、`avoid_future_data`可以启用，但不能代替每个字段的时点检查。复权价格、持仓成本与止损基准保持一致。

## 调度、费用和成交

- 盘后检查止损与次日交易时段执行分成两个回调/事件；盘后信号只写待执行状态，不能拿盘后订单当次日已成交。
- `run_monthly`的回测首月边界要检查；若用户说自然月首个交易日，用交易日历核对实际日期，不随意把首日延后。
- 费用使用当前云端支持的`OrderCost`及`set_order_cost`，区分佣金、最低收费、税费；跨税制变化日期要分段，费率由卡确认。不要复制一个示例税率覆盖所有历史。
- `PriceRelatedSlippage(0.002)`描述的价差为往返0.2%，不能解释为单边0.2%；单边/往返参数先核对文档再填。
- 下单返回`None`、部分成交、涨跌停、T+1、整手、费用预留都要实际处理；下单日志、成交日志、真实持仓各留证据。卖不出时按已确认规则重试，不能无条件删掉仓位。
- 回测面板日期、资金、频率、基准仍需设置；云端API不能在普通本地Python导入成功，不据此判定云端代码错误。

## 出码前最少核对

读官方相应函数；确认平台/入口→字段与日期口径→回调签名→信号/委托/成交时间→费用→订单与持仓核对。先做最小取数检查（列名、类型、日期范围、首几行），再跑完整策略；不为了跑通删掉财务条件。

官方：[API](https://www.joinquant.com/help/api/help?name=api)、[因子](https://www.joinquant.com/help/api/help?name=factor_values)。来源记录见[sources.json](sources.json)。

## 2026-11-05 聚宽真实走查补充

以下属于本次云端教学案例的实测，不能推广为所有策略或平台均已验证。

- **累计不是单季。** `indicator.inc_net_profit_year_on_year`对应单季度同比，不可替代累计口径。2024-01-02的真实探针中，000001.XSHE该字段为−2.22%，而截至2023-12-29已公告的累计净利润为396.35亿元、同期366.59亿元，累计增长+8.1181%。
- 本例累计口径使用`finance.STK_INCOME_STATEMENT`的`net_profit`，这是净利润，不能擅自换成`np_parent_company_owners`归母净利润。查询`finance.run_query(query(...))`；实际列有`id/code/pub_date/start_date/end_date/report_date/report_type/net_profit`，ORM对象不支持凭猜测调用`.__table__`。
- 同时限制`pub_date<=信号asof`、`end_date<=asof`；选最新已公告、当年1月1日起的累计报告。在本例实测记录中`report_type=0`为当期、`1`为同公告上年同期对比数，以代码、公告日、report_date及前一年end_date配对；先用目标股票和日期小样本确认，不把此观察当所有财报表的通用枚举。增长=(当期−同期)/abs(同期)，同期0或缺失跳过。这是本例已确认定义，其他策略先问。
- `finance.run_query`有3000行上限；分批查询并检测触顶，不能把被截断数据直接拿去排序。已附教学代码按40只一批查询，本批次大小仍需按查询跨度检查。
- **整手先检查。** 目标市值调整不足一手会报开仓/平仓数量小于100；非清仓目标先检查差额，日志记“跳过不足一手”，全部退出仍按可卖数量处理。不要用吞掉所有订单错误来解决。
- 页面进入：聚宽公司首页→聚宽量化研究平台→策略回测→新建策略→空白模版。所谓空白模版仍带默认策略，须全选替换，避免混入两套initialize和旧税率。日期框通过日历选年/月/日，不能当普通输入框直接键入。
- 本次观察到免费CPU额度为60分钟，额度与收费以账号当日页面为准；未购买额外算力。本次日志导出提示消耗3积分，未确认扣分。页面只展示前100条日志、前1000条持仓记录；截图要等加载完成，后段核对可另建只精简日志的同规则回测，不能补造记录。
- 模拟位会占满。只新建用户授权的独立教学策略；不自行关闭旧策略。模拟弹窗资金默认10000，本例手工改成100000；频率选“每天”、Python3，实际开始日期默认下一日。创建后设置页显示“未开始”，概述角标可显示“进行中”，必须同时看开始时间与首次回调。
- 本例自然月首个交易日才选股；月中启动先空仓并非出错。不要为了截图悄悄增加“启动首日买入”。模拟代码与回测代码分别存储，修改回测后要核对是否需要显式“替换代码”，不能假定自动同步。

官方API：https://www.joinquant.com/help/api/help?name=api 。本次2024年回测不代表未来收益或2026年模拟已执行。

- **不要猜均价含费。** 本次600926.XSHG买入900股、成交价15.37、另收买佣5元，真实`avg_cost`仍为15.370000。教程采用这个动态均价作为止损基准；若用户要求含费成本，要另外明确维护口径，不能仅给avg_cost贴上“含手续费”的标签。

## 2026-11-09 云端命名覆盖问题

`from jqdata import *`可能覆盖Python内置的`any/all/sum/min/max`。本轮真实云端初版的20条价格均正常，但未限定的`any(generator)`把无效价格条件始终判真，回测完成却0交易；本地桩未模拟此命名覆盖，13项检查通过仍漏检。

Python迭代器/标量运算显式`import builtins`并使用`builtins.any/sum/min/max`等；NumPy数组聚合显式`np.any/np.sum`，不混用。涉及拒绝全部信号/0交易时先打印原始样本、实际条件与函数来源，不能先改策略阈值。有限预检已拦截“jqdata通配导入＋未限定any/all生成器”的已观察模式；它不能替代真实云端运行，也不能穷举全部命名覆盖。

真实云端诊断证实`any/all/sum.__module__`为`numpy.core.fromnumeric`，`min/max`仍为builtins；不要将所有同名函数一概称为已覆盖。只改内置函数来源的V2在2024-01-02至2024-06-28本例完成12笔真实成交，逐笔佣金与成交日现金复核一致；这是ETF均线单例的证据，不能推出任意因子策略都已运行通过。

用户明确采用相同规则时可读[已测ETF均线示例](../assets/joinquant-etf-ma20/说明.md)。复杂因子先按[因子工作流](factors.md)确认口径，不能为了复用示例把财务/因子需求改成均线。

## 指定因子：2026-11-09真实小样本取数

- `jqfactor.get_all_factors()`核对精确ID；`get_factor_values(securities, factors=['roe_ttm'], end_date=asof, count=2)`在两个历史回调日均真实返回字典，`roe_ttm`值为日期×证券的DataFrame。本次3只样本shape为(2,3)，用日期和证券名对齐，不能按`.values`位置拼PE。
- 官方`roe_ttm`是净利润(TTM)/期末股东权益，不是加权平均净资产收益率。真实原值如0.104091表示比例；按百分比设阈值前做显式换算。`valuation.pe_ratio`为PE TTM，本例用`get_fundamentals(..., date=asof)`真实取数；用户泛称PE仍应确认类型。
- 官方库`momentum`是滞后21交易日、过去504日超额对数收益指数加权（半衰期126）并带风格处理，不能替代用户要求的20日收益。用截至asof的21个收盘价自算`P_t/P_t_minus20-1`，并确认复权/停牌口径。
- 自定义名不要求先在平台因子库注册。本次探针`skill_custom_mom20`不在官方目录，确认公式后由已授权价格在代码内计算，六个实际日期/证券结果已独立复算。此证明可自定义计算，不代表因子有效或完整多因子策略回测通过。
- pandas矩阵`to_dict()`可能以Timestamp作字典键，`json.dumps(default=str)`也不会转换这些键。本次取数已成功却日志TypeError；修复为显式日期字符串/证券/数值记录，保留真实shape和日期。不把日志序列化失败误判为因子无权限。

只验证两个历史日、3只样本及上述字段；全股票池、月度排名/持仓与其他因子另验。可按需参考[只读取数示例](../assets/factor-examples/joinquant/probe.py)，它不下单、不自动变更用户策略。官方：[因子库](https://www.joinquant.com/help/api/help?name=factor_values)。
