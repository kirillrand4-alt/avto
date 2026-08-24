# -*- coding: utf-8 -*-
"""Откуда 14 баунсов: кто отбился, из какого ящика, с какой причиной.

Владелец 24.08: «посмотри баунсы 14 штук — откуда они». Печатаем полный
разбор: событие, адрес, домен получателя, ящик-отправитель, код и текст
отчёта о недоставке, а следом — сводки по ящику, по домену получателя и
по коду, чтобы было видно, это наша проблема или мусор в базе.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

СУТКИ = "2026-08-24"

def детали(строка):
    try:
        return json.loads(строка or "{}")
    except Exception:  # noqa: BLE001
        return {}

всё = c.execute(
    "SELECT e.id, e.event_ts, e.mailbox_id, e.message_id, e.detail_json, "
    "       r.email, r.company_name, r.inn, r.mx_provider, "
    "       m.subject, m.sent_at "
    "  FROM events e "
    "  LEFT JOIN recipients r ON r.id = e.recipient_id "
    "  LEFT JOIN messages   m ON m.id = e.message_id "
    " WHERE e.event_type='bounce' ORDER BY e.event_ts").fetchall()

сегодня = [р for р in всё if str(р["event_ts"])[:10] == СУТКИ]
print("баунсов всего в базе: %d, из них за %s: %d"
      % (len(всё), СУТКИ, len(сегодня)))

показать = сегодня if сегодня else всё[-20:]
print("\n=== РАЗБОР (%d шт) ===" % len(показать))
for р in показать:
    д = детали(р["detail_json"])
    код = д.get("status") or д.get("code") or д.get("dsn_status") or ""
    вид = д.get("bounce_type") or д.get("type") or ""
    текст = (д.get("diagnostic") or д.get("diagnostic_code")
             or д.get("reason") or д.get("snippet") or "")
    почта = str(р["email"] or "?")
    домен = почта.split("@")[-1]
    print("  %s  %-34s %-14s" % (str(р["event_ts"])[:16], почта, домен))
    print("        ящик=%-32s письмо=%s отправлено=%s"
          % (str(р["mailbox_id"] or "?")[:32], р["message_id"],
             str(р["sent_at"] or "")[:16]))
    print("        код=%-10s вид=%-10s mx=%s  %s"
          % (str(код), str(вид), str(р["mx_provider"] or "?"),
             str(р["company_name"] or "")[:30]))
    if текст:
        print("        %s" % str(текст).replace("\n", " ")[:190])

def свод(имя, ключ):
    счёт = Counter(ключ(р) for р in показать)
    print("\n=== %s ===" % имя)
    for к, н in счёт.most_common():
        print("  %-44s %d" % (str(к)[:44], н))

свод("ПО ЯЩИКУ-ОТПРАВИТЕЛЮ", lambda р: str(р["mailbox_id"] or "?"))
свод("ПО ДОМЕНУ ПОЛУЧАТЕЛЯ", lambda р: str(р["email"] or "?@?").split("@")[-1])
свод("ПО MX ПОЛУЧАТЕЛЯ", lambda р: str(р["mx_provider"] or "?"))
свод("ПО КОДУ", lambda р: str(детали(р["detail_json"]).get("status")
                             or детали(р["detail_json"]).get("code") or "?"))
свод("ПО ВИДУ", lambda р: str(детали(р["detail_json"]).get("bounce_type")
                              or детали(р["detail_json"]).get("type") or "?"))

print("\n=== ОТПРАВЛЕНО ЗА СУТКИ (для доли) ===")
for р in c.execute(
        "SELECT COUNT(*) n FROM messages WHERE status='sent' "
        "  AND substr(COALESCE(sent_at,created_at),1,10)=?", (СУТКИ,)):
    n = р["n"]
    print("  писем отправлено: %d, баунсов: %d → %.1f%%"
          % (n, len(сегодня), 100.0 * len(сегодня) / n if n else 0))

print("\n=== ЭТИ АДРЕСА ПРОВЕРЯЛИСЬ ПРОБОЙ? ===")
try:
    for р in показать:
        строки = c.execute(
            "SELECT verdict, ts FROM addr_probe WHERE email=?",
            (р["email"],)).fetchall()
        print("  %-34s %s" % (str(р["email"])[:34],
                              "; ".join("%s @ %s" % (с["verdict"], str(с["ts"])[:16])
                                        for с in строки) or "ПРОБЫ НЕ БЫЛО"))
except Exception as e:  # noqa: BLE001
    print("  addr_probe недоступна: %s" % e)
