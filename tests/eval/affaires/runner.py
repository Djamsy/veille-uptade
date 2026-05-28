"""Runner d'évaluation pour la fusion en affaires.

Charge `fixtures.jsonl`, applique une baseline, calcule precision/recall/F1.
Utilisable comme :

    python -m tests.eval.affaires.runner --baseline jaccard_tokens
    python -m tests.eval.affaires.runner --baseline jaccard_plus_entities --threshold 0.35
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures.jsonl"
RESULTS_DIR = HERE / "results"


@dataclass
class Pair:
    id: str
    should_merge: bool
    rationale: str
    article_a: dict[str, Any]
    article_b: dict[str, Any]


def load_fixtures(path: Path = FIXTURES) -> list[Pair]:
    pairs: list[Pair] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        row = json.loads(line)
        pairs.append(
            Pair(
                id=row["id"],
                should_merge=bool(row["should_merge"]),
                rationale=row.get("rationale", ""),
                article_a=row["article_a"],
                article_b=row["article_b"],
            )
        )
    return pairs


def load_baseline(name: str):
    return importlib.import_module(f"tests.eval.affaires.baselines.{name}")


@dataclass
class Metrics:
    tp: int = 0  # true positive : should_merge & predicted_merge
    fp: int = 0  # false positive : should_split & predicted_merge
    fn: int = 0  # false negative : should_merge & predicted_split
    tn: int = 0  # true negative : should_split & predicted_split

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class RunResult:
    baseline: str
    threshold: float
    n: int
    n_positive: int
    n_negative: int
    metrics: Metrics
    errors: list[dict[str, Any]]


def evaluate(baseline_name: str, threshold: float | None = None) -> RunResult:
    baseline = load_baseline(baseline_name)
    if threshold is None:
        threshold = float(getattr(baseline, "DEFAULT_THRESHOLD", 0.5))

    pairs = load_fixtures()
    m = Metrics()
    errors: list[dict[str, Any]] = []

    for pair in pairs:
        s = float(baseline.score(pair.article_a, pair.article_b))
        predicted_merge = s >= threshold

        if pair.should_merge and predicted_merge:
            m.tp += 1
        elif pair.should_merge and not predicted_merge:
            m.fn += 1
            errors.append(
                {
                    "id": pair.id,
                    "expected": "merge",
                    "predicted": "split",
                    "score": s,
                    "rationale": pair.rationale,
                }
            )
        elif not pair.should_merge and predicted_merge:
            m.fp += 1
            errors.append(
                {
                    "id": pair.id,
                    "expected": "split",
                    "predicted": "merge",
                    "score": s,
                    "rationale": pair.rationale,
                }
            )
        else:
            m.tn += 1

    return RunResult(
        baseline=baseline_name,
        threshold=threshold,
        n=len(pairs),
        n_positive=sum(1 for p in pairs if p.should_merge),
        n_negative=sum(1 for p in pairs if not p.should_merge),
        metrics=m,
        errors=errors,
    )


def format_report(r: RunResult) -> str:
    lines = [
        f"=== Eval fusion affaires — baseline={r.baseline} ===",
        f"Dataset : {r.n} paires ({r.n_positive} positives, {r.n_negative} négatives)",
        f"Seuil de décision : {r.threshold:.2f}",
        "",
        "Confusion matrix",
        "                  predicted_merge   predicted_split",
        f"  should_merge          {r.metrics.tp:<3}              {r.metrics.fn:<3}",
        f"  should_split          {r.metrics.fp:<3}              {r.metrics.tn:<3}",
        "",
        f"Precision : {r.metrics.precision:.2f}",
        f"Recall    : {r.metrics.recall:.2f}",
        f"F1        : {r.metrics.f1:.2f}",
    ]
    if r.errors:
        lines.append("")
        lines.append("Erreurs :")
        for err in r.errors:
            lines.append(
                f"  {err['id']:<32}  attendu={err['expected']:<5}  prédit={err['predicted']:<5}  score={err['score']:.2f}"
            )
    return "\n".join(lines)


def save_snapshot(r: RunResult) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{r.baseline}.json"
    out.write_text(
        json.dumps(
            {
                "baseline": r.baseline,
                "threshold": r.threshold,
                "n": r.n,
                "n_positive": r.n_positive,
                "n_negative": r.n_negative,
                "precision": r.metrics.precision,
                "recall": r.metrics.recall,
                "f1": r.metrics.f1,
                "confusion": {
                    "tp": r.metrics.tp,
                    "fp": r.metrics.fp,
                    "fn": r.metrics.fn,
                    "tn": r.metrics.tn,
                },
                "errors": r.errors,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="jaccard_tokens")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--save", action="store_true", help="Sauvegarder le snapshot JSON")
    args = parser.parse_args()

    r = evaluate(args.baseline, args.threshold)
    print(format_report(r))
    if args.save:
        path = save_snapshot(r)
        print(f"\nSnapshot sauvegardé : {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
