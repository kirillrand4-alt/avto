# -*- coding: utf-8 -*-
"""Точный ответ: от кого пришло письмо «Прошу предложения присылать мне».

Прошлый прогон утонул в служебных письмах Яндекса и обрезался по объёму.
Здесь печатаем ТОЛЬКО совпадения по тексту и только суть.
"""
import json
import sqlite3

ИСКОМОЕ = "предложения присылать"
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT e.id, e.event_type, e.mailbox_id, "
    "       substr(COALESCE(e.event_ts,e.created_at),1,19) когда, "
    "       COALESCE(e.detail_json,'') dj, r.email, r.company_name, r.inn "
    "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
    " WHERE lower(COALESCE(e.detail_json,'')) LIKE ? ORDER BY e.id DESC",
    (f"%{ИСКОМОЕ}%",)).fetchall()
print(f"совпадений по тексту: {len(ряды)}\n")
for р in ряды:
    try:
        д = json.loads(р["dj"] or "{}")
    except Exception:                                              # noqa: BLE001
        д = {}
    заг = д.get("headers") if isinstance(д.get("headers"), dict) else {}
    тело = str(д.get("snippet") or д.get("body") or "")
    print(f"#{р['id']} {р['event_type']} {р['когда']}")
    print(f"  ОТ        : {заг.get('From') or д.get('from_addr') or '?'}")
    print(f"  Reply-To  : {заг.get('Reply-To') or '-'}")
    print(f"  КОМУ      : {заг.get('To') or '?'}")
    print(f"  наш ящик  : {р['mailbox_id'] or '?'}")
    print(f"  тема      : {str(заг.get('Subject') or '')[:90]}")
    print(f"  компания  : {р['company_name'] or '?'} / {р['email'] or '?'} "
          f"/ ИНН {р['inn'] or '?'}")
    куда = тело.lower().find(ИСКОМОЕ)
    if куда >= 0:
        print(f"  фрагмент  : ...{тело[max(0, куда-160):куда+220].strip()}...")
    print()
