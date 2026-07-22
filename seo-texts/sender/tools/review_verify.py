#!/usr/bin/env python3
"""Задача 5: перепрогон ревью-хвостов ЧЕРЕЗ ПРОВАЙДЕР (ENGINEER-TASKS-CONFIRM-SEND).

Два режима в одном скрипте (оба резюмируемы, кэш на диске):
  findings — верификация critical/high находок из REVIEW-FINDINGS.json ПРОТИВ
             ТЕКУЩЕГО кода (многие уже закрыты фиксами П1-П3 сессии 2026-07-21 —
             вердикт «исправлен» валиден); короткие ответы (обрыв шлюза был на
             длинных), кэш по хэшу находки;
  modules  — свежее ревью 10 модулей, не распарсенных в прошлый раз
             (postoffice ramp warmup unsub unsub_server tokens regions importer
             reply_classify config), по одному модулю на вызов.

Рецепт вызова — проверенный (review_lenses.default_caller): _raw_stream,
claude-fable-5, thinking=False, ретраи 8 с бэкофф+джиттер, фолбэк opus-4-8
после 3 подряд провалов, контекст <50КБ.

Запуск (из seo-texts/):
  python3 sender/tools/review_verify.py findings --workers 6
  python3 sender/tools/review_verify.py modules  --workers 3
Итоги: sender/.review-verify-cache/*.json -> сводка review-tails-report.json
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import pathlib
import random
import re
import sys
import time

SENDER = pathlib.Path(__file__).resolve().parents[1]
ROOT = SENDER.parent
sys.path.insert(0, str(ROOT))

FINDINGS_JSON = pathlib.Path(
    "/tmp/claude-0/-home-user-avto/ff023a20-c8a9-568e-a006-378d8c2b38dc"
    "/scratchpad/REVIEW-FINDINGS.json")
CACHE = SENDER / ".review-verify-cache"
REPORT = SENDER / "review-tails-report.json"

UNPARSED_MODULES = [
    "postoffice.py", "ramp.py", "warmup.py", "unsub.py", "unsub_server.py",
    "tokens.py", "regions.py", "importer.py", "reply_classify.py", "config.py",
]

# Фиксы этой ветки, о которых верификатор должен знать (иначе будет
# «подтверждать» дыры, закрытые коммитами 4589553/8bcf449/51ae558).
FIXED_CONTEXT = """Свежие фиксы уже в коде (учитывай, НЕ подтверждай закрытое):
- нормализация email/домена/ИНН в upsert_recipient + lower(trim()) в SQL suppression;
- отписка бессрочна (DO UPDATE-апгрейд, не истекает, не снимается);
- one-click: 404 при неудаче; токен отписки унифицирован (sender -> tokens.py, параметр t);
- has_reply перепроверяется в send() перед SMTP; STARTTLS на не-SSL портах до login;
- CRLF-санация Subject/To/From; fail-safe чтения/записи паузы и оценки гейтов;
- bounce-гейт каденции по recipient_id; next_step_for по sent-событиям;
- day_key в зоне конфига; XSS-эскейп токена; лимит Content-Length; extra_json
  не перетирается пустым; RCPT-проба переживает не-int код."""


def _caller(prompt: str, max_tokens: int = 1600) -> str:
    """Провайдерский вызов по проверенному рецепту (стриминг внутри _raw_stream)."""
    import gen_provider  # type: ignore

    model = "claude-fable-5"
    fallback = "claude-opus-4-8"
    messages = [{"role": "user", "content": prompt}]
    consecutive = 0
    last = None
    for attempt in range(9):
        try:
            msg = gen_provider._raw_stream(messages, model, max_tokens, thinking=False)
            text = "".join(
                b.text for b in msg.content if getattr(b, "type", "") == "text")
            if text and len(text) >= 20:
                return text
            raise RuntimeError("слишком короткий ответ")
        except Exception as exc:  # noqa: BLE001 - флаки-шлюз
            last = exc
            consecutive += 1
            if consecutive >= 3 and model != fallback:
                model = fallback
                consecutive = 0
            time.sleep(min(30.0, (2 ** attempt) * 0.5) + random.uniform(0, 0.5))
    raise RuntimeError(f"провайдер не ответил: {last}")


def _find_json(raw: str):
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Режим findings
# ---------------------------------------------------------------------------

def _code_excerpt(finding: dict) -> str:
    """±70 строк текущего кода вокруг лучшей привязки находки.

    Номера строк в находках — от снапшота ревью (код с тех пор сдвинулся);
    привязываемся по номеру как по ориентиру, но даём широкое окно.
    """
    rel = finding.get("file", "")
    path = ROOT.parent / rel if not rel.startswith("seo-texts") else ROOT.parent / rel
    path = pathlib.Path(str(path).replace("seo-texts/seo-texts", "seo-texts"))
    if not path.exists():
        path = ROOT / rel.replace("seo-texts/", "")
    if not path.exists():
        return f"(файл {rel} не найден в текущей ветке)"
    lines = path.read_text(encoding="utf-8").splitlines()
    ln = int(finding.get("line") or 1)
    lo = max(0, ln - 70)
    hi = min(len(lines), ln + 70)
    body = "\n".join(f"{i+1}\t{lines[i]}" for i in range(lo, hi))
    if len(body) > 24000:
        body = body[:24000]
    return body


def verify_finding(idx: int, finding: dict) -> dict:
    key = hashlib.sha256(json.dumps(finding, sort_keys=True).encode()).hexdigest()[:16]
    cache_f = CACHE / f"finding-{idx:03d}-{key}.json"
    if cache_f.exists():
        return json.loads(cache_f.read_text(encoding="utf-8"))

    excerpt = _code_excerpt(finding)
    prompt = (
        "Ты состязательный верификатор находки код-ревью. Ниже находка "
        "(номера строк — от СТАРОГО снапшота) и АКТУАЛЬНЫЙ фрагмент кода. "
        "По умолчанию скептичен: подтверждай только то, что видно в коде.\n\n"
        f"{FIXED_CONTEXT}\n\n"
        f"НАХОДКА [{finding.get('severity')}] {finding.get('file')}:{finding.get('line')}\n"
        f"{finding.get('summary')}\n"
        f"Сценарий: {finding.get('failure_scenario', '')[:600]}\n\n"
        f"ТЕКУЩИЙ КОД ({finding.get('file')}):\n{excerpt}\n\n"
        "Ответ СТРОГО одним JSON (коротко, без прозы вокруг): "
        '{"verdict":"confirmed|false|fixed","why":"<=40 слов",'
        '"fix_hint":"<=30 слов или пусто"}'
    )
    raw = _caller(prompt)
    data = _find_json(raw) or {"verdict": "parse_error", "why": raw[:200]}
    row = {"idx": idx, "file": finding.get("file"), "line": finding.get("line"),
           "severity": finding.get("severity"),
           "summary": finding.get("summary", "")[:200], **data}
    cache_f.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[f{idx}] {row.get('verdict')}: {finding.get('file')}:{finding.get('line')}",
          flush=True)
    return row


def run_findings(workers: int) -> list[dict]:
    items = json.loads(FINDINGS_JSON.read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("findings", [])
    targets = [(i, f) for i, f in enumerate(items)
               if f.get("severity") in ("critical", "high")]
    print(f"к верификации: {len(targets)} critical/high", flush=True)
    rows = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(verify_finding, i, f): i for i, f in targets}
        for fut in cf.as_completed(futs):
            try:
                rows.append(fut.result())
            except Exception as e:  # noqa: BLE001
                rows.append({"idx": futs[fut], "verdict": "error", "why": str(e)[:200]})
                print(f"[f{futs[fut]}] ОШИБКА: {e}", flush=True)
    return sorted(rows, key=lambda r: r.get("idx", 0))


# ---------------------------------------------------------------------------
# Режим modules
# ---------------------------------------------------------------------------

def review_module(name: str) -> dict:
    cache_f = CACHE / f"module-{name}.json"
    if cache_f.exists():
        return json.loads(cache_f.read_text(encoding="utf-8"))

    src = (SENDER / name).read_text(encoding="utf-8")
    if len(src) > 45000:
        src = src[:45000] + "\n# ... (обрезано до 45КБ)"
    prompt = (
        "Ты строгий ревьюер продакшн-кода рассыльщика (Python stdlib, SQLite). "
        "Модуль ниже. Ищи ТОЛЬКО реальные дефекты: юр-риски ФЗ-38/152 "
        "(отписка/атрибуция/персданные), потерю/дублирование писем, гонки, "
        "fail-open, инъекции, краши на реальных входах. Стиль/вкусовщину не "
        "предлагай. На каждый дефект — точная привязка и сценарий отказа.\n\n"
        f"{FIXED_CONTEXT}\n\n"
        f"=== sender/{name} ===\n{src}\n\n"
        "Ответ СТРОГО одним JSON: {\"findings\":[{\"line\":N,"
        "\"severity\":\"critical|high|medium|low\",\"summary\":\"...\","
        "\"scenario\":\"...\",\"fix_hint\":\"...\"}]} — максимум 8 самых важных; "
        "если дефектов нет, findings=[]."
    )
    raw = _caller(prompt, max_tokens=2500)
    data = _find_json(raw) or {"findings": [], "parse_error": raw[:300]}
    row = {"module": name, **data}
    cache_f.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(row.get("findings") or [])
    print(f"[{name}] находок: {n}", flush=True)
    return row


def run_modules(workers: int) -> list[dict]:
    rows = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(review_module, m): m for m in UNPARSED_MODULES}
        for fut in cf.as_completed(futs):
            try:
                rows.append(fut.result())
            except Exception as e:  # noqa: BLE001
                rows.append({"module": futs[fut], "error": str(e)[:200]})
                print(f"[{futs[fut]}] ОШИБКА: {e}", flush=True)
    return sorted(rows, key=lambda r: r.get("module", ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["findings", "modules", "report"])
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    CACHE.mkdir(exist_ok=True)

    if args.mode == "findings":
        rows = run_findings(args.workers)
        out = {"findings_verified": rows}
    elif args.mode == "modules":
        rows = run_modules(args.workers)
        out = {"modules_reviewed": rows}
    else:  # report: собрать всё из кэша
        f_rows = [json.loads(p.read_text(encoding="utf-8"))
                  for p in sorted(CACHE.glob("finding-*.json"))]
        m_rows = [json.loads(p.read_text(encoding="utf-8"))
                  for p in sorted(CACHE.glob("module-*.json"))]
        out = {"findings_verified": f_rows, "modules_reviewed": m_rows}

    # Мердж в общий отчёт (не затирая другой режим).
    existing = {}
    if REPORT.exists():
        try:
            existing = json.loads(REPORT.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            existing = {}
    existing.update(out)
    from collections import Counter
    fv = existing.get("findings_verified") or []
    existing["summary"] = {
        "verified_total": len(fv),
        "verdicts": dict(Counter(str(r.get("verdict")) for r in fv)),
        "modules_done": len(existing.get("modules_reviewed") or []),
        "module_findings": sum(len(m.get("findings") or [])
                               for m in existing.get("modules_reviewed") or []),
    }
    REPORT.write_text(json.dumps(existing, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(json.dumps(existing["summary"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
