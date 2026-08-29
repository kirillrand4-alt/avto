# -*- coding: utf-8 -*-
"""Свести ответ АО «ОКБ «Экситон» с его карточкой.

Мы писали 20.08 на oeksiton@bk.ru, а главный инженер ответил со своего
gi@okbexiton.ru — домен другой, поэтому привязка не сработала и письмо легло
«вне переписки». Лид завёлся, но пустой: без ИНН, без названия, без переписки.
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
БАЗА = r"C:\sender\sender.db"
ПОЛУЧАТЕЛЬ, ЛИД = 6364, 136
СОБЫТИЯ = (155308, 308536)
ТЕКСТ = ("Доброе утро!\n"
         "Вопрос компрессорного оборудования для нашей организации "
         "в настоящий момент не актуален.\n"
         "\n"
         "С уважением,\n"
         "главный инженер АО «ОКБ «Экситон»\n"
         "Новоселов Антон Владимирович\n"
         "\n"
         "(ответ пришёл 24.08 и повторно 28.08 с gi@okbexiton.ru; письмо мы "
         "отправляли 20.08 на oeksiton@bk.ru)")

from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
r = store.get_recipient(ПОЛУЧАТЕЛЬ)
print("получатель %s: %s | ИНН %s | %s"
      % (ПОЛУЧАТЕЛЬ, getattr(r, "email", "?"), getattr(r, "inn", "?"),
         getattr(r, "company_name", "?")))
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
л = c.execute("SELECT id, recipient_id, inn, company_name, email, status, "
              "       reply_kind, need FROM leads WHERE id=?", (ЛИД,)).fetchone()
print("лид %s: rid=%s инн=%s имя=%s статус=%s вид=%s"
      % (л["id"], л["recipient_id"], л["inn"], л["company_name"], л["status"],
         л["reply_kind"]))
print("   что написал сейчас: %r" % str(л["need"] or "")[:80])
for eid in СОБЫТИЯ:
    э = c.execute("SELECT id, event_type, event_ts, recipient_id FROM events "
                  " WHERE id=?", (eid,)).fetchone()
    if э:
        print("   ev=%s %s %s rid=%s" % (э["id"], э["event_type"],
                                         str(э["event_ts"])[:19], э["recipient_id"]))
c.close()

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit сведу")
    raise SystemExit(0)

with store.transaction() as conn:
    for eid in СОБЫТИЯ:
        строка = conn.execute("SELECT detail_json FROM events WHERE id=?",
                              (eid,)).fetchone()
        if not строка:
            continue
        try:
            d = json.loads(строка["detail_json"] or "{}")
        except Exception:                                          # noqa: BLE001
            d = {}
        if isinstance(d, dict):
            d["reply_kind"] = "not_interested"
            d["privyazka"] = "вручную: ответ с другого домена той же компании"
        conn.execute("UPDATE events SET event_type='reply', recipient_id=?, "
                     "       detail_json=? WHERE id=?",
                     (ПОЛУЧАТЕЛЬ, json.dumps(d, ensure_ascii=False), eid))
    n = conn.execute(
        "UPDATE leads SET recipient_id=?, inn=?, company_name=?, need=?, "
        "       reply_kind='not_interested', updated_at=? WHERE id=?",
        (ПОЛУЧАТЕЛЬ, getattr(r, "inn", None), getattr(r, "company_name", None),
         ТЕКСТ, time.strftime("%Y-%m-%dT%H:%M:%S"), ЛИД)).rowcount
print("\nлид обновлён: %d, событий привязано: %d" % (n, len(СОБЫТИЯ)))
print("\n=== переписка компании теперь ===")
for it in store.dialog_thread_company(str(getattr(r, "inn", "") or "")):
    print("   %s %s [%s] %s :: %s"
          % (it.get("direction"), str(it.get("ts"))[:19], it.get("kind"),
             it.get("email"), str(it.get("body") or "").replace("\n", " ")[:80]))
