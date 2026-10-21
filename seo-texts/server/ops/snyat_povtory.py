# -*- coding: utf-8 -*-
"""Снять с подтверждения карточки с флагом повтора (recent_contact: контакт
<30 дней тем же направлением) — владелец 21.10: «сними их». Карточка и письмо
-> skipped с причиной; журнал _ops/snyat-povtory.jsonl. Плюс печать окна
повтора из конфига (почему заслон генерации их пропустил)."""
import io
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
print("confirm.recent_contact_days =", cfg.get("confirm.recent_contact_days", "нет (по умолчанию 90)"),
      "| company_contacts_per_period =", cfg.get("confirm.company_contacts_per_period", "нет"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = time.strftime("%Y-%m-%dT%H:%M:%S")
ряды = []
for rid, mid, em, pj in c.execute("SELECT id, message_id, email, panel_json FROM confirm_reviews WHERE status='pending'"):
    p = json.loads(pj or "{}")
    if any(isinstance(f, dict) and f.get("code") == "recent_contact" for f in p.get("stop_flags") or []):
        ряды.append((rid, mid, em))
print("карточек с флагом повтора:", len(ряды))
if "--primenit" in sys.argv:
    with c, io.open(r"C:\sender\_ops\snyat-povtory.jsonl", "a", encoding="utf-8") as ж:
        for rid, mid, em in ряды:
            c.execute("UPDATE confirm_reviews SET status='skipped', updated_at=? WHERE id=? AND status='pending'", (т, rid))
            if mid:
                c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status='pending_review'",
                          ("повтор <30 дней тем же направлением (владелец 21.10)", т, mid))
            ж.write(json.dumps({"review": rid, "message": mid, "email": em, "ts": т}, ensure_ascii=False) + "\n")
    print("СНЯТО:", len(ряды))
