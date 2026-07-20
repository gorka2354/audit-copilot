# Eval-артефакты (воспроизводимые)

`detector-eval.md` / `detector-eval.json` — снимок detector-level eval, сгенерированный
**вхолодную**: реальный движок через `ReplayAnalyzer` + публичный корпус DeFiVulnLabs, без
приватного security-lab, без LLM-ключа и без сети.

## Воспроизвести

```bash
uv run python scripts/demo_eval.py --sample 0 --out assets/eval/reports/detector-eval
```

Числа детерминированы (fixtures записаны один раз), поэтому артефакт не дрейфует и защищён
CI-гейтом (`tests/unit/test_recall_gate.py`): если recall упадёт ниже базлайна, сборка
краснеет. Это отличает «показываю метрику» от «утверждаю метрику».

Agent-level (grounding, стоимость, латентность) требует LLM-ключа и живой инфраструктуры —
отдельный прогон `make eval SAMPLE=5 EVAL_ARGS=--judge`; в CI не гейтится, потому что без
ключа невоспроизводим.

Сгенерировано: 2026-07-20.
