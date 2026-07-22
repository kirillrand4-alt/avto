#!/usr/bin/env python3
"""Dry-run калибровки confirm-send на 20 письмах (сдача ENGINEER-TASKS).

⛔ ХОЛД: ничего не отправляется. Скрипт: живой снапшот enrich.db (с дропа) →
отбор 20 лидов → генерация писем ЧЕРЕЗ ПРОВАЙДЕР (кэш, резюмируемо) →
инфо-панель build_panel() → confirm-очередь (все pending) → валидатор
MUST-полей → отчёт sender/calibration-dryrun-report.json.

Состав 20 лидов (живые данные, честный микс):
  * ~10 компаний С ПОЧТОЙ (реальные роли/mx/verified) — «повода нет,
    холодный заход»;
  * ~6 компаний С СИГНАЛОМ (реальная карточка повода; почты у них в
    снапшоте нет — адрес calib-<inn>@dryrun.invalid, .invalid недоставляем
    по RFC 2606 даже теоретически);
  * спецкейсы красной полосы: конкурент, verified=mismatch, мёртвый MX,
    отписанный (сеем suppression), недавний контакт (сеем send_log),
    письмо со снятой серией (Fini TERA110 в тексте, лид synthetic).

Запуск (из seo-texts/): python3 sender/tools/calibration_dryrun.py
  [--db sender/calibration.db] [--enrich <snapshot>] [--workers 6] [--no-gen]
--no-gen: без провайдера (письма-шаблоны) — для быстрой проверки конвейера.
"""
import argparse
import concurrent.futures as cf
import json
import pathlib
import random
import sqlite3
import sys
import time
from datetime import datetime, timezone

SENDER = pathlib.Path(__file__).resolve().parents[1]
ROOT = SENDER.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "email-assistant"))

DEFAULT_ENRICH = ("/tmp/claude-0/-home-user-avto/"
                  "ff023a20-c8a9-568e-a006-378d8c2b38dc/scratchpad/"
                  "enrich_snapshot.db")
CACHE = SENDER / ".calib-cache"
REPORT = SENDER / "calibration-dryrun-report.json"

MUST_FIELDS = [
    # (панель-путь, название в ТЗ)
    ("stop_flags", "1. стоп-флаги"),
    ("scoring", "2. скоринг-шапка"),
    ("signal", "3. карточка повода"),
    ("contact", "4. контакт"),
    ("company", "5. компания-снипет"),
    ("letter", "6. письмо+подсветка"),
    ("kb", "7. KB-провенанс"),
    ("compliance", "8. комплаенс"),
    ("actions", "9. панель действий"),
    ("history", "10. история контактов"),
]


