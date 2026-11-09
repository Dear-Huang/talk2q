"""Evidence-backed alias resolver: ambiguity is an error, never a fallback."""
from factor_contract import ContractError
FIELDS={
 'pe_ratio_ttm':{'label':'市盈率TTM','unit':'multiple','formula':'market_cap_3 / net_profit_parent_company_ttm_0'},
 'pe_ratio_lyr':{'label':'市盈率最近年报','unit':'multiple','formula':'market_cap_3 / net_profit_parent_company_lyr_0'},
 'return_on_equity_ttm':{'label':'净资产收益率TTM','unit':'fraction_by_documented_formula','formula':'net_profit_parent_company_ttm_0 * 2 / (equity_parent_company_ttm_0 + equity_parent_company_ttm_1)'},
 'return_on_equity_diluted_ttm':{'label':'摊薄净资产收益率TTM','unit':'fraction_by_documented_formula','formula':'net_profit_parent_company_ttm_0 / equity_parent_company_ttm_0'},
}
AMBIGUOUS={'PE':['pe_ratio_ttm','pe_ratio_lyr'],'市盈率':['pe_ratio_ttm','pe_ratio_lyr'],'ROE TTM':['return_on_equity_ttm','return_on_equity_diluted_ttm'],'ROE':['return_on_equity_ttm','return_on_equity_diluted_ttm'],'净资产收益率':['return_on_equity_ttm','return_on_equity_diluted_ttm'],'20交易日动量':['custom_20_return_ratio_requires_confirmation']}

def resolve_factor(name,live_catalog=None):
    if name in AMBIGUOUS:
        raise ContractError('Ambiguous factor '+name+'; confirm exact definition: '+', '.join(AMBIGUOUS[name]))
    if name not in FIELDS:raise ContractError('Unsupported exact factor; research or confirmed custom definition required: '+name)
    if live_catalog is not None and name not in live_catalog:
        raise ContractError('Exact factor unavailable in current catalog/permission; preserve condition and supply authorized data: '+name)
    return dict(id=name,**FIELDS[name])
