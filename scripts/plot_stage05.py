#!/usr/bin/env python3
"""Render the locked holdout policy comparison."""

import argparse
from pathlib import Path

from plot_stage04 import load, plot_top30


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--output", type=Path, default=root / "results/05_holdout_evaluation")
    out = parser.parse_args().output
    figures = out / "figures"
    figures.mkdir(exist_ok=True)
    plot_top30(load(out / "tables/holdout_at30.csv"), figures / "holdout_uplift.png", "最终保留集")


if __name__ == "__main__":
    main()
