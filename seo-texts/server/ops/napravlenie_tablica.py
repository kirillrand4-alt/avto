# -*- coding: utf-8 -*-
"""Таблица направлений по сегодняшним отправленным письмам.

Показываем то, что видит владелец в панели (значок направления), рядом с
тем, из чего направление сосчитано: метка базы, ОКВЭД, обоснование цепочки.
Расхождение «письмо vs кампания» уже проверено - его нет, значит смотреть
надо на смысл: тому ли направлению отдали компанию.
"""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
строки = c.execute(
    "SELECT cr.id, cr.campaign_id, cr.email, cr.subject, cr.decided_by, "
    "       COALESCE(cr.panel_json,'') AS pj "
    "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
    " WHERE m.status='sent' AND substr(m.updated_at,1,10)='2026-08-21' "
    " ORDER BY m.updated_at DESC"
).fetchall()
print(f"отправлено сегодня: {len(строки)}\n")
for р in строки:
    try:
        п = json.loads(р["pj"] or "{}")
    except Exception:                                             # noqa: BLE001
        п = {}
    L = п.get("letter") or {}
    K = п.get("company") or {}
    д = str(L.get("division") or "?")
    почему = str(L.get("division_reason") or "?")
    цепь = str(L.get("division_why") or (п.get("extra") or {}).get("_напр_почему") or "")
    имя = str(K.get("name") or K.get("company") or "")[:38]
    оквэд = str(K.get("okved") or K.get("okved_name") or "")[:46]
    метка = str(K.get("division") or "")
    камп = int(р["campaign_id"] or 0)
    print(f"№{р['id']:<5} {д:<5} камп{камп:<3} метка={метка or '-':<7} "
          f"{имя}")
    print(f"        ОКВЭД: {оквэд}")
    print(f"        тема:  {str(р['subject'])[:72]}")
    print(f"        почему={почему} цепь={цепь or '-'} решил={р['decided_by']}")
