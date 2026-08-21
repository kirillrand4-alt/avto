# -*- coding: utf-8 -*-
"""Показать отправленное письмо по адресу: текст, направление, обоснование."""
import json
import sqlite3
import sys

адрес = sys.argv[1] if len(sys.argv) > 1 else ""
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
р = c.execute(
    "SELECT id, campaign_id, inn, email, subject, body, status, "
    "       COALESCE(panel_json,'') AS pj, decided_by, decided_at "
    "  FROM confirm_reviews WHERE email=? ORDER BY id DESC LIMIT 1",
    (адрес,)).fetchone()
if р is None:
    print("карточки нет")
    raise SystemExit(0)
print(f"№{р['id']} кампания {р['campaign_id']} статус {р['status']} "
      f"решил {р['decided_by']} {str(р['decided_at'])[:19]}")
print(f"ИНН {р['inn']} | {р['email']}")
print(f"ТЕМА: {р['subject']}\n")
print(р["body"])
try:
    п = json.loads(р["pj"] or "{}")
except Exception:                                                  # noqa: BLE001
    п = {}
письмо = п.get("letter") or {}
комп = п.get("company") or {}
print("\n--- направление ---")
print("letter_division:", письмо.get("division") or п.get("letter_division"))
print("почему:", письмо.get("division_reason") or п.get("letter_division_reason"))
print("метка компании:", комп.get("division"))
print("ОКВЭД:", комп.get("okved"), "|", str(комп.get("activity") or "")[:160])
