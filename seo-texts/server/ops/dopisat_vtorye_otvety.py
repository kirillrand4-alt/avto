# -*- coding: utf-8 -*-
"""Догнать карточки лидов вторыми и третьими ответами, которые не доехали.

Пока карточка «уже была», повторный ответ в неё не писался: у «Росткрана»
так потерялся телефон механика, и лид пролежал шесть дней. Правка в
store.create_lead это чинит на будущее — этим прогоном догоняем прошлое.

Идём тем же путём, что сторож: LeadDesk.push_warm_lead с текстом ответа.
Он сам решит, дописывать ли (повтор того же текста не двоит), поднять ли
метку и поставить ли телефон.

ВАЖНО — ветку письма (thread_id) передаём ту же, что у карточки. Ключ
склейки строится как ``lead:<ветка>``, а без ветки — ``lead:<почта>``; с
пустой веткой push_warm_lead завёл бы РЯДОМ новую карточку вместо дописки
в старую (так и вышло на первом прогоне 25.08, карточки 143/144/147).

    pl_run.py dopisat_vtorye_otvety.py                  # вхолостую
    pl_run.py dopisat_vtorye_otvety.py primenit         # дописать
    pl_run.py dopisat_vtorye_otvety.py udalit=143,144   # снять дубли
"""
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config      # noqa: E402
from sender.leaddesk import LeadDesk  # noqa: E402
from sender.store import Store        # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
УДАЛИТЬ = [int(x) for a in sys.argv[1:] if a.startswith("udalit=")
           for x in a.split("=", 1)[1].split(",") if x.strip()]
БАЗА = r"C:\sender\sender.db"
# Последние семь цифр берём поодиночке: люди разбивают номер как попало
# («+7 909 7865 379» у механика «Росткрана» — 3-4-3, а не 3-3-2-2).
ТЕЛЕФОН = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*(?:\d[\s\-]*){7}")

c = sqlite3.connect(БАЗА, timeout=30)
c.row_factory = sqlite3.Row
карточки = c.execute(
    "SELECT id, recipient_id, email, company_name, phone, reply_kind, "
    "       COALESCE(thread_id,'') thread_id, COALESCE(need,'') need FROM leads "
    " WHERE recipient_id IS NOT NULL").fetchall()
print("карточек с получателем: %d" % len(карточки))

к_дописке = []
к_телефону = []
for к in карточки:
    ответы = c.execute(
        "SELECT id, event_ts, event_type, detail_json FROM events "
        " WHERE recipient_id=? AND event_type IN ('reply','reply_auto') "
        " ORDER BY event_ts", (к["recipient_id"],)).fetchall()
    if len(ответы) < 2:
        continue
    for о in ответы:
        d = json.loads(о["detail_json"] or "{}")
        т = " ".join(str(d.get("snippet") or "").split())
        if not т:
            continue
        # Кусок в 60 знаков: сравнивать целиком нельзя — в карточке текст
        # обрезан, а в событии он полный.
        тел = ТЕЛЕФОН.search(т)
        if тел and not (к["phone"] or "").strip():
            к_телефону.append({"карточка": к["id"], "когда": о["event_ts"],
                               "телефон": " ".join(тел.group(0).split())})
        if т[:60] and т[:60] in к["need"]:
            continue
        к_дописке.append({"карточка": к["id"], "компания": к["company_name"],
                          "почта": к["email"], "ветка": к["thread_id"],
                          "получатель": к["recipient_id"], "событие": о["id"],
                          "когда": о["event_ts"], "метка": d.get("reply_kind"),
                          "телефон": тел.group(0) if тел else None,
                          "текст": т})

if УДАЛИТЬ:
    for lid in УДАЛИТЬ:
        r = c.execute("SELECT recipient_id, dedup_key FROM leads WHERE id=?",
                      (lid,)).fetchone()
        if r is None:
            print("дубль #%s — уже нет" % lid)
            continue
        c.execute("DELETE FROM leads WHERE id=?", (lid,))
        print("снят дубль #%s (получатель %s, ключ %s)"
              % (lid, r["recipient_id"], r["dedup_key"]))
    c.commit()

print("ответов, не доехавших до карточек: %d" % len(к_дописке))
for з in к_дописке[:12]:
    print("   карточка #%-4s %-28s %s%s"
          % (з["карточка"], str(з["компания"] or "")[:28], str(з["когда"])[:16],
             (" | ТЕЛЕФОН " + з["телефон"]) if з["телефон"] else ""))
    print("        %s" % з["текст"][:110])

if not ДЕЛАТЬ:
    print("\nвхолостую. Дописать — primenit")
    raise SystemExit(0)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(БАЗА)
десk = LeadDesk(cfg, store)
дописано = 0
пропущено = 0
for з in sorted(к_дописке, key=lambda x: str(x["когда"])):
    if not з["ветка"]:
        # Без ветки склейка пойдёт по почте и заведёт новую карточку —
        # это не дописка, а дубль. Лучше пропустить и сказать вслух.
        пропущено += 1
        print("   #%s пропуск: у карточки нет ветки" % з["карточка"])
        continue
    рек = store.get_recipient(int(з["получатель"]))
    if рек is None:
        continue
    метки = [з["метка"] or "reply"]
    if з["телефон"]:
        метки.append("тел " + з["телефон"])
    if десk.push_warm_lead(рек, з["ветка"],
                           "[%s] %s" % (", ".join(метки), з["текст"]),
                           otvetil=з["почта"]):
        дописано += 1
print("\nдописано ответов: %d, пропущено без ветки: %d" % (дописано, пропущено))

# Телефон, который нашёлся в ответе, а в карточке пусто. Дописку текста
# такой ответ уже не даст (текст на месте), а поля телефона всё равно нет —
# продавец не увидит, кому звонить. Заполняем только пустое, чужое не трём.
телефонов = 0
for з in sorted(к_телефону, key=lambda x: str(x["когда"])):
    cur = c.execute("SELECT COALESCE(phone,'') FROM leads WHERE id=?",
                    (з["карточка"],)).fetchone()
    if cur is None or cur[0].strip():
        continue
    c.execute("UPDATE leads SET phone=?, updated_at=? WHERE id=?",
              (з["телефон"], datetime.now(timezone.utc).isoformat(), з["карточка"]))
    телефонов += 1
    print("   телефон в карточку #%s: %s" % (з["карточка"], з["телефон"]))
c.commit()
print("проставлено телефонов: %d" % телефонов)
