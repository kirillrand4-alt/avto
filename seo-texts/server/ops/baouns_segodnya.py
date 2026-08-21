# -*- coding: utf-8 -*-
"""Отбивки, ПРИШЕДШИЕ сегодня: чьё письмо и когда оно уходило.

Панель в «Динамике 7 дней» считает отбивку по дню её ПРИХОДА, а письмо
могло уйти раньше - отсюда картина «отправлено 0, bounce 1».
"""
import json
import sqlite3
from datetime import datetime, timezone

сегодня = datetime.now(timezone.utc).date().isoformat()
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT e.id, e.message_id, e.event_ts, e.created_at, e.detail_json, "
    "       m.campaign_id, m.mailbox_id, m.status, m.updated_at, "
    "       r.email, r.company_name, r.inn "
    "  FROM events e LEFT JOIN messages m ON m.id=e.message_id "
    "  LEFT JOIN recipients r ON r.id=m.recipient_id "
    " WHERE e.event_type='bounce' "
    "   AND (substr(e.created_at,1,10)=? OR substr(e.event_ts,1,10)=?) "
    " ORDER BY e.id DESC", (сегодня, сегодня)).fetchall()
print(f"отбивок с датой {сегодня}: {len(ряды)}\n")
for р in ряды:
    д = {}
    try:
        д = (json.loads(р["detail_json"]) or {}).get("dsn") or {}
    except Exception:                                          # noqa: BLE001
        pass
    print(f"событие #{р['id']}  пришло {р['created_at']}  "
          f"метка события {р['event_ts']}")
    print(f"  письмо #{р['message_id']} кампания {р['campaign_id']} "
          f"ящик {р['mailbox_id']} статус письма {р['status']} "
          f"отправлено {р['updated_at']}")
    print(f"  кому: {р['email']} | {р['company_name']} | ИНН {р['inn']}")
    print(f"  код {д.get('smtp_code')} вердикт {д.get('verdict')}: "
          f"{str(д.get('diagnostic'))[:120]}")
