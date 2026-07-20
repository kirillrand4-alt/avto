#!/usr/bin/env python3
"""Golden-прогон ревью-конвейера по 14 письмам дрйрана email-assistant.

Черновики дрйрана содержат ИЗВЕСТНЫЕ посаженные проблемы (скептик их уже ловил):
незакрытый горячий торг №9, неподтверждённые базой цифры/модели №3/№5/№12.
Конвейер (qa_reply -> 8 LLM-линз -> судья) обязан поймать их сам — это метрика
recall реальных ошибок (REVIEW-CHAIN.md §Тест-сет).

Прогон ЖИВОЙ (провайдерский API, claude-fable-5, thinking=False), поэтому:
- regenerate НЕ передаём: артефакт — вердикты ПЕРВОГО прохода (петля
  перегенерации покрыта юнитами с фейками);
- кэш по письмам в .golden-cache/ (резюмируемо после рестарта);
- письма параллелятся (линзы внутри письма — последовательно);
- итог пишется в sender/autoresponder-golden-report.json (коммитится, его
  инварианты проверяет tests/test_golden_report.py).

Запуск (из seo-texts/): python3 sender/tools/run_golden_review.py [--workers 4]
"""
import argparse
import concurrent.futures as cf
import json
import pathlib
import sys
import time

SENDER = pathlib.Path(__file__).resolve().parents[1]
ROOT = SENDER.parent
sys.path.insert(0, str(ROOT))

from sender.reply_classify import classify_reply  # noqa: E402
from sender.review_chain import review_chain  # noqa: E402
from sender.review_lenses import kb_slice_for  # noqa: E402

EA = ROOT / "email-assistant"
CACHE = SENDER / ".golden-cache"
REPORT = SENDER / "autoresponder-golden-report.json"


def load_corpus():
    letters = json.loads((EA / "dryrun-letters.json").read_text(encoding="utf-8"))
    results = json.loads((EA / "dryrun-results.json").read_text(encoding="utf-8"))
    kb = json.loads((EA / "answer-kb.json").read_text(encoding="utf-8"))
    drafts = {}
    for i, r in enumerate(results, start=1):
        drafts[i] = r.get("draft") or ""
    return letters, drafts, kb


def run_letter(n: int, incoming: str, draft: str, kb: dict) -> dict:
    cache_f = CACHE / f"letter-{n}.json"
    if cache_f.exists():
        return json.loads(cache_f.read_text(encoding="utf-8"))

    signal = classify_reply("Re: ваш запрос", incoming)
    kb_slice = kb_slice_for(incoming + "\n" + draft, kb)
    t0 = time.time()
    res = review_chain(
        "Re: ваш запрос" if draft else "",
        draft,
        incoming=incoming,
        reply_kind=signal.kind,
        kb_slice=kb_slice,
        regenerate=None,  # артефакт = первый проход
    )
    row = {
        "n": n,
        "reply_kind": signal.kind,
        "decision": res.decision,
        "iterations": res.iterations,
        "escalate_reason": res.escalate_reason,
        "qa_problems": list(res.qa_problems),
        "verdicts": {
            name: {"verdict": v.verdict, "problems": list(v.problems),
                   "model": v.model}
            for name, v in res.verdicts.items()
        },
        "sec": round(time.time() - t0, 1),
        "draft_empty": not draft.strip(),
    }
    cache_f.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{n}] {row['decision']} ({row['sec']}s) qa={len(row['qa_problems'])} "
          f"crit={[k for k, v in row['verdicts'].items() if v['verdict'] == 'CRITICAL']}",
          flush=True)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    CACHE.mkdir(exist_ok=True)
    letters, drafts, kb = load_corpus()

    rows = {}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(run_letter, item["n"], item["letter"],
                      drafts.get(item["n"], ""), kb): item["n"]
            for item in letters
        }
        for fut in cf.as_completed(futs):
            n = futs[fut]
            try:
                rows[n] = fut.result()
            except Exception as e:  # noqa: BLE001
                rows[n] = {"n": n, "error": str(e)}
                print(f"[{n}] ОШИБКА: {e}", flush=True)

    ordered = [rows[k] for k in sorted(rows)]
    ok = [r for r in ordered if "error" not in r]
    send_first_try = sum(1 for r in ok if r["decision"] == "SEND")

    def fact_critical(r):
        v = r.get("verdicts", {}).get("fact_check", {})
        return v.get("verdict") == "CRITICAL"

    summary = {
        "letters": len(ordered),
        "errors": [r["n"] for r in ordered if "error" in r],
        "send_first_try": send_first_try,
        "send_first_try_pct": round(100 * send_first_try / max(1, len(ok))),
        # обязательные попадания спеки (проверяет тест):
        "n9_escalated": next((r["decision"] == "ESCALATE" for r in ok if r["n"] == 9), False),
        "n3_fact_critical": next((fact_critical(r) for r in ok if r["n"] == 3), False),
        "n5_fact_critical": next((fact_critical(r) for r in ok if r["n"] == 5), False),
        "n12_caught": next((r["decision"] != "SEND" for r in ok if r["n"] == 12), False),
    }
    report = {"summary": summary, "letters": ordered}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1), flush=True)
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
