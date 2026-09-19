"""Pre-registered SHM experiment: where does the remaining ~2.7% MAPE come from?

    python scripts/shm_variants_experiment.py      (after scripts/shm_rainflow_cache.py)

shm-v1 is rainflow + Miner with (m, C) fitted in log space inside each fold; m lands
at 5.01-5.03, so the exponent is essentially known. Variants, each adding at most ONE
fitted parameter, all fitted inside the training folds only:

  v1          as shipped: D = sum n (range)^m / C
  m5          m fixed at 5 (C only)
  full_half   residual half cycles counted as full cycles
  cutoff      cycles with range below s0 ignored (s0 on a grid, fitted in-fold)
  goodman     range_eq = range / (1 - mean/Su), Su fitted in-fold (mean-stress correction)

Same 5 folds over files as shm-v1 (seed 20260918), repeated over 2 further seeds.
Metric max(0, 1 - MAPE). Adopt only if the mean improves by >= 0.005 on every seed.
Also reports the residual spread of v1 to judge whether the rest is label noise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[1]
SHM = ROOT / "repo" / "PS3" / "02_Datasets" / "SHM"
CACHE = ROOT / "artifacts_cache"
SEEDS = (20260918, 1, 2)


def load():
    z = np.load(CACHE / "shm_train_cycles.npz")
    names = sorted({k.split("::")[0] for k in z.files})
    return {n: (z[f"{n}::rng"], z[f"{n}::mean"], z[f"{n}::cnt"]) for n in names}


def log_S(cyc, names, m, variant, p):
    out = np.empty(len(names))
    for k, n in enumerate(names):
        rng, mean, cnt = cyc[n]
        cnt = np.where(cnt == 0.5, 1.0, cnt) if variant == "full_half" else cnt
        r = rng
        if variant == "goodman":
            r = rng / np.clip(1 - mean / p, 1e-3, None)
        good = r > (p if variant == "cutoff" else 0)
        out[k] = logsumexp(np.log(cnt[good]) + m * np.log(r[good])) if good.any() else -np.inf
    return out


def grids(cyc, names):
    """Label-free grid points (from the stress data only), so they can be shared by
    all folds; which grid point is used is still chosen inside each training fold."""
    all_r = np.concatenate([cyc[n][0] for n in names])
    all_mean = np.concatenate([cyc[n][1] for n in names])
    mx = np.abs(all_mean).max() + all_r.max()
    ms = np.arange(4.9, 5.16, 0.05)
    return {"v1": [(m, None) for m in ms], "m5": [(5.0, None)],
            "full_half": [(m, None) for m in ms],
            "cutoff": [(m, q) for q in np.quantile(all_r, [.1, .2, .4, .6]) for m in ms],
            "goodman": [(m, q) for q in mx * np.array([1.5, 3, 10, 100]) for m in ms]}


def precompute(cyc, names, grid):
    return {v: {g: log_S(cyc, names, g[0], v, g[1]) for g in gs} for v, gs in grid.items()}


def fit(table, tr, d):
    best = (np.inf, None)
    for g, ls_all in table.items():
        ls = ls_all[tr]
        if not np.isfinite(ls).all():
            continue
        logC = np.mean(ls - np.log(d[tr]))
        mape = np.mean(np.abs(np.exp(ls - logC) - d[tr]) / d[tr])
        if mape < best[0]:
            best = (mape, (g, logC))
    return best[1]


def main() -> int:
    labels = pd.read_csv(SHM / "Train_Labels.csv")
    cyc = load()
    names = list(labels.filename)
    d = labels.damage.to_numpy(float)
    variants = ["v1", "m5", "full_half", "cutoff", "goodman"]
    L = precompute(cyc, names, grids(cyc, names))
    print("precomputed", flush=True)
    res = {v: [] for v in variants}
    resid = []
    for seed in SEEDS:
        folds = np.array_split(np.random.default_rng(seed).permutation(len(names)), 5)
        for v in variants:
            pred = np.empty(len(names))
            for va in folds:
                tr = np.setdiff1d(np.arange(len(names)), va)
                g, logC = fit(L[v], tr, d)
                pred[va] = np.exp(L[v][g][va] - logC)
            score = max(0.0, 1 - float(np.mean(np.abs(pred - d) / d)))
            res[v].append(score)
            if v == "v1" and seed == SEEDS[0]:
                resid = np.log(pred / d)
            print(f"seed {seed:9d} {v:10s} {score:.5f}", flush=True)
    base = res["v1"]
    table = [{"variant": v, "per_seed": [round(s, 5) for s in res[v]], "mean": round(float(np.mean(res[v])), 5)} for v in variants]
    best = max(table[1:], key=lambda r: r["mean"])
    adopt = all(b >= a + 0.005 for a, b in zip(base, res[best["variant"]]))
    corr = float(np.corrcoef(resid, np.log(d))[0, 1])
    out = {"protocol": __doc__.strip(), "table": table,
           "v1_log_residual": {"sd": round(float(np.std(resid)), 4), "corr_with_log_damage": round(corr, 3),
                               "max_abs_pct": round(float(np.max(np.abs(np.expm1(resid)))) * 100, 2)},
           "decision": {"adopt": bool(adopt), "variant": best["variant"] if adopt else "v1",
                        "reason": f"best alternative {best['variant']} {best['mean']:.5f} vs v1 {np.mean(base):.5f}"}}
    (ROOT / "subsystems" / "shm" / "artifacts" / "experiment_variants.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("v1_log_residual", "decision")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