def pick_leads(enrich_path: str) -> list[dict]:
    cx = sqlite3.connect(f"file:{enrich_path}?mode=ro", uri=True)
    cx.row_factory = sqlite3.Row
    leads: list[dict] = []

    def add(inn, email, tag):
        leads.append({"inn": str(inn), "email": email, "tag": tag})

    # ~8 с почтой: лучшие роли первыми (снабжение/директор/гл.инженер);
    # слоты: 8 cold + 6 signal + 3 спецкейса снапшота + 3 посевных = 20.
    rows = cx.execute("""
        SELECT e.inn, e.email, e.role FROM emails e
          JOIN companies c ON c.inn = e.inn
         WHERE c.is_competitor = 0 AND COALESCE(c.verified,'') != 'mismatch'
           AND COALESCE(e.mx_ok, 1) = 1
         ORDER BY CASE e.role
                    WHEN 'снабжение/закупки' THEN 0 WHEN 'директор' THEN 1
                    WHEN 'гл.инженер' THEN 2 WHEN 'продажи' THEN 3 ELSE 9 END,
                  e.inn LIMIT 40""").fetchall()
    seen = set()
    for r in rows:
        if r["inn"] in seen:
            continue
        seen.add(r["inn"])
        add(r["inn"], r["email"], "cold_real_contact")
        if len(leads) >= 8:
            break

    # ~6 с сигналом (без почты в снапшоте) — карточка повода живая
    for r in cx.execute("""
        SELECT s.inn, MAX(s.hotness) h FROM signals s
          JOIN companies c ON c.inn = s.inn
         WHERE c.is_competitor = 0 AND COALESCE(c.verified,'') != 'mismatch'
         GROUP BY s.inn ORDER BY h DESC, s.inn LIMIT 6""").fetchall():
        add(r["inn"], f"calib-{r['inn']}@dryrun.invalid", "signal_lead")

    # спецкейсы красной полосы
    comp = cx.execute(
        "SELECT inn FROM companies WHERE is_competitor=1 LIMIT 1").fetchone()
    if comp:
        add(comp["inn"], f"calib-{comp['inn']}@dryrun.invalid", "competitor")
    mm = cx.execute(
        "SELECT inn FROM companies WHERE verified='mismatch' LIMIT 1").fetchone()
    if mm:
        add(mm["inn"], f"calib-{mm['inn']}@dryrun.invalid", "site_mismatch")
    dead = cx.execute(
        "SELECT inn, email FROM emails WHERE mx_ok=0 LIMIT 1").fetchone()
    if dead:
        add(dead["inn"], dead["email"], "dead_mx")
    cx.close()

    # синтетика поведения (данные компаний живые, поведение сеем сами):
    unsub = dict(leads[0])
    unsub = {"inn": unsub["inn"], "email": f"unsub-{unsub['inn']}@dryrun.invalid",
             "tag": "unsubscribed_seeded"}
    leads.append(unsub)
    recent = {"inn": leads[1]["inn"],
              "email": f"recent-{leads[1]['inn']}@dryrun.invalid",
              "tag": "recent_contact_seeded"}
    leads.append(recent)
    snyat = {"inn": leads[2]["inn"],
             "email": f"snyat-{leads[2]['inn']}@dryrun.invalid",
             "tag": "discontinued_series_in_letter"}
    leads.append(snyat)
    return leads[:20]


def _caller(prompt: str, max_tokens: int = 1200) -> str:
    import gen_provider  # type: ignore
    model, fallback = "claude-fable-5", "claude-opus-4-8"
    consecutive, last = 0, None
    for attempt in range(9):
        try:
            msg = gen_provider._raw_stream(
                [{"role": "user", "content": prompt}], model, max_tokens,
                thinking=False)
            text = "".join(b.text for b in msg.content
                           if getattr(b, "type", "") == "text")
            if text and len(text) >= 60:
                return text
            raise RuntimeError("короткий ответ")
        except Exception as exc:  # noqa: BLE001
            last = exc
            consecutive += 1
            if consecutive >= 3 and model != fallback:
                model, consecutive = fallback, 0
            time.sleep(min(30.0, (2 ** attempt) * 0.5) + random.uniform(0, 0.5))
    raise RuntimeError(f"провайдер не ответил: {last}")


def _json_prefix(raw: str) -> dict:
    """Первый JSON-объект из ответа; хвостовой мусор шлюза («Extra data»)
    не роняет прогон."""
    i = raw.find("{")
    if i < 0:
        return {}
    try:
        obj, _end = json.JSONDecoder().raw_decode(raw[i:])
        return obj if isinstance(obj, dict) else {}
    except ValueError:
        return {}


