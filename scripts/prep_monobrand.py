#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Preprocessing per export Semrush/Ahrefs mono-brand (una riga = keyword
posizionata sul dominio di un unico brand), che non contengono le colonne
Brand e Brand/Not Brand richieste da scripts/cluster.py --mode prepare.

Aggiunge:
- Brand: nome brand passato via --brand, ripetuto su tutte le righe
- Brand/Not Brand: "Brand" se la keyword contiene un token del nome brand
  (word-boundary, case-insensitive), altrimenti "Not Brand"

Uso:
    python scripts/prep_monobrand.py --input input/foo.csv --brand "Nome Brand" --output input/prepared/foo.csv
"""

import argparse
import re
from pathlib import Path

import pandas as pd


def is_branded(keyword: str, brand: str) -> str:
    kw = str(keyword).lower()
    tokens = [t for t in re.split(r"\s+", brand.lower()) if len(t) > 2]
    for tok in tokens:
        if re.search(r"(?<![a-zà-ÿ0-9])" + re.escape(tok) + r"(?![a-zà-ÿ0-9])", kw):
            return "Brand"
    return "Not Brand"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--brand", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    df.insert(0, "Brand", args.brand)
    df["Brand/Not Brand"] = df["Keyword"].apply(lambda kw: is_branded(kw, args.brand))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    n_brand = (df["Brand/Not Brand"] == "Brand").sum()
    print(f"[OK] {len(df)} righe -> {out_path}")
    print(f"   Brand: {n_brand} ({n_brand / len(df) * 100:.1f}%)  |  Not Brand: {len(df) - n_brand}")


if __name__ == "__main__":
    main()
