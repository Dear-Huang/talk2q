# BigQuant｜先锁定引擎入口，再写代码

依据2026-11-04官方章节与后续版本核验记录。平台持续更新；下列版本差异用于防混用，不代表云端目前固定安装该版本。2026-11-09新增云端0.1.11完整教学例真实回测与对账，见[完整交付与云端实测](bigquant-complete.md)；此前本地6.0.3取数鉴权失败的证据仍保留，两者分别记录。

## 必问的环境区别

新用户找不到代码框时，先读[代码入口与用户材料](bigquant-entry.md)，帮助进入AIStudio，按截图/模板识别环境；优先交付可打开的完整Notebook，不要求用户先懂API名称。

先问“你在BigQuant哪个入口运行？能否提供当前空白模板或版本信息？”如果已经提供，就不重复问。至少区分：

- Python `from bigquant import bigtrader` + `bigtrader.run(...)`。
- 模块化/Notebook `from bigmodule import M` + `M.bigtrader.v30(...)`（模块版本以实际模板为准）。

二者不是一段代码替换函数名的关系。回调、传入数据、引擎参数、费用类和结果读取沿同一个实际可运行模板走。没有锁定入口时继续规则卡，不猜一套最终代码。

## 数据准备必须交付

1. DAI先核对官方数据字典中真实表名/字段/类型/权限、`date`与`instrument`、日期覆盖。财务字段要能证明在信号日已公告；表里有报告期不代表有可得时点。
2. 股票、ETF、期货数据不能从一个表的演示推导另一个品种。证券常见`.SH/.SZ`后缀，按元数据映射，不能照搬`.XSHG/.XSHE`。
3. SQL、因子计算与回调里各自处理日期时，写清信号日和执行日。官方引擎说明当前bar下单下一bar开始撮合；目标入口、开/收盘成交配置还须核实。不能在SQL和引擎两处各错位一次。
4. 外部特征可能一次加载整个区间；回调只读取截至当前信号时点可得的行。均线/动量先准备足够历史，20交易日收益需21个价格，日历天预热不等于交易日数。
5. 最小取数检查输出表头、类型、首尾日期、样本行与缺失数；空数据/权限不足时停止该数据路径，不能悄悄删条件或补虚构数据。

## 代码契约与明确的版本差异

| 项 | 规则 |
|---|---|
| 初始化/逐bar | 使用选中模板支持的`initialize(context)`、`handle_data(context, data)`及订单/成交回调；不是聚宽的全局下单函数 |
| 目标权重 | 文档有`context.order_target_percent`，实际签名与返回/异常政策以当前版本为准；权重是目标比例，不是新增比例 |
| 持仓 | 新式引擎可用`get_positions/get_position`；不能无核验移植旧模板`context.portfolio` |
| 数据 | 新式入口可能走`datasets`与`DataReader.current/history`；不要假定有`context.data`或行情history一定返回DataFrame |
| 时间 | 核对`context.current_dt/trading_day`等实际属性；不要抄旧模板的`data.current_dt` |
| 费用 | 先看当前签名。项目核验的本地`bigquant==6.0.3`为`set_commission(buy_ratio, sell_ratio, min_commission, tax_ratio=None)`，没有导出的`bigtrader.PerOrder`；不能据此推断所有云端版本相同 |
| 滑点 | 同一6.0.3核验为`set_slippage(slippage, percent=False)`；百分比要显式确认`percent=True`。旧类式API不能直接拼入 |
| 预热 | 同一版本`before_start_days`按日历天。既要核对足够历史，又要查首个应调仓日有没有真实信号 |
| 拒单 | 有些配置默认抛异常，单写`if rv < 0`不会接到返回；按当前`raise_on_error`政策处理。禁止用吞掉所有异常来“成功” |

6.0.3信息来自本项目2026-11-04维护笔记，安装与签名核验不等于数据权限或完整回测通过；它只是识别版本冲突的线索。遇到冲突请核对用户环境，不强行升级或降级。

## 交付与验证

完整代码包含数据查询/特征→回调→成本/撮合→启动调用→结果读取。只交一个`handle_data`不够。若用模块入口，数据模块输出与引擎输入对象也必须对上。

