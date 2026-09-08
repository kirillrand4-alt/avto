# -*- coding: utf-8 -*-
"""Поставить письмо АГРО-ХОРС на адрес, который назвала сама компания.

Автоответ с agro-hors@yandex.ru: «с 15 июля 2026 изменился основной адрес…
по вопросам продаж, коммерческих предложений - com.dir@agro-hors.ru… письма
на старый адрес могут остаться без ответа».

Ставим в ОЧЕРЕДЬ, а не шлём напрямую: письмо пойдёт штатным путём, с
заголовком отписки и через подтверждение оператора, как все остальные.
Старый адрес в стоп-лист не заводим - он живой, просто компания просит на
него не писать; приговором по канону считаются только «нет ящика» и «нет MX».

    python perenapravit_agro_hors.py            # вхолостую
    python perenapravit_agro_hors.py --primenit
"""
import io
import json
import os
import sys
import time
from datetime import date

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.confirm import ConfirmSend                           # noqa: E402
from sender.dtos import RecipientIn                              # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402
from imya_v_pismo import итоговое_имя                            # noqa: E402
from zona_po_innu import зона_по_inn                             # noqa: E402
import varianty_pisma as V                                       # noqa: E402

ИНН = "6316219819"
СТАРЫЙ = "agro-hors@yandex.ru"
НОВЫЙ = "com.dir@agro-hors.ru"          # «по вопросам продаж, коммерческих предложений»
ГРУППА = "Агро зерно 2026"
ИСТОЧНИК = "перенаправление по автоответу"
КАМПАНИЯ = 11
ЖУРНАЛ = r"C:\sender\_ops\agro-ochered.jsonl"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
день = date.today().isoformat()

with store._lock:
    стар = store._conn.execute(
        "SELECT id, company_name, region, extra_json, segment FROM recipients "
        " WHERE email=?", (СТАРЫЙ,)).fetchone()
    занят = store._conn.execute(
        "SELECT id FROM recipients WHERE email=?", (НОВЫЙ,)).fetchone()
if стар is None:
    print("получателя со старым адресом нет — не понимаю, кого переносить")
    raise SystemExit(1)
print("старый получатель: %s (%s)" % (стар["company_name"], СТАРЫЙ))
print("новый адрес уже в базе: %s" % ("да, id %s" % занят["id"] if занят else "нет"))

# ИМЯ БЕРЁМ ИЗ РАЗБОРА, а не чистим кавычки руками: регистр правит разбор
# моделью (ops/imena_agro), и без него в письмо уходит «АГРО-ХОРС» капсом.
имя_сыро = " ".join(str(стар["company_name"] or "").split())
разобрано = None
ИМЕНА = r"C:\sender\_ops\agro-imena.jsonl"
for _с in io.open(ИМЕНА, encoding="utf-8", errors="replace"):
    _с = _с.strip()
    if not _с:
        continue
    try:
        _z = json.loads(_с)
    except Exception:                                           # noqa: BLE001
        continue
    if " ".join(str(_z.get("сыро") or "").split()) == имя_сыро:
        разобрано = (_z.get("имя"), bool(_z.get("человек")))
        break
if разобрано is None:
    print("названия «%s» нет в разборе — не подставляю вслепую" % имя_сыро)
    raise SystemExit(1)
подл, _вид = итоговое_имя(разобрано[0], разобрано[1])
print("название в письме: %s (из разбора: %r)" % (подл, разобрано[0]))
тело = V.письмо(ИНН, подл, стар["region"])
тема = V.тема(ИНН)
try:
    extra = json.loads(стар["extra_json"] or "{}")
except Exception:                                               # noqa: BLE001
    extra = {}
extra = dict(extra)
extra["gruppy"] = [ГРУППА]
extra["osnovnoy_adres"] = СТАРЫЙ
extra["pochemu_zapasnoy"] = ("автоответ компании: с 15.07.2026 письма по "
                             "коммерческим вопросам на com.dir@agro-hors.ru, "
                             "старый адрес может остаться без ответа")

print("")
print("Тема: %s" % тема)
print("Кому: %s" % НОВЫЙ)
print("")
print(тело[:600] + ("…" if len(тело) > 600 else ""))

if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Поставить в очередь — --primenit")
    raise SystemExit(0)

р = RecipientIn(email=НОВЫЙ, domain=НОВЫЙ.split("@", 1)[1], inn=ИНН,
                company_name=стар["company_name"], segment="meyer",
                source=ИСТОЧНИК, region=стар["region"],
                tz=зона_по_inn(ИНН), extra=extra)
rid = store.upsert_recipient(р)
rec = store.get_recipient(rid)
пара = q._ensure_message(КАМПАНИЯ, rid)
mid = пара[0] if пара else None
if not mid:
    print("нет message_id: %s" % (пара[2] if пара else "?"))
    raise SystemExit(1)
письмо = {"subject": тема, "body": тело, "division": "meyer",
          "division_reason": "перенаправление по автоответу компании",
          "rounds": []}
try:
    panel = q._panel(rec, письмо, день, {})
except Exception as ex:                                         # noqa: BLE001
    panel = {"ai": False, "letter_division": "meyer"}
    print("панель не собралась: %s" % str(ex)[:90])
r = cs.submit(email=НОВЫЙ, subject=тема, body=тело, inn=ИНН,
              campaign_id=КАМПАНИЯ, recipient_id=rid, message_id=mid,
              panel=panel)
зап = {"recipient_id": rid, "inn": ИНН, "почта": НОВЫЙ,
       "имя_реестра": стар["company_name"], "имя_в_письме": подл,
       "день": день, "тема": тема, "тело": тело,
       "вместо_адреса": СТАРЫЙ,
       "review_id": getattr(r, "review_id", None),
       "статус": str(getattr(r, "status", "") or ""),
       "причина": str(getattr(r, "reason", "") or "")}
with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ф:
    ф.write(json.dumps(зап, ensure_ascii=False) + "\n")
    ф.flush()
    os.fsync(ф.fileno())
print("")
print("=" * 74)
print("=== ПЕРЕНАПРАВЛЕНИЕ ===")
print("получатель %s заведён (id %s)" % (НОВЫЙ, rid))
print("карточка очереди: %s, статус %s %s"
      % (зап["review_id"], зап["статус"], зап["причина"][:60]))
