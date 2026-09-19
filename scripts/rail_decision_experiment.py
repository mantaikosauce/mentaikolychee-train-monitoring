"""Pre-registered Rail experiment: does the DECISION rule, not the model, cost macro F1?

    python scripts/rail_decision_experiment.py

Out-of-fold errors of rail-v2 are mostly Normal files called Side II (9 of 17), so
the question is where the Normal / corrugated boundary sits, not which side.

Candidates, all on the v2 feature set ("base") with the v2 forest (300 trees,
max_features 0.7, min_samples_leaf 3, balanced) and side-swap augmentation inside
training folds only:

  flat      rail-v2 as shipped: argmax of the 3-class probabilities.
  thresh    same forest; predict corrugated only when P(Normal) < t, then the likelier
            side. t is chosen INSIDE each training fold by 3-fold grouped CV over a
            fixed grid, so the held-out fold never influences it.
  hier      two stages: forest A = Normal vs corrugated, forest B = Side I vs Side II
            trained on corrugated files only (side-swap doubles them). Decision at 0.5.

Protocol: 5 stratified grouped folds x 3 seeds (groups = identical-feature files),
macro F1 over Normal / Side I / Side II pooled per repeat.
Decision: adopt a candidate only if its mean beats flat by >= 0.01 AND it is not
worse than flat on any of the 3 repeats. Otherwise rail-v2 stays. Written to
subsystems/rail/artifacts/experiment_decision.json either way.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.rail_wavelength_experiment import augment, features_all  # noqa: E402

LABELS = ["Normal", "Side I", "Side II"]
SEED = 42
GRID = np.round(np.arange(0.30, 0.81, 0.05), 2)


def forest():
    return RandomForestClassifier(n_estimators=300, max_features=0.7, min_samples_leaf=3,
                                  class_weight="balanced", random_state=SEED, n_jobs=-1)


def folds_for(x, y, groups, seed, k):
    f = np.zeros(len(y), dtype=int)
    for i, (_, va) in enumerate(StratifiedGroupKFold(k, shuffle=True, random_state=seed).split(x, y, groups)):
        f[va] = i
    return f


def proba_flat(x, y, tr, va):
    ax, ay = augment(x.iloc[tr], y.iloc[tr])
    m = clone(forest()).fit(ax, ay)
    return pd.DataFrame(m.predict_proba(x.iloc[va]), columns=m.classes_)[LABELS].to_numpy()


def decide(p, t):
    side = np.where(p[:, 1] >= p[:, 2], "Side I", "Side II")
    return np.where(p[:, 0] >= t, "Normal", side)


def pred_flat(x, y, tr, va, groups):
    p = proba_flat(x, y, tr, va)
    return np.array(LABELS, dtype=object)[p.argmax(1)]


def pred_thresh(x, y, tr, va, groups):
    # choose t on the training part only, by inner grouped CV
    xi, yi, gi = x.iloc[tr].reset_index(drop=True), y.iloc[tr].reset_index(drop=True), groups[tr]
    inner = folds_for(xi, yi, gi, SEED, 3)
    p_in = np.zeros((len(yi), 3))
    for f in range(3):
        iva, itr = np.where(inner == f)[0], np.where(inner != f)[0]
        p_in[iva] = proba_flat(xi, yi, itr, iva)
    scores = [f1_score(yi, decide(p_in, t), labels=LABELS, average="macro") for t in GRID]
    t = float(GRID[int(np.argmax(scores))])
    pred_thresh.chosen.append(t)
    return decide(proba_flat(x, y, tr, va), t)


pred_thresh.chosen = []


def pred_hier(x, y, tr, va, groups):
    ax, ay = augment(x.iloc[tr], y.iloc[tr])
    a = clone(forest()).fit(ax, (ay != "Normal").astype(int))
    cor = (ay != "Normal").to_numpy()
    b = clone(forest()).fit(ax[cor], ay[cor])
    is_cor = a.predict_proba(x.iloc[va])[:, 1] >= 0.5
    side = b.predict(x.iloc[va])
    return np.where(is_cor, side, "Normal")


def main() -> int:
    t0 = time.time()
    x_all, y, _ = features_all()
    wl = [c for c in x_all.columns if "_wl_" in c]
    x = x_all[[c for c in x_all.columns if c not in wl]]
    groups = pd.util.hash_pandas_object(x, index=False).to_numpy()
    cands = {"flat": pred_flat, "thresh": pred_thresh, "hier": pred_hier}
    res = {k: [] for k in cands}
    cms = {k: np.zeros((3, 3), dtype=int) for k in cands}
    for seed in (1, 2, 3):
        folds = folds_for(x, y, groups, seed, 5)
        for name, fn in cands.items():
            pred = np.empty(len(y), dtype=object)
            for f in range(5):
                va, tr = np.where(folds == f)[0], np.where(folds != f)[0]
                pred[va] = fn(x, y, tr, va, groups)
            res[name].append(float(f1_score(y, pred, labels=LABELS, average="macro")))
            cms[name] += confusion_matrix(y, pred, labels=LABELS)
            print(f"seed {seed} {name:7s} {res[name][-1]:.4f}   {time.time() - t0:.0f}s", flush=True)

    flat = res["flat"]
    table = []
    for name, s in res.items():
        table.append({"candidate": name, "repeats": [round(v, 4) for v in s], "mean": round(float(np.mean(s)), 4),
                      "std": round(float(np.std(s)), 4),
                      "confusion_summed_over_repeats": {"rows_truth_cols_pred": LABELS, "matrix": cms[name].tolist()}})
    best = max((r for r in table if r["candidate"] != "flat"), key=lambda r: r["mean"])
    adopt = best["mean"] >= np.mean(flat) + 0.01 and all(b >= f for b, f in zip(res[best["candidate"]], flat))
    out = {"protocol": __doc__.strip(), "table": table,
           "thresholds_chosen_inside_folds": pred_thresh.chosen,
           "decision": {"adopt": bool(adopt), "candidate": best["candidate"] if adopt else "flat",
                        "reason": f"best alternative {best['candidate']} {best['mean']:.4f} vs flat {np.mean(flat):.4f}"},
           "seconds": round(time.time() - t0)}
    (ROOT / "subsystems" / "rail" / "artifacts" / "experiment_decision.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for r in table:
        print(r["candidate"], r["mean"], "±", r["std"], r["confusion_summed_over_repeats"]["matrix"])
    print("thresholds:", pred_thresh.chosen)
    print("decision:", out["decision"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
