"""张新民框架：资产负债表科目分类映射（东财 F10 字段名）。"""

from __future__ import annotations

# 经营性资产
OPERATING_ASSET_FIELDS = [
    "MONETARYFUNDS",           # 货币资金
    "ACCOUNTS_RECE",           # 应收账款
    "NOTE_RECE",               # 应收票据
    "PREPAYMENT",              # 预付款项
    "INVENTORY",               # 存货
    "CONTRACT_ASSET",          # 合同资产
    "OTHER_RECE",              # 其他应收款
    "FIXED_ASSET",             # 固定资产
    "CIP",                     # 在建工程
    "INTANGIBLE_ASSET",        # 无形资产
    "DEVELOP_EXPENSE",         # 开发支出
    "LONG_PREPAID_EXPENSE",    # 长期待摊费用
    "DEFERRED_EXPENSE",        # 递延所得税资产（部分口径归入经营相关）
]

# 投资性资产
INVESTING_ASSET_FIELDS = [
    "LONG_EQUITY_INVEST",      # 长期股权投资
    "OTHER_EQUITY_INVEST",     # 其他权益工具投资
    "HOLD_MATURITY_INVEST",    # 持有至到期投资
    "INVEST_REALESTATE",       # 投资性房地产
    "GOODWILL",                # 商誉
    "AVAILABLE_SALE_FINASSET", # 可供出售金融资产
    "TRADE_FINASSET_NOTFVTPL", # 交易性金融资产等
]

# 金融性负债（有息负债）
FINANCIAL_LIABILITY_FIELDS = [
    "SHORT_LOAN",              # 短期借款
    "BOND_PAYABLE",            # 应付债券
    "LONG_LOAN",               # 长期借款
    "SHORT_BOND_PAYABLE",      # 应付短期债券
    "LEASE_LIABILITY",         # 租赁负债
    "NONCURRENT_LIAB_1YEAR",   # 一年内到期的非流动负债
]

# 经营性负债
OPERATING_LIABILITY_FIELDS = [
    "ACCOUNTS_PAYABLE",        # 应付账款
    "NOTE_PAYABLE",            # 应付票据
    "ADVANCE_RECEIVABLES",     # 预收款项 / 合同负债
    "CONTRACT_LIAB",           # 合同负债
    "STAFF_SALARY_PAYABLE",    # 应付职工薪酬
    "TAX_PAYABLE",             # 应交税费
    "TOTAL_OTHER_PAYABLE",     # 其他应付款
]

# 利润表：核心利润费用项
CORE_PROFIT_EXPENSE_FIELDS = [
    "SALE_EXPENSE",
    "MANAGE_EXPENSE",
    "RESEARCH_EXPENSE",
    "FINANCE_EXPENSE",
]

REVENUE_FIELDS = ["TOTALOPERATEREVE", "TOTAL_OPERATE_INCOME", "OPERATE_INCOME_PK"]
COGS_FIELDS = ["OPERATE_COST", "OPERATE_EXPENSE"]
TAX_FIELDS = ["OPERATE_TAX_ADD", "OPERATE_TAX"]
NET_PROFIT_FIELDS = ["PARENTNETPROFIT", "PARENT_NETPROFIT"]
DEDUCT_PROFIT_FIELDS = ["KCFJCXSYJLR", "DEDUCT_PARENT_NETPROFIT"]
OCF_FIELDS = ["NETCASH_OPERATE_PK", "NETCASH_OPERATE"]
CAPEX_FIELDS = ["CONSTRUCT_LONG_ASSET"]
SALES_CASH_FIELDS = ["SALES_SERVICES"]
ICF_FIELDS = ["NETCASH_INVEST_PK", "NETCASH_INVEST"]
FCF_FIN_FIELDS = ["NETCASH_FINANCE_PK", "NETCASH_FINANCE"]
TOTAL_ASSETS_FIELDS = ["TOTAL_ASSETS_PK", "TOTAL_ASSETS"]
TOTAL_EQUITY_FIELDS = ["TOTAL_EQUITY_PK", "TOTAL_EQUITY"]
TOTAL_LIAB_FIELDS = ["LIABILITY", "TOTAL_LIABILITIES"]
