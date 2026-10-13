# -*- coding: utf-8 -*-
"""Обращение по имени в письмах кампании 14: у кого имя есть и поздоровались ли.

Владелец 13.10: «проверь, используется ли обращение по имени к тем, у кого
оно написано». Имя может лежать в recipients.contact_name и в extra.fio
(книги паспортов: «Письмо: кому (ФИО)»).
"""
import json
import re
import sqlite3
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender import ai_letter as al  # noqa: E402

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
ПРИВ = re.compile(r"^\s*(Добрый день|Здравствуйте|Доброе утро)\s*,\s*([^!\n]{2,40})!", re.M)
св = Counter()
примеры = {"имя в fio, нет в contact_name": [], "имя есть, без обращения": [], "по имени": []}
for р in c.execute("SELECT m.id, m.status, m.body_rendered, cr.body AS cr_body, r.contact_name, "
                   "r.extra_json, lower(r.email) e FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                   "LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
                   "WHERE m.campaign_id=14 AND m.status IN ('scheduled','pending_review','sent')"):
    try:
        ex = json.loads(р["extra_json"] or "{}")
    except Exception:  # noqa: BLE001
        ex = {}
    тело = р["body_rendered"] or р["cr_body"] or ""
    кн = (р["contact_name"] or "").strip()
    fio = str(ex.get("fio") or "").strip()
    м = ПРИВ.search(тело[:300])
    по_имени = bool(м)
    св["писем"] += 1
    св["contact_name есть"] += bool(кн)
    св["fio из книги есть"] += bool(fio)
    св["fio есть, contact_name пуст"] += bool(fio and not кн)
    св["полное имя (ФИО) где-то есть"] += bool(al._polnoe_imya(кн or fio))
    св["поздоровались по имени"] += по_имени
    _роль = str(ex.get("role") or "").strip().lower()
    _годно = bool(кн and al._polnoe_imya(кн) and al._imya_soglasuetsya_s_yashchikom(кн, р["e"])
                  and _роль not in ("приёмная", "общий", "бухгалтерия"))
    if _годно and not по_имени:
        св["теперь было бы по имени: %s" % р["status"]] += 1
    if fio and not кн and len(примеры["имя в fio, нет в contact_name"]) < 5:
        примеры["имя в fio, нет в contact_name"].append("%s <%s> должн. %s" % (fio, р["e"], ex.get("dolzhnost")))
    if (кн or fio) and not по_имени and len(примеры["имя есть, без обращения"]) < 5:
        примеры["имя есть, без обращения"].append("%s <%s>: %s" % (кн or fio, р["e"], тело[:60].replace("\n", " ")))
    if по_имени and len(примеры["по имени"]) < 5:
        примеры["по имени"].append("%s <%s>: %s" % (кн or fio, р["e"], м.group(0)[:60]))
for к, v in св.items():
    print("   %-34s %d" % (к, v))
for к, сп in примеры.items():
    print("--- %s ---" % к)
    for s in сп:
        print("   " + s)
print("=== ИМЯ В ПИСЬМАХ ===")
