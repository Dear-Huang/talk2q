"""Offline plan builder from authorized CSV extracts. Deliberately not a live trader.

Caller must state PE/ROE/price definitions; this file never logs in or submits orders.
"""
import argparse
import json
from pathlib import Path
import pandas as pd
from factor_pipeline import select, FactorDefinition


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--execution-date", required=True)
    parser.add_argument("--pe-basis", required=True)
    parser.add_argument("--roe-basis", required=True)
    parser.add_argument("--price-basis", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = {name: pd.read_csv(args.input/f"{name}.csv") for name in ["calendar","members","valuation","financial","bars"]}
    result = select(args.execution_date, **data, definition=FactorDefinition(args.pe_basis,args.roe_basis,args.price_basis))
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    print("Plan generated; no order or fill has occurred:", args.output)


if __name__ == "__main__": main()
