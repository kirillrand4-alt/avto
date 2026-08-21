# -*- coding: utf-8 -*-
"""Почему отбивок стало резко больше: доля по дням и разбор сегодняшних.

Считаем ЧЕСТНУЮ долю: отбивки дня к отправленному в тот же день. Потом
разбираем каждую сегодняшнюю отбивку до диагностики почтового сервера и
смотрим, откуда взялся адрес: из вебинарного списка, из копии второму
контакту или из обычной партии - у этих трёх источников разное качество
адресов, и валить их в одну кучу нельзя.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

# --- доля отбивок по дням -------------------------------------------------
ушло = Counter(str(р[0]) for р in c.execute(
    "SELECT substr(COALESCE(sent_at,updated_at),1,10) FROM messages "
    "WHERE status='sent'"))
отб = Counter(str(р[0]) for р in c.execute(
    "SELECT substr(COALESCE(event_ts,created_at),1,10) FROM events "
    "WHERE event_type='bounce'"))
дни = sorted(set(ушло) | set(отб))[-16:]
print(f"{'день':<12} {'ушло':>6} {'отбивок':>8} {'доля':>7}")
for д in дни:
    у, о = ушло.get(д, 0), отб.get(д, 0)
    print(f"{д:<12} {у:>6} {о:>8} {(100.0*о/у if у else 0):>6.1f}%")

# --- сегодняшние отбивки поштучно ----------------------------------------
ряды = c.execute(
    "SELECT e.id, e.campaign_id, e.mailbox_id, e.message_id, "
    "       COALESCE(e.detail_json,'') dj, substr(e.event_ts,1,16) когда, "
    "       m.subject, r.email, r.company_name, "
    "       cr.dedup_key, substr(m.sent_at,1,16) ушло_в "
    "  FROM events e "
    "  LEFT JOIN messages m ON m.id=e.message_id "
    "  LEFT JOIN recipients r ON r.id=e.recipient_id "
    "  LEFT JOIN confirm_reviews cr ON cr.message_id=e.message_id "
    " WHERE e.event_type='bounce' "
    "   AND substr(COALESCE(e.event_ts,e.created_at),1,10)='2026-08-21' "
    " ORDER BY e.id").fetchall()
print(f"\nсегодняшних отбивок: {len(ряды)}\n")
источники = Counter()
for р in ряды:
    try:
        д = json.loads(р["dj"] or "{}")
    except Exception:                                              # noqa: BLE001
        д = {}
    ключ = str(р["dedup_key"] or "")
    ист = ("вебинар" if ключ.startswith("vebinar28:") else
           "обычная партия" if ключ else "неизвестно")
    источники[ист] += 1
    вердикт = д.get("verdict") or д.get("kind") or "?"
    код = д.get("smtp_code") or д.get("status") or ""
    диаг = str(д.get("diagnostic") or д.get("reason") or d if False else
               д.get("diagnostic") or д.get("reason") or "")[:150]
    print(f"#{р['id']} {р['когда']} камп{р['campaign_id']} [{ист}]")
    print(f"   адрес: {р['email']} ({str(р['company_name'])[:32]})")
    print(f"   ящик:  {р['mailbox_id']} | письмо ушло {р['ушло_в']}")
    print(f"   вердикт: {вердикт} код: {код}")
    if диаг:
        print(f"   диагностика: {диаг}")
    if not вердикт or вердикт == "?":
        print(f"   detail_json: {str(р['dj'])[:220]}")
print("источники адресов:", dict(источники))