def gen_letter(lead_ctx: dict, kb_ctx: dict, *, no_gen: bool) -> dict:
    """Письмо по лид-контексту. Кэш по ИНН+email; резюмируемо."""
    key = f"{lead_ctx['inn']}-{lead_ctx['email'].split('@')[0][:20]}"
    key += "-tpl" if no_gen else "-gen"  # кэши режимов не смешиваются
    cache_f = CACHE / f"letter-{key}.json"
    if cache_f.exists():
        return json.loads(cache_f.read_text(encoding="utf-8"))

    comp = lead_ctx.get("company") or {}
    sig = (lead_ctx.get("signals") or [{}])[0] if lead_ctx.get("signals") else {}
    if no_gen:
        body = (f"Здравствуйте!\n\nПишу по теме сжатого воздуха для "
                f"{comp.get('name') or 'вашего производства'}.\n\n--\n"
                f"ООО «Руспром», ИНН 2221239841, prokompressor.ru\n"
                f"Не хотите получать письма — ответьте «отписаться».")
        row = {"subject": "Сжатый воздух для производства", "body": body,
               "generated": False}
    else:
        prompt = (
            "Напиши короткое холодное B2B-письмо (тема + тело) от менеджера "
            "ООО «Руспром» (prokompressor.ru, компрессоры/пневматика; "
            "направление meyer = фотосепараторы Meyer).\n"
            "ЖЁСТКИЕ ПРАВИЛА: без длинных тире; байлайн «ООО «Руспром», "
            "ИНН 2221239841, prokompressor.ru» в подписи; строка про отказ "
            "от писем («ответьте отписаться»); без слов «лучший/№1/"
            "гарантируем»; цифры ТОЛЬКО из данных ниже; 700-1100 знаков; "
            "тон инженера-практика, без воды.\n\n"
            f"КОМПАНИЯ: {comp.get('name') or '—'}; регион "
            f"{comp.get('region') or '—'}; деятельность: "
            f"{(comp.get('activity') or '')[:200] or 'по ОКВЭД ' + str(comp.get('okved') or '')}\n"
            f"ПОВОД: {sig.get('event_type') or 'нет (холодный заход)'} — "
            f"{(sig.get('what') or '')[:150]}"
            + (f"; сумма {sig['sum']}" if sig.get("sum") else "") + "\n"
            f"KB: {json.dumps({k: kb_ctx.get(k) for k in ('geo', 'price_band', 'signal_hint')}, ensure_ascii=False)}\n\n"
            "Ответ СТРОГО одним JSON: {\"subject\":\"...\",\"body\":\"...\"}"
        )
        raw = _caller(prompt)
        data = _json_prefix(raw)
        if not data.get("body"):
            raw = _caller(prompt)  # один повтор: шлюз бывает шумный
            data = _json_prefix(raw)
        row = {"subject": str(data.get("subject") or "")[:150],
               "body": str(data.get("body") or ""), "generated": True}
        if not row["body"]:
            raise RuntimeError(f"пустое письмо для {key}")
    cache_f.write_text(json.dumps(row, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    return row


def validate_must(panel: dict) -> list[str]:
    """Каких MUST-полей не хватает в панели (пусто = все на месте)."""
    missing = []
    for key, name in MUST_FIELDS:
        if key not in panel:
            missing.append(name)
    # содержательные проверки поверх наличия ключей
    if panel.get("scoring", {}).get("available") and \
            "score" not in panel["scoring"]:
        missing.append("2. балл скоринга")
    sig = panel.get("signal", {})
    if sig.get("present") and not sig.get("top", {}).get("source_url", ""):
        missing.append("3. source_url повода")
    if "hotkeys" not in panel.get("actions", {}):
        missing.append("9. хоткеи")
    if "recent_90d" not in panel.get("history", {}):
        missing.append("10. флаг <90 дн")
    if "не проверялось" not in str(panel.get("reserved", {}).get("catch_all")):
        missing.append("catch-all честная заглушка")
    return missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(SENDER / "calibration.db"))
    ap.add_argument("--enrich", default=DEFAULT_ENRICH)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-gen", action="store_true")
    args = ap.parse_args()
    CACHE.mkdir(exist_ok=True)

    from sender.confirm import ConfirmSend
    from sender.dtos import CampaignIn, MessageIn, RecipientIn, SequenceStepIn
    from sender.infopanel import build_panel, load_enrich_lead
    from sender.store import Store
    from sender.suppression import Suppression
    from kb_retrieve import select_for_lead

    class _Cfg:
        def get(self, key, default=None):
            return {"confirm.mode": "all"}.get(key, default)

    store = Store(args.db)
    store.init_schema()
    suppression = Suppression(store)
    confirm = ConfirmSend(_Cfg(), store, suppression)

    cid = store.create_campaign(CampaignIn(
        name="Калибровка confirm-send (dry-run)",
        legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="{subject}", body_tmpl="{body}"))

    leads = pick_leads(args.enrich)
    print(f"лидов отобрано: {len(leads)}", flush=True)

    # посев поведения для спецкейсов (durable в калибровочной БД)
    for L in leads:
        if L["tag"] == "unsubscribed_seeded":
            suppression.add_email(L["email"], "unsubscribe", source="calib_seed")
        if L["tag"] == "recent_contact_seeded":
            store.send_log_add(email=L["email"], inn=L["inn"],
                               subject="Прошлое касание (посев)",
                               outcome="sent", ts=datetime.now(timezone.utc))

    # enrich-контекст + kb + генерация писем (параллельно, кэш)
    def prepare(L):
        ctx = load_enrich_lead(L["inn"], db_path=args.enrich)
        comp = ctx.get("company") or {}
        sig0 = (ctx.get("signals") or [{}])
        sig0 = sig0[0] if sig0 else {}
        kb_ctx = select_for_lead({
            "city": "", "region": comp.get("region") or "",
            "sphere": (comp.get("activity") or "")[:40],
            "okved": comp.get("okved") or "", "division": comp.get("division") or "",
            "signal": ({"event_type": sig0.get("event_type"), "days_ago": 15}
                       if sig0 else None),
        })
        letter = gen_letter({**L, "company": comp,
                             "signals": ctx.get("signals")}, kb_ctx,
                            no_gen=args.no_gen)
        if L["tag"] == "discontinued_series_in_letter":
            letter = dict(letter)
            letter["body"] += ("\n\nP.S. Ранее вы спрашивали Fini TERA110 — "
                               "подберём актуальный аналог.")
        return L, ctx, kb_ctx, letter

    prepared = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in cf.as_completed([ex.submit(prepare, L) for L in leads]):
            prepared.append(fut.result())
            print(f"  готово: {prepared[-1][0]['email']}", flush=True)

    # сабмит в очередь: message (pending_review) + review с панелью
    rows_report = []
    for L, ctx, kb_ctx, letter in sorted(prepared, key=lambda t: t[0]["email"]):
        comp = ctx.get("company") or {}
        rid = store.upsert_recipient(RecipientIn(
            email=L["email"], domain=L["email"].split("@")[1], inn=L["inn"],
            company_name=comp.get("name"), okved=comp.get("okved"),
            segment=comp.get("division") or None, region=comp.get("region")))
        mid, _ = store.enqueue_message(MessageIn(
            idempotency_key=f"calib:{L['email']}", campaign_id=cid,
            recipient_id=rid, sequence_step_id=sid,
            scheduled_at=datetime.now(timezone.utc)), status="pending_review")
        panel = build_panel(
            inn=L["inn"], email=L["email"],
            letter_subject=letter["subject"], letter_body=letter["body"],
            company=comp, emails=ctx.get("emails") or [],
            signals=ctx.get("signals") or [], store=store, kb_ctx=kb_ctx)
        res = confirm.submit(
            email=L["email"], inn=L["inn"], campaign_id=cid,
            recipient_id=rid, message_id=mid,
            subject=letter["subject"], body=letter["body"], panel=panel)
        missing = validate_must(panel)
        rows_report.append({
            "email": L["email"], "inn": L["inn"], "tag": L["tag"],
            "review_id": res.review_id, "queue_status": res.status,
            "queue_reason": res.reason,
            "generated": letter.get("generated", False),
            "stop_flags": [f["code"] for f in panel.get("stop_flags", [])],
            "score": panel.get("scoring", {}).get("score"),
            "signal_present": panel.get("signal", {}).get("present"),
            "must_missing": missing,
        })
        print(f"  [{res.status}] {L['email']} флаги={rows_report[-1]['stop_flags']}"
              f" MUST-пропуски={missing or 'нет'}", flush=True)

    counts = store.confirm_counts()
    summary = {
        "letters": len(rows_report),
        "queue_counts": counts,
        "generated_via_provider": sum(1 for r in rows_report if r["generated"]),
        "all_must_fields_present": all(not r["must_missing"]
                                       for r in rows_report),
        "red_flag_cases": {r["tag"]: r["stop_flags"] for r in rows_report
                           if r["stop_flags"]},
        "db": args.db,
        "hold": "реальная отправка не выполнялась (SMTP не вызывался)",
    }
    REPORT.write_text(json.dumps({"summary": summary, "letters": rows_report},
                                 ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1), flush=True)
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
