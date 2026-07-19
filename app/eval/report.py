"""Рендер eval-отчёта в Markdown (для чтения) и JSON (машиночитаемый)."""

from __future__ import annotations

import json

from app.eval.harness import AgentEval, DetectorEval


def render_markdown(detector: DetectorEval, agent: AgentEval | None = None) -> str:
    d = detector
    lines = [
        f"# Eval — {d.corpus}",
        "",
        "## Детекторы (recall по покрытым классам)",
        f"- покрыто классов: {d.covered} / {len(d.outcomes)}",
        f"- recall: {d.recall:.0%}  ({d.confusion.tp} hit / {d.confusion.fn} miss)",
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
            lines.append(
                f"- LLM-judge grounding: {agent.grounding:.0%}  (судья: {agent.judged_by})"
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
            "judged_by": agent.judged_by,
            "cost_usd": agent.cost_usd,
            "avg_latency_ms": agent.avg_latency_ms,
        }
    return json.dumps(payload, indent=2, ensure_ascii=False)
