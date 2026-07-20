"""Рендер eval-отчёта в Markdown (для чтения) и JSON (машиночитаемый)."""

from __future__ import annotations

import json

from app.eval.harness import AgentEval, CleanEval, DetectorEval
from app.eval.metrics import wilson_interval


def render_markdown(
    detector: DetectorEval, agent: AgentEval | None = None, clean: CleanEval | None = None
) -> str:
    d = detector
    tp = d.confusion.tp
    known = d.covered + d.blind_spots
    cov_lo, cov_hi = wilson_interval(tp, d.covered)
    kn_lo, kn_hi = wilson_interval(tp, known)
    cor_lo, cor_hi = wilson_interval(tp, len(d.outcomes))
    lines = [
        f"# Eval — {d.corpus}",
        "",
        "## Детекторы (recall — три честных знаменателя)",
        f"- покрыто классов: {d.covered} / {len(d.outcomes)} "
        f"(+{d.blind_spots} blind-spot: класс есть, детектора нет)",
        f"- recall covered: {d.recall:.0%} [{cov_lo:.0%}, {cov_hi:.0%}]  "
        f"({tp}/{d.covered}) — по классам, что движок умеет ловить",
        f"- recall +blind:  {d.known_recall:.0%} [{kn_lo:.0%}, {kn_hi:.0%}]  "
        f"({tp}/{known}) — включая непокрытые классы (для пользователя это тоже промах)",
        f"- recall корпус:  {d.corpus_recall:.0%} [{cor_lo:.0%}, {cor_hi:.0%}]  "
        f"({tp}/{len(d.outcomes)}) — по всем репро корпуса",
    ]
    misses = [o for o in d.outcomes if o.covered and not o.hit]
    if misses:
        lines += ["", "### Промахи (детектор ожидался, но не сработал)"]
        lines += [
            f"- {o.name} — ожидалось {sorted(o.expected)}, сработало {sorted(o.fired) or '∅'}"
            for o in misses
        ]
    if clean is not None:
        frac = clean.flagged_fraction
        lines += [
            "",
            "## Precision (false-positive rate на заведомо чистых контрактах)",
            f"- чистых контрактов: {clean.total}",
            f"- с ложным срабатыванием: {clean.flagged}/{clean.total} ({frac:.0%})",
            f"- среднее ложных флагов: {clean.avg_fp:.2f} на контракт",
        ]
    if agent is not None:
        lines += [
            "",
            "## Агент (подвыборка)",
            f"- прогон: {agent.sample_size} контрактов, {agent.findings} находок",
            f"- покрытие цитатами: {agent.coverage:.0%}",
            f"- провенанс цитат: {agent.faithfulness:.0%} — инвариант by design (не метрика)",
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


def render_json(
    detector: DetectorEval, agent: AgentEval | None = None, clean: CleanEval | None = None
) -> str:
    payload: dict[str, object] = {
        "corpus": detector.corpus,
        "detector": {
            "covered": detector.covered,
            "blind_spots": detector.blind_spots,
            "total": len(detector.outcomes),
            "recall": detector.recall,
            "recall_ci": list(wilson_interval(detector.confusion.tp, detector.covered)),
            "recall_known": detector.known_recall,
            "recall_known_ci": list(
                wilson_interval(detector.confusion.tp, detector.covered + detector.blind_spots)
            ),
            "recall_corpus": detector.corpus_recall,
            "recall_corpus_ci": list(
                wilson_interval(detector.confusion.tp, len(detector.outcomes))
            ),
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
    if clean is not None:
        payload["clean"] = {
            "total": clean.total,
            "flagged": clean.flagged,
            "flagged_fraction": clean.flagged_fraction,
            "total_findings": clean.total_findings,
            "avg_fp": clean.avg_fp,
        }
    return json.dumps(payload, indent=2, ensure_ascii=False)
