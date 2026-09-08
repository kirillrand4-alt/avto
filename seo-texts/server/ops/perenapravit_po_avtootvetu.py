# -*- coding: utf-8 -*-
"""Переставить письмо на адрес, который компания назвала в автоответе.

Автоответы такого рода идут потоком («адрес изменён на …», «письма по
коммерческим вопросам - на …»), и обрабатывать их надо одинаково, а не
писать скрипт под каждую компанию.

Ставим в ОЧЕРЕДЬ, а не шлём напрямую: письмо пойдёт штатным путём, с
заголовком отписки и через подтверждение. Старый адрес в стоп-лист не
заводим - он живой, просто компания просит на него не писать; приговором по
канону считаются только «нет ящика» и «нет MX».

    python perenapravit_po_avtootvetu.py инн=6117003702 адрес=akhanov@balabinskoe.ru
    python perenapravit_po_avtootvetu.py инн=... адрес=... --primenit
    ... --otpravit    # ещё и подтвердить отправку (личное решение владельца)
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

ИНН = НОВЫЙ = ""
for _а in sys.argv[1:]:
    if _а.startswith(("инн=", "inn=")):
        ИНН = "".join(c for c in _а.split("=", 1)[1] if c.isdigit())
    elif _а.startswith(("адрес=", "adres=", "email=")):
        НОВЫЙ = _а.split("=", 1)[1].strip().lower()
if not (ИНН and НОВЫЙ):
    print("нужны инн=... и адрес=...")
    raise SystemExit(2)
ГРУППА = "Агро зерно 2026"
ИСТОЧНИК = "перенаправление по автоответу"
ОТПРАВИТЬ = "--otpravit" in sys.argv
КАМПАНИЯ = 11
ЖУРНАЛ = r"C:\sender\_ops\agro-ochered.jsonl"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
день = date.today().isoformat()

# Старого получателя ищем по ИНН: адрес в автоответе меняется, а компания та же.
with store._lock:
    стар = store._conn.execute(
        "SELECT id, email, company_name, region, extra_json, segment "
        "  FROM recipients WHERE inn=? ORDER BY id LIMIT 1", (ИНН,)).fetchone()
    занят = store._conn.execute(
        "SELECT id FROM recipients WHERE email=?", (НОВЫЙ,)).fetchone()
if стар is None:
    print("получателя с ИНН %s в базе нет — не понимаю, кого переносить" % ИНН)
    raise SystemExit(1)
СТАРЫЙ = str(стар["email"])
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
extra["pochemu_zapasnoy"] = ("автоответ компании: писать на %s вместо %s"
                             % (НОВЫЙ, СТАРЫЙ))

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
итог_отправки = ""
if ОТПРАВИТЬ and зап["статус"] == "pending" and зап["review_id"]:
    # Личное решение владельца по КОНКРЕТНОМУ письму: «протолкни». Это тот же
    # путь, что нажатие «Отправить» в панели, и он же пишется в аудит.
    try:
        ушло = cs.approve(int(зап["review_id"]),
                          operator="владелец (перенаправление по автоответу)")
        итог_отправки = "approve вернул %s" % ушло
    except Exception as ex:                                     # noqa: BLE001
        итог_отправки = "НЕ УШЛО: %s: %s" % (type(ex).__name__, str(ex)[:130])
print("")
print("=" * 74)
print("=== ПЕРЕНАПРАВЛЕНИЕ ===")
print("компания: %s (ИНН %s)" % (стар["company_name"], ИНН))
print("было %s → стало %s" % (СТАРЫЙ, НОВЫЙ))
print("получатель заведён (id %s)" % rid)
print("карточка очереди: %s, статус %s %s"
      % (зап["review_id"], зап["статус"], зап["причина"][:60]))
if ОТПРАВИТЬ:
    print("отправка: %s" % итог_отправки)
