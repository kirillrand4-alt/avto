# -*- coding: utf-8 -*-
"""Привязать потерянное входящее к получателю и завести карточку в ленте.

Универсальный: python privyazat_sobytie_0907.py <событие> <получатель> [--primenit]

Что делает: событие 'other' без привязки -> 'reply' с recipient_id, message_id
последнего нашего письма этому получателю и его campaign_id; затем карточка
через штатный leaddesk.push_warm_lead. Метку и статус берём у боевого
классификатора; вежливый отказ по правилу create_lead заводится сразу в
not_interested (в общей ленте не нужен, в своей очереди виден).

По умолчанию СУХОЙ ПРОГОН.
"""
import json
import sqlite3
import sys
from types import SimpleNamespace

sys.path.insert(0, r"C:\sender")

СОБЫТИЕ = int(sys.argv[1])
ПОЛУЧАТЕЛЬ = int(sys.argv[2])
ПРИМЕНИТЬ = "--primenit" in sys.argv

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.leaddesk import LeadDesk                              # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
путь = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(путь)

c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True, timeout=90)
c.row_factory = sqlite3.Row
соб = c.execute("SELECT * FROM events WHERE id=?", (СОБЫТИЕ,)).fetchone()
пол = c.execute("SELECT * FROM recipients WHERE id=?", (ПОЛУЧАТЕЛЬ,)).fetchone()
письма = list(c.execute(
    "SELECT id, campaign_id, status, sent_at, mailbox_id, subject FROM messages"
    " WHERE recipient_id=? AND status='sent' ORDER BY sent_at DESC",
    (ПОЛУЧАТЕЛЬ,)))
c.close()

d = json.loads(соб["detail_json"] or "{}")
h = d.get("headers") or {}
текст = " ".join(str(d.get("snippet") or "").split())
письмо = письма[0] if письма else None

# МЕТКА РУКАМИ. Классификатор проверен на заведомых текстах: «не интересно»,
# «пришлите КП», отпуск и отписку он берёт верно, а КОСВЕННЫЕ формулировки
# («планов нет», «актуален и интересен») кладёт в neutral. Поэтому метку
# можно задать ключом --metka=..., вердикт машины сохраняем рядом.
метка_ruchnaya = ""
for а in sys.argv[1:]:
    if а.startswith("--metka="):
        метка_ruchnaya = а.split("=", 1)[1]
метка_машины = ""
метка = ""
try:
    from sender.reply_classify import classify_reply                # noqa: E402
    с = classify_reply(str(h.get("Subject") or ""), текст, h)
    метка_машины = getattr(с, "kind", "") or ""
except Exception as ex:                                             # noqa: BLE001
    метка_машины = "классификатор недоступен: %s" % str(ex)[:60]
метка = метка_ruchnaya or метка_машины

# Вежливый отказ по правилу самого create_lead заводится сразу в конечный
# статус: в общей ленте он не нужен, а в своей очереди виден и сходится
# со счётчиком ответов.
статус = "not_interested" if метка == "not_interested" else "new"
тип_события = "reply_auto" if метка == "auto_reply" else "reply"

шаги = []
if ПРИМЕНИТЬ and письмо is not None:
    d["reply_kind"] = метка
    d["reply_kind_klassifikator"] = метка_машины
    d["privyazka_ruchnaya"] = {
        "kem": "ops/privyazat_sobytie_0907.py",
        "pochemu": "входящее без привязки, компания опознана по домену "
                   "отправителя",
        "recipient_id": ПОЛУЧАТЕЛЬ, "message_id": письмо["id"]}
    with store.transaction() as conn:
        conn.execute(
            "UPDATE events SET event_type=?, recipient_id=?, message_id=?,"
            " campaign_id=?, detail_json=? WHERE id=?",
            (тип_события, ПОЛУЧАТЕЛЬ, письмо["id"], письмо["campaign_id"],
             json.dumps(d, ensure_ascii=False), СОБЫТИЕ))
    шаги.append("событие %d: other -> %s, привязано к получателю %d, письму %d"
                % (СОБЫТИЕ, тип_события, ПОЛУЧАТЕЛЬ, письмо["id"]))
    отправитель = ""
    import re as _re
    м = _re.search(r"[\w.+-]+@[\w.-]+", str(h.get("From") or ""))
    if м:
        отправитель = м.group(0)
    desk = LeadDesk(store=store, config=cfg)
    кто = SimpleNamespace(id=пол["id"], email=пол["email"],
                          company_name=пол["company_name"], inn=пол["inn"])
    лид = desk.push_warm_lead(кто, None, "[%s] %s" % (метка or "neutral", текст),
                              otvetil=отправитель, status=статус)
    шаги.append("push_warm_lead -> лид %s (статус %s)" % (лид, статус))
elif ПРИМЕНИТЬ:
    шаги.append("НЕ ТРОГАЛ: этому получателю нет ни одного отправленного письма")
else:
    шаги.append("сухой прогон: ничего не меняю")

c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True, timeout=90)
c.row_factory = sqlite3.Row
после = c.execute("SELECT * FROM events WHERE id=?", (СОБЫТИЕ,)).fetchone()
лиды = list(c.execute("SELECT * FROM leads WHERE recipient_id=?",
                      (ПОЛУЧАТЕЛЬ,)))
c.close()

print("=" * 74)
print("=== ПРИВЯЗКА СОБЫТИЯ %d К ПОЛУЧАТЕЛЮ %d ===" % (СОБЫТИЕ, ПОЛУЧАТЕЛЬ))
print("режим: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("")
print("от кого:  %s" % str(h.get("From"))[:70])
print("кому:     %s   ящик события: %s"
      % (str(h.get("To"))[:40], соб["mailbox_id"]))
print("тема:     %s" % str(h.get("Subject"))[:60])
print("дата:     %s" % str(h.get("Date"))[:40])
print("текст:    %s" % текст[:400])
print("")
print("получатель %s: %s | %s | ИНН %s | направление %s"
      % (пол["id"], пол["email"], str(пол["company_name"])[:34], пол["inn"],
         пол["segment"]))
print("наши письма ему: %d" % len(письма))
for м_ in письма[:3]:
    print("   msg=%s камп=%s %s ящик=%s | %s"
          % (м_["id"], м_["campaign_id"], str(м_["sent_at"])[:19],
             м_["mailbox_id"], str(м_["subject"])[:40]))
print("")
print("метка: %s%s -> тип события %s, статус лида %s"
      % (метка, (" (классификатор давал: %s)" % метка_машины)
         if метка_ruchnaya else "", тип_события, статус))
for с_ in шаги:
    print("   " + с_)
print("")
print("событие сейчас: тип=%s получатель=%s письмо=%s кампания=%s"
      % (после["event_type"], после["recipient_id"], после["message_id"],
         после["campaign_id"]))
for л in лиды:
    print("лид %s: %s | %s | статус %s | метка %s"
          % (л["id"], л["email"], str(л["company_name"])[:34], л["status"],
             л["reply_kind"]))
if not лиды:
    print("лидов по этому получателю нет")