先卖后买不保证资金立即可用，按实际成交与现金决定买入。订单回调、成交、持仓与未成交余量都核对。不得通过延后一天、改成交价、取消止损等方式暗改卡来消除报错。

API key、数据授权、云端权益由用户在官方安全入口处理，不写入代码或聊天。bq CLI某些运行能力在查阅时标为暂未开放，不能依据示例声称已能自动运行云端回测。模拟能力以实际账号/策略入口为准。

官方：[BigTrader API](https://bigquant.com/wiki/doc/nxDOuIdhm2)、[快速教程/模块入口](https://bigquant.com/wiki/doc/5qj3KAOmx8)、[CLI](https://bigquant.com/wiki/doc/c00CYNWmYB)。来源记录见[sources.json](sources.json)。

## 2026-11-09 本地6.0.3核验补充

- 目标比例单的参考价格未必是用户指定的次日开盘价。要求按开盘目标仓位时，核对数量折算、信号冻结时点与撮合配置；不能把盘前按昨收折算的80%直接称为开盘80%。当日open只可用于该时点的执行与数量，不能把当日close放进前日信号。
- 真实类型的成交字段为`TradeData.filled_qty/filled_price`，不是`trade_qty/trade_price`；订单有`local_order_id/status_msg`等字段。核对当前类型注解或真实对象；用`hasattr`静默省略必需字段，会让日志看起来运行却缺成交证据。
- DAI交易日历鉴权发生在业务初始化/交易回调之前。本次实际报`all_trading_days ... no API key`，0交易日、无绩效行；空结果不能算0收益或策略通过。签名核对通过、引擎配置初始化返回0，不等于策略的`initialize`已触发。
- 不在正式引擎生命周期之外手动调用绑定C++的Context来“预检初始化”：本次这种诊断进程发生0xC0000005。用签名检查和有标签的回调桩诊断，正常真实回调仍需引擎启动及合法数据权限。
- 本次修订候选的`current/default`日线开盘撮合尚无真实数据成交验证；不得把候选配置写成所有6.x环境已验收的开盘模板。官网本日仍有旧类式费用示例，必须与当前安装包核对。

## 指定因子：2026-11-09官方数据字典核验

|用途|官方字段/关键语义|适用边界|
|---|---|---|
|历史沪深300池|`cn_stock_index_component`中`instrument='000300.SH'`是指数，`member_code`才是股票；`date`取信号日截面|不能把指数代码当股票，也不能用当前池回填历史|
|PE TTM|`cn_stock_valuation.pe_ttm`，单位倍；官方说明财务按公告日处理|泛称PE先确认TTM/静态/动态；不能仅凭相似名字替换|
|TTM ROE|`cn_stock_financial_profitability.roe_avg_ttm`为平均归母权益分母，`roe_period_ttm`为期末归母权益分母|两种不同定义先确认；实际返回尺度未授权取样，阈值前复核单位|
|公告时点|上表`date`为公告/更正日，`report_date`为报告期，`shift=0`为该公告时点最新一期|每个信号日仅用`date<=asof`最后已知快照；保留两个日期，查询需包含首日前已有财报|
|自定义20日动量|`cn_stock_bar1d.close`已后复权，21个交易日价格计算`C(D)/C(D-20)-1`|不要再乘adjust_factor；复权口径和缺失日处理需按用户选择，DataReader原始价格不能直接混成同一口径|

本次仅公开数据字典与DAI调用签名已核对，未执行授权SQL或真实因子回测。缺少官方等价因子时按[因子工作流](factors.md)从证据充分的原始字段计算；没有数据权限时保留条件并给授权导出/用户PIT数据契约，不暗删ROE。

官方数据字典：[估值](https://bigquant.com/data/datasources/cn_stock_valuation)、[指数成分](https://bigquant.com/data/datasources/cn_stock_index_component)、[盈利能力](https://bigquant.com/data/datasources/cn_stock_financial_profitability)、[股票日行情](https://bigquant.com/data/datasources/cn_stock_bar1d)。
