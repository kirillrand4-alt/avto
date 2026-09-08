# -*- coding: utf-8 -*-
"""Где искать в панели две карточки перенаправления и что мешает их увидеть."""
import json, sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ИД = (17810, 17813)
store = Store(r"C:\sender\sender.db")
группы = store.recipient_groups().get("по_id") or {}
with store._lock:
    for rid in ИД:
        р = store._conn.execute(
            "SELECT id, status, email, subject, campaign_id, recipient_id, "
            "       message_id, reason, created_at, panel_json "
            "  FROM confirm_reviews WHERE id=?", (rid,)).fetchone()
        if р is None:
            print("карточки %s нет" % rid)
            continue
        try:
            п = json.loads(р["panel_json"] or "{}")
        except Exception:                                       # noqa: BLE001
            п = {}
        м = store._conn.execute("SELECT status FROM messages WHERE id=?",
                                (int(р["message_id"] or 0),)).fetchone()
        print("=" * 70)
        print("карточка %s | %s | %s" % (р["id"], р["status"], р["email"]))
        print("   тема:        %s" % р["subject"])
        print("   кампания:    %s" % р["campaign_id"])
        print("   письмо:      %s" % (м["status"] if м else "нет"))
        print("   заведена:    %s" % р["created_at"])
        print("   направление письма: %r" % п.get("letter_division"))
        print("   группы получателя:  %s"
              % (группы.get(int(р["recipient_id"] or 0)) or "нет"))
        флаги = п.get("stop_flags") or []
        print("   стоп-флаги:  %s" % (флаги or "нет"))
        д = (п.get("actions") or {}).get("confirm_hold")
        print("   confirm_hold: %s" % д)
print("")
print("=" * 70)
print("=== ГДЕ ИХ ИСКАТЬ ===")
print("очередь сортируется по score и режется по 50: свежая карточка без")
print("паспорта уходит в хвост. Ищите по адресу через строку поиска.")
