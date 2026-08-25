# -*- coding: utf-8 -*-
"""Завести карточки тем ответам клиентов, которые их не получили.

ПОЧЕМУ ПОТЕРЯЛИСЬ. Карточка заводилась только при непустом thread_id, а
корпоративные почтовики режут References — ветки нет, и живой ответ не
показывался никому. Сверка 25.08: 129 ответов против 112 карточек.

Заводим не своей рукой в таблицу, а тем же LeadDesk.push_warm_lead, что
зовёт сторож: у него своя склейка (по ветке, иначе по адресу), свой SLA и
свой разбор пометок. Иначе карточка получится не такой, как все.

    pl_run.py vernut_poteryashek.py            # вхолостую
    pl_run.py vernut_poteryashek.py primenit   # завести
"""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config        # noqa: E402
from sender.leaddesk import LeadDesk    # noqa: E402
from sender.store import Store          # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
БАЗА = r"C:\sender\sender.db"

c = sqlite3.connect(БАЗА, timeout=30)
c.row_factory = sqlite3.Row
есть_лид = set()
for р in c.execute("SELECT recipient_id, thread_id, email FROM leads"):
    if р["recipient_id"]:
        есть_лид.add(("rid", int(р["recipient_id"])))
    if р["thread_id"]:
        есть_лид.add(("тред", str(р["thread_id"])))
    if р["email"]:
        есть_лид.add(("почта", str(р["email"]).strip().lower()))

def адрес_из_заголовка(заголовки):
    откуда = str((заголовки or {}).get("From") or "")
    if "@" not in откуда:
        return ""
    return откуда.split("<")[-1].strip("<> ").lower()


потеряшки = []
for р in c.execute(
        "SELECT ев.id, ев.event_ts, ев.event_type, ев.recipient_id, "
        "       ев.detail_json, r.email, r.company_name "
        "  FROM events ев LEFT JOIN recipients r ON r.id=ев.recipient_id "
        " WHERE ев.event_type IN ('reply','reply_auto') ORDER BY ев.id"):
    try:
        d = json.loads(р["detail_json"] or "{}")
    except Exception:  # noqa: BLE001
        d = {}
    rid = р["recipient_id"]
    заголовки = d.get("headers") if isinstance(d.get("headers"), dict) else {}
    if not rid:
        # Хозяина ищем по ветке: у ответа в In-Reply-To/References лежит
        # Message-ID НАШЕГО письма, а по нему messages отдают получателя.
        цепочка = [str(d.get("in_reply_to_hdr") or "")]
        цепочка += str(d.get("references") or "").split()
        цепочка += [str(заголовки.get("In-Reply-To") or "")]
        for mid in [м.strip() for м in цепочка if м and м.strip()]:
            стр = c.execute("SELECT recipient_id FROM messages "
                            " WHERE rfc_message_id=?", (mid,)).fetchone()
            if стр and стр["recipient_id"]:
                rid = int(стр["recipient_id"])
                break
    адрес = адрес_из_заголовка(заголовки)
    if not rid and адрес_из_заголовка(заголовки):
        # Последняя попытка: человек ответил с того же адреса, на который
        # писали. Тогда компания в базе есть, просто событие не привязалось.
        стр = c.execute("SELECT id FROM recipients WHERE LOWER(email)=?",
                        (адрес_из_заголовка(заголовки),)).fetchone()
        if стр:
            rid = int(стр["id"])
    if rid and ("rid", int(rid)) in есть_лид:
        continue
    if адрес and ("почта", адрес) in есть_лид:
        continue
    потеряшки.append({"id": р["id"], "ts": р["event_ts"], "тип": р["event_type"],
                      "rid": rid, "почта": адрес or (р["email"] or ""),
                      "компания": р["company_name"],
                      "метка": d.get("reply_kind") or "",
                      "текст": " ".join(str(d.get("snippet") or "").split())[:600]})

print("=== ОТВЕТОВ БЕЗ КАРТОЧКИ: %d ===" % len(потеряшки))
без_хозяина = [п for п in потеряшки if not п["rid"]]
for п in потеряшки:
    print("   #%-7s %s %-9s %-28s %-26s %s"
          % (п["id"], str(п["ts"])[:16], п["тип"],
             str(п["компания"] or "—")[:28], str(п["почта"] or "—")[:26],
             п["текст"][:44]))
print("\nбез привязки к компании (карточку заводить некому): %d" % len(без_хозяина))

if not ДЕЛАТЬ:
    print("\nвхолостую. Завести — primenit")
    raise SystemExit(0)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(БАЗА)
десk = LeadDesk(cfg, store)
заведено = пропущено = 0
for п in потеряшки:
    if not п["rid"]:
        пропущено += 1
        continue
    рек = store.get_recipient(int(п["rid"]))
    if рек is None:
        пропущено += 1
        continue
    метка = п["метка"] or ("auto_reply" if п["тип"] == "reply_auto" else "reply")
    сниппет = "[%s] %s" % (метка, п["текст"])
    lid = десk.push_warm_lead(рек, "", сниппет, otvetil=п["почта"] or None)
    if lid:
        заведено += 1
    else:
        пропущено += 1
print("\nзаведено карточек: %d, пропущено: %d" % (заведено, пропущено))
print("карточек в ленте теперь: %d"
      % sqlite3.connect(БАЗА).execute("SELECT COUNT(*) FROM leads").fetchone()[0])
