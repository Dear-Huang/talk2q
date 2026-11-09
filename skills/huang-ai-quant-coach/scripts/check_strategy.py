"""Offline syntax and limited cross-platform checks. Never executes strategy code."""
import argparse, ast, json, sys, tokenize

def inspect_code(code, platform, engine='unknown'):
    findings=[]
    def add(level, node, message):
        findings.append({'level':level,'line':getattr(node,'lineno',0),'message':message})
    try:
        tree=ast.parse(code)
    except SyntaxError as e:
        return [{'level':'error','line':e.lineno,'message':f'Python语法错误：{e.msg}'}]
    nodes=list(ast.walk(tree)); functions={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    families={'joinquant':{'jqdata','jqfactor','jqdatasdk'},'bigquant':{'bigquant','bigmodule','dai'},'ricequant':{'rqalpha','rqdatac'},'myquant':{'gm'}}
    for n in nodes:
        imports=[]
        if isinstance(n,ast.Import): imports=[a.name.split('.')[0] for a in n.names]
        if isinstance(n,ast.ImportFrom): imports=[(n.module or '').split('.')[0]]
        for root in imports:
            for family,names in families.items():
                if root in names and family!=platform:
                    add('warning',n,f'发现{family}相关导入{root}；请核对是否有意跨平台取数，不能直接复用其回测/订单API。')
            if platform=='joinquant' and root=='jqdatasdk':
                add('warning',n,'jqdatasdk是本地数据SDK；当前选择聚宽云端，请核对入口。')
    if platform=='joinquant':
        if 'initialize' not in functions: add('warning',tree,'未发现顶层initialize(context)，核对是否提交了完整云端策略。')
        jq_star=any(isinstance(n,ast.ImportFrom) and n.module=='jqdata' and any(a.name=='*' for a in n.names) for n in tree.body)
        explicit_names=set(functions)
        for n in tree.body:
            if isinstance(n,ast.Assign):
                explicit_names.update(t.id for t in n.targets if isinstance(t,ast.Name))
            if isinstance(n,ast.ImportFrom) and n.module=='builtins':
                explicit_names.update(a.asname or a.name for a in n.names)
        if jq_star:
            for n in nodes:
                if not isinstance(n,ast.Call) or not isinstance(n.func,ast.Name) or n.func.id in explicit_names:continue
                if n.func.id in {'any','all'} and n.args and isinstance(n.args[0],ast.GeneratorExp):
                    add('error',n,'jqdata通配导入可能把any/all覆盖为NumPy函数；本次云端any(generator)始终判真导致0交易。Python迭代器逻辑请显式用builtins.any/all，数组聚合用np.any/all。')
                elif n.func.id in {'sum','min','max'}:
                    add('warning',n,'jqdata通配导入后未限定sum/min/max的来源；Python标量/迭代器运算请用builtins，NumPy运算请用np，避免参数含义或返回类型改变。')
        for n in nodes:
            if not isinstance(n,ast.Call) or not isinstance(n.func,ast.Name) or n.func.id not in {'run_daily','run_weekly','run_monthly'} or not n.args: continue
            cb=functions.get(n.args[0].id) if isinstance(n.args[0],ast.Name) else None
            if cb:
                required=len(cb.args.posonlyargs)+len(cb.args.args)-len(cb.args.defaults)
                if required!=1: add('error',cb,f'{n.func.id}注册的{cb.name}有{required}个必需位置参数；聚宽定时回调应仅需context。')
        for n in nodes:
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='get_fundamentals':
                keys={k.arg for k in n.keywords if not isinstance(k.value,ast.Constant) or k.value.value is not None}
                if {'date','statDate'}<=keys: add('error',n,'get_fundamentals同时传非空date与statDate；二者应择一，并核对公告时点。')
    if platform=='bigquant':
        has_module=any(isinstance(n,ast.Attribute) and n.attr=='bigtrader' and isinstance(n.value,ast.Name) and n.value.id=='M' for n in nodes)
        has_run=any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='run' and isinstance(n.func.value,ast.Name) and n.func.value.id=='bigtrader' for n in nodes)
        if has_module and has_run: add('warning',tree,'同时发现M.bigtrader与bigtrader.run，核对是否混拼两套引擎入口。')
        if engine=='bigtrader6':
            for n in nodes:
                if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='context' and n.attr in {'portfolio','data'}:
                    add('warning',n,f'选择BigTrader 6.x契约但使用context.{n.attr}；核对实际版本，不能直接套旧模板。')
                if isinstance(n,ast.Attribute) and n.attr=='PerOrder' and isinstance(n.value,ast.Name) and n.value.id=='bigtrader':
                    add('warning',n,'bigtrader.PerOrder在已核验的本地6.0.3未导出；按当前set_commission签名核对。')
        if engine=='bigquant-cloud011':
            for n in nodes:
                if (isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                        and isinstance(n.func.value,ast.Name) and n.func.value.id=='context'
                        and n.func.attr=='get_commission' and not n.args and not n.keywords):
                    add('error',n,'已实测BigQuant云端0.1.11的context.get_commission(code)需要证券代码；无参调用真实抛TypeError，不能将通用内存提示当原因。')
    if platform=='ricequant' and 'initialize' in functions and 'init' not in functions:
        add('warning',functions['initialize'],'发现initialize但无init；核对是否误用其他平台初始化回调。')
    if platform=='ricequant' and engine=='rqalpha642':
        # Observed in an actual 6.4.2 sell branch: old positions returns a proxy,
        # whereas get_position returns the newer Position with a closable field.
        # Restrict this diagnostic to provable local assignments; unknown objects
        # are left for runtime validation rather than flagged by attribute alone.
        def old_positions(expr):
            return (isinstance(expr,ast.Attribute) and expr.attr=='positions'
                    and isinstance(expr.value,ast.Attribute) and expr.value.attr=='portfolio')
        for fn in functions.values():
            proxy_names=set()
            ordered=sorted(ast.walk(fn),key=lambda n:getattr(n,'lineno',0))
            for n in ordered:
                if isinstance(n,ast.Assign):
                    value=n.value
                    proxy=(isinstance(value,ast.Subscript) and old_positions(value.value)) or (
                        isinstance(value,ast.Call) and isinstance(value.func,ast.Attribute)
                        and value.func.attr=='get' and old_positions(value.func.value))
                    for target in n.targets:
                        if isinstance(target,ast.Name):
                            if proxy:proxy_names.add(target.id)
                            else:proxy_names.discard(target.id)
                if isinstance(n,ast.Attribute) and n.attr=='closable':
                    direct=isinstance(n.value,ast.Subscript) and old_positions(n.value.value)
                    local=isinstance(n.value,ast.Name) and n.value.id in proxy_names
                    if direct or local:
                        add('error',n,'RQAlpha 6.4.2的portfolio.positions返回StockPositionProxy，无closable；该代理用sellable，或统一改用get_position返回Position再读closable，并实测卖出分支。')
    add('info',tree,'此检查未执行策略。未覆盖动态别名、完整API签名、数据权限、时点、费用、撮合或平台运行正确性。')
    return findings

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform',required=True,choices=['joinquant','bigquant','ricequant','myquant'])
    p.add_argument('--engine',default='unknown',choices=['unknown','bigtrader6','bigquant-cloud011','module','rqalpha642'],help='仅在已确认环境时指定；bigtrader6对应本地6.0.3，bigquant-cloud011对应AIStudio0.1.11，rqalpha642对应开源6.4.2有限契约')
    p.add_argument('--json',action='store_true');p.add_argument('file')
    a=p.parse_args()
    try:
        with tokenize.open(a.file) as f: code=f.read()
    except (OSError,UnicodeError,SyntaxError) as e:
        p.error(f'无法读取策略：{e}')
    findings=inspect_code(code,a.platform,a.engine)
    if a.json: print(json.dumps(findings,ensure_ascii=False,indent=2))
    else:
        for x in findings: print(f"[{x['level']}] line {x['line']}: {x['message']}")
    return 1 if any(x['level']=='error' for x in findings) else 0
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.exit(main())
