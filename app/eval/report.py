"""Рендер eval-отчёта в Markdown (для чтения) и JSON (машиночитаемый)."""

from __future__ import annotations

import json

from app.eval.harness import AgentEval, DetectorEval
from app.eval.metrics import wilson_interval


def render_markdown(detector: DetectorEval, agent: AgentEval | None = None) -> str:
    d = detector
    r_lo, r_hi = wilson_interval(d.confusion.tp, d.covered)
    lines = [
        f"# Eval — {d.corpus}",
        "",
        "## Детекторы (recall по покрытым классам)",
        f"- покрыто классов: {d.covered} / {len(d.outcomes)}",
        f"- recall: {d.recall:.0%} [{r_lo:.0%}, {r_hi:.0%}]  "
        f"({d.confusion.tp} hit / {d.confusion.fn} miss)",
    ]
    misses = [o for o in d.outcomes if o.covered and not o.hit]
    if misses:
        lines += ["", "### Промахи (детектор ожидался, но не сработал)"]
        lines += [
            f"- {o.name} — ожидалось {sorted(o.expected)}, сработало {sorted(o.fired) or '∅'}"
            for o in misses
        ]
    if agent is not None:
        lines += [
            "",
            "## Агент (подвыборка)",
            f"- прогон: {agent.sample_size} контрактов, {agent.findings} находок",
            f"- покрытие цитатами: {agent.coverage:.0%}",
            f"- структурная faithfulness: {agent.faithfulness:.0%}",
        ]
        if agent.grounding is not None:
            g_lo, g_hi = wilson_interval(agent.grounding_supported, agent.grounding_total)
            lines.append(
                f"- LLM-judge grounding: {agent.grounding:.0%} [{g_lo:.0%}, {g_hi:.0%}]  "
                f"(судья: {agent.judged_by}, стоимость судьи ${agent.judge_cost_usd:.4f})"
            )
        lines.append(
            f"- стоимость: ${agent.cost_usd:.4f}, "
            f"средняя латентность: {agent.avg_latency_ms:.0f} мс"
        )
    return "\n".join(lines) + "\n"


def render_json(detector: DetectorEval, agent: AgentEval | None = None) -> str:
    payload: dict[str, object] = {
        "corpus": detector.corpus,
        "detector": {
            "covered": detector.covered,
            "total": len(detector.outcomes),
            "recall": detector.recall,
            "recall_ci": list(wilson_interval(detector.confusion.tp, detector.covered)),
            "tp": detector.confusion.tp,
            "fn": detector.confusion.fn,
            "cases": [
                {
                    "name": o.name,
                    "class": o.vuln_class,
                    "expected": sorted(o.expected),
                    "fired": sorted(o.fired),
                    "hit": o.hit,
                }
                for o in detector.outcomes
            ],
        },
    }
    if agent is not None:
        payload["agent"] = {
            "sample_size": agent.sample_size,
            "findings": agent.findings,
            "coverage": agent.coverage,
            "faithfulness": agent.faithfulness,
            "grounding": agent.grounding,
            "grounding_ci": (
                list(wilson_interval(agent.grounding_supported, agent.grounding_total))
                if agent.grounding is not None
                else None
            ),
            "judged_by": agent.judged_by,
            "cost_usd": agent.cost_usd,
            "judge_cost_usd": agent.judge_cost_usd,
            "avg_latency_ms": agent.avg_latency_ms,
        }
    return json.dumps(payload, indent=2, ensure_ascii=False)
