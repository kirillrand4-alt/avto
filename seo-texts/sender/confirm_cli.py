"""Текстовый рендер инфо-панели confirm-send для CLI (Задача 4 — паритет).

CLI рендерит ТЕ ЖЕ JSON-поля панели, что и веб-экран: build_panel() один,
представления два. Здесь только форматирование текста — никакой логики.
"""

from __future__ import annotations

from typing import Any


def _flag_line(flags: list[dict]) -> list[str]:
    if not flags:
        return ["  стоп-флагов нет"]
    return [f"  ⛔ {f['label']}" for f in flags]


def _bar(val: int, mx: int, width: int = 10) -> str:
    filled = 0 if mx <= 0 else round(width * min(val, mx) / mx)
    return "█" * filled + "·" * (width - filled)


def render_panel_text(review: dict) -> str:
    """Полный экран одного письма: панель + письмо + действия."""
    p: dict[str, Any] = review.get("panel") or {}
    out: list[str] = []
    rid = review.get("id")
    out.append(f"═══ Письмо на подтверждение #{rid} "
               f"[{review.get('status', '?')}] ═══")
    out.append(f"Кому: {review.get('email')}  ИНН: {review.get('inn') or '—'}"
               f"  кампания: {review.get('campaign_id') or '—'}")

    # 1. Красная полоса стоп-флагов — ДО письма.
    flags = p.get("stop_flags") or []
    out.append("")
    out.append("── СТОП-ФЛАГИ " + ("🔴" * len(flags) if flags else "🟢"))
    out.extend(_flag_line(flags))
    if flags:
        out.append("  ⚠ «Отправить» требует двойного подтверждения (--force)")

    # 2. Скоринг-шапка.
    s = p.get("scoring") or {}
    if s.get("available"):
        parts = s.get("parts") or {}
        out.append("")
        out.append(f"── СКОРИНГ: {s.get('score', 0)}/90 "
                   f"({s.get('color')})  {s.get('capex_badge', '')}"
                   f"  buying_power={s.get('buying_power', '—')}"
                   + (f"  бюджет:{s['budget_confirmed']}"
                      if s.get("budget_confirmed") else ""))
        out.append(f"   сигнал  {_bar(parts.get('signal', 0), 40)} "
                   f"{parts.get('signal', 0)}/40")
        out.append(f"   выручка {_bar(parts.get('revenue', 0), 20)} "
                   f"{parts.get('revenue', 0)}/20")
        out.append(f"   verified{_bar(parts.get('verified', 0), 15)} "
                   f"{parts.get('verified', 0)}/15")
        out.append(f"   роль    {_bar(parts.get('role', 0), 15)} "
                   f"{parts.get('role', 0)}/15")

    # 3. Повод.
    sig = p.get("signal") or {}
    out.append("")
    if sig.get("present"):
        t = sig["top"]
        out.append(f"── ПОВОД: {t.get('event_type')} {t.get('stars', '')}"
                   f"  {t.get('date', '')}")
        out.append(f"   {t.get('what', '')}"
                   + (f"  [{t['sum']}]" if t.get("sum") else ""))
        if t.get("source_url"):
            out.append(f"   ссылка: {t['source_url'][:100]}")
        for o in sig.get("others") or []:
            out.append(f"   + {o.get('event_type')}: {o.get('what', '')[:60]}")
    else:
        out.append(f"── ПОВОД: {sig.get('label', 'нет данных')}")

    # 3b. ВСЕ новостные события со ссылками (§3 BASE-MERGE).
    ne = p.get("news_events") or {}
    if ne.get("count"):
        out.append("")
        out.append(f"── НОВОСТНЫЕ СОБЫТИЯ ({ne['count']}) — каждая ссылка "
                   "кликабельна")
        for ev in ne.get("events") or []:
            mark = "✅" if ev.get("match_ok") else "🟡"
            out.append(f"   {mark} [{ev.get('signal_match')}] "
                       f"{ev.get('event_type')} {ev.get('date', '')}"
                       + (f"  [{ev['sum']}]" if ev.get("sum") else ""))
            what = ev.get("what") or ev.get("news_object") or ""
            if what:
                out.append(f"      {what[:120]}")
            if ev.get("source_url"):
                out.append(f"      {ev.get('source_name') or 'источник'}: "
                           f"{ev['source_url']}")

    # 4. Контакт.
    c = p.get("contact") or {}
    lpr_mark = {"match": "✅ ЛПР совпал", "mismatch": "⚠ ЛПР разные",
                "impersonal": "— безлично", "no_data": "— нет данных ЛПР"}
    out.append("")
    out.append(f"── КОНТАКТ: {c.get('email')}  "
               f"{'🔴 ' if c.get('router') else ''}{c.get('role', '')}"
               f"  {c.get('person') or ''}")
    mx = c.get("mx_ok")
    out.append(f"   {lpr_mark.get(c.get('lpr'), '')}; "
               f"mx: {'✅' if mx else ('❌ МЁРТВ' if mx is False else 'не проверялся')}; "
               f"verified: {c.get('verified_icons', '—')}")
    if c.get("domain_mismatch"):
        out.append(f"   🟡 домен письма {c.get('email_domain')} ≠ "
                   f"домен сайта {c.get('site_domain')}")

    # 5. Компания.
    comp = p.get("company") or {}
    out.append("")
    out.append(f"── КОМПАНИЯ [{comp.get('division_badge', '—')}]: "
               f"{comp.get('name', '—')}  {comp.get('region', '')}")
    out.append(f"   выручка: {comp.get('revenue_h', 'нет данных')}; "
               f"ОКВЭД {comp.get('okved', '—')}; "
               f"директор: {comp.get('director') or '—'}")
    if comp.get("activity"):
        out.append(f"   занимается: {comp['activity'][:100]}")
    out.append(f"   зачем оборудование: {comp.get('why_equipment', '')}")

    # 5b. Полная карточка компании (§3 BASE-MERGE: «вся информация»).
    cf = p.get("company_full") or {}
    if cf.get("available"):
        out.append("")
        div = cf.get("division") or "НЕ ОПРЕДЕЛЕНО"
        out.append(f"── ПОЛНАЯ КАРТОЧКА  направление: {div} (база обзвона)"
                   + (f"; предположение enrich: {cf['division_guess']}"
                      if cf.get("division_guess") else ""))
        reg = cf.get("reg") or {}
        if reg.get("name_short"):
            out.append(f"   {reg.get('name_short')}  {reg.get('status', '')}"
                       f"  {reg.get('address', '')[:80]}")
            out.append(f"   ОКВЭД {reg.get('okved_main', '')[:60]}; "
                       f"все: {reg.get('okved_all_codes', '')[:80]}")
        prod = cf.get("product") or {}
        if prod.get("equip_categories"):
            out.append(f"   продукт: {prod['equip_categories'][:90]} "
                       f"(балл {cf.get('priority', {}).get('priority_max', '—')})")
        cts = cf.get("contacts") or {}
        for e in (cts.get("emails") or [])[:6]:
            src = e.get("source_url") or e.get("source") or ""
            out.append(f"   ✉ {e.get('email')}  {e.get('role', '')} "
                       f"[{e.get('origin')}] {src[:70]}")
        for ph in (cts.get("phones") or [])[:6]:
            out.append(f"   ☎ {ph.get('phone')}  [{ph.get('source')}]")
        sv = cf.get("site_view") or {}
        if sv.get("site"):
            out.append(f"   сайт: {sv['site']} (verified: {sv.get('site_verified')})")
        elif sv.get("cand_site"):
            out.append(f"   сайт-кандидат: {sv['cand_site']} "
                       f"({sv.get('cand_site_note')})")
        opo = cf.get("opo") or {}
        if opo.get("object") or opo.get("flag"):
            out.append(f"   ОПО: {opo.get('object') or opo.get('flag')}"
                       + (f"  источник: {opo['source'][:60]}"
                          if opo.get("source") else ""))
        if (cf.get("zakupki") or {}).get("contact"):
            out.append(f"   закупки: {cf['zakupki']['contact'][:90]}")

    # 6. Письмо.
    letter = p.get("letter") or {}
    out.append("")
    out.append(f"── ПИСЬМО: {letter.get('subject') or review.get('subject')}")
    body = letter.get("body") or review.get("body") or ""
    for line in body.splitlines():
        out.append(f"   │ {line}")
    hls = letter.get("highlights") or []
    if hls:
        out.append("   подстановки: " + "; ".join(
            f"[{h['kind']}] {h['text']}" for h in hls[:8]))

    # 7. KB-провенанс.
    kb = p.get("kb") or {}
    if kb.get("cases") or kb.get("geo_fact_str") or kb.get("trigger_phrase"):
        out.append("")
        out.append("── KB-ПРОВЕНАНС:")
        for case in kb.get("cases") or []:
            out.append(f"   кейс {case.get('id')}: {case.get('city')} — "
                       f"{case.get('what', '')[:70]}")
        if kb.get("price_band"):
            out.append(f"   ценовой коридор: {kb['price_band']}")
        if kb.get("geo_fact_str"):
            claim = kb.get("geo_claimed")
            mark = " 🟡 ЗАВЫШЕНО" if kb.get("geo_overclaim") else ""
            out.append(f"   гео-факт: {kb['geo_fact_str']}"
                       + (f" (в письме: {claim}){mark}" if claim else ""))
        if kb.get("trigger_phrase"):
            conf = kb.get("trigger_confirmed")
            out.append(f"   триггер: {kb['trigger_phrase'][:80]} "
                       f"(подтверждено signals: "
                       f"{'да' if conf else 'нет' if conf is not None else '—'})")

    # 8. Комплаенс.
    cm = p.get("compliance") or {}
    out.append("")
    out.append("── КОМПЛАЕНС ФЗ-38/152:")
    out.append(f"   атрибуция ООО «Руспром»+ИНН/URL: "
               f"{'✅' if cm.get('attribution_ok') else '🔴 НЕТ'}")
    out.append(f"   отписка в теле: "
               f"{'✅' if cm.get('unsub_in_body') else '🔴 нет'}"
               + (f" ({cm['unsub_note']})" if cm.get("unsub_note") else ""))
    out.append(f"   персданные (ФИО): ×{cm.get('fio_count', 0)} "
               f"[шкала {cm.get('fio_scale', '0')}]")
    if cm.get("banned_phrases"):
        out.append(f"   🟡 обороты: {', '.join(cm['banned_phrases'])}")

    # 10. История контактов.
    h = p.get("history") or {}
    out.append("")
    if h.get("items"):
        last = h.get("last") or {}
        flag = " 🔴 <90 дн!" if h.get("recent_90d") else ""
        out.append(f"── ИСТОРИЯ: контактов {len(h['items'])}; последняя "
                   f"отправка {str(last.get('ts', ''))[:10]}"
                   f" «{last.get('subject') or ''}»{flag}"
                   + ("; был ответ" if h.get("replied_before") else ""))
    else:
        out.append("── ИСТОРИЯ: контактов не было"
                   + (f" ({h['note']})" if h.get("note") else ""))

    # SHOULD-строка (кратко).
    sh = p.get("should") or {}
    if sh:
        d = sh.get("deliverability") or {}
        light = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(d.get("light"), "")
        bits = [f"доставляемость {light} ({d.get('why', '')})"]
        if sh.get("contact_age_days") is not None:
            bits.append(f"возраст контакта {sh['contact_age_days']} дн"
                        f" [{sh.get('contact_age_flag')}]")
        if sh.get("price_gap"):
            bits.append("🟡 ценовой разрыв (прайс выше buying_power)")
        if sh.get("domain_concentration") and sh["domain_concentration"] > 1:
            bits.append(f"домен в пачке ×{sh['domain_concentration']}")
        bits.append(f"основание: {sh.get('legal_basis', '—')}")
        out.append("── ДОП: " + "; ".join(bits))

    reserved = p.get("reserved") or {}
    if reserved.get("catch_all"):
        out.append(f"   catch-all: {reserved['catch_all']}")

    # 9. Действия.
    out.append("")
    out.append("── [Enter] Отправить  [E] Править  [S] Скип  [X] Стоп-лист")
    return "\n".join(out)


def render_queue_text(rows: list[dict], counts: dict) -> str:
    """Список очереди подтверждений (компактно)."""
    out = [f"Очередь подтверждений: pending={counts.get('pending', 0)} "
           f"approved={counts.get('approved', 0)} edited={counts.get('edited', 0)} "
           f"skipped={counts.get('skipped', 0)} stoplist={counts.get('stoplist', 0)}"]
    for r in rows:
        p = r.get("panel") or {}
        flags = len(p.get("stop_flags") or [])
        score = (p.get("scoring") or {}).get("score", "—")
        out.append(f"  #{r['id']:>4} {r.get('email', ''):<35} "
                   f"балл={score:<4} флагов={flags} «{(r.get('subject') or '')[:40]}»")
    return "\n".join(out)
