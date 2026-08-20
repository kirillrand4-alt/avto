# -*- coding: utf-8 -*-
"""Копии второму контакту: сказать в письме, что коллеге уже писали.

Владелец: «поправь имя адресата если копия это чисто копия стала».
Имени править не пришлось: в письмах обращения по имени нет вовсе, а в
базе за этими семью адресами человека тоже нет — гадать имя по логину
(evsvechnikova@ -> Свечникова?) в холодном письме нельзя, ошибка в имени
хуже её отсутствия.

Зато чисто копией они действительно стали: два письма «Гастрофабрике»
совпадают между собой на 100% и повторяют то, что 19.08 ушло на общий
адрес. Поэтому правим по сути: одна честная строка о том, что тот же
вопрос уже направлен на общий адрес. Тогда второй человек понимает, что
это не спам-веер, а дубль для верности.

Длинных тире не ставим - в письмах дефис.
"""
import sqlite3
import sys

КАТИТЬ = "--katit" in sys.argv
МЕЙЕР_СТАРОЕ = ("Если вопрос не к вам, буду благодарен за контакт коллеги - "
                "обращусь напрямую.")
МЕЙЕР_НОВОЕ = ("Тот же вопрос я направлял на общий адрес компании - пишу и "
               "вам, если эта тема ближе к вашей зоне. Если нет, буду "
               "благодарен за контакт коллеги.")
КЦ_ЯКОРЬ = ("Если тема сейчас неактуальна, буду признателен за короткий "
            "ответ, чтобы в дальнейшем вас не отвлекать.")
КЦ_НОВОЕ = ("Тот же вопрос я направлял на общий адрес компании - дублирую "
            "вам.\n\n" + КЦ_ЯКОРЬ)

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.auto_send import (next_slot, recipient_tz_name,      # noqa: E402
                              window_from)
from datetime import datetime, timezone                          # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
окно = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.id, cr.email, cr.body, cr.message_id, cr.recipient_id, "
    "       r.company_name, r.inn "
    "FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
    "WHERE cr.status='pending' ORDER BY cr.id").fetchall()

правки = []
for r in ряды:
    инн = "".join(ch for ch in str(r["inn"] or "") if ch.isdigit())
    почта = str(r["email"] or "").strip().lower()
    if not инн:
        continue
    адреса = {str(x[0] or "").lower() for x in c.execute(
        "SELECT email FROM send_log WHERE inn=?", (инн,))}
    if not адреса or почта in адреса:
        continue                       # не копия: либо первый, либо дубль
    тело = str(r["body"] or "")
    if МЕЙЕР_СТАРОЕ in тело:
        новое = тело.replace(МЕЙЕР_СТАРОЕ, МЕЙЕР_НОВОЕ)
    elif КЦ_ЯКОРЬ in тело:
        новое = тело.replace(КЦ_ЯКОРЬ, КЦ_НОВОЕ)
    else:
        print(f"  #{r['id']} концовка незнакомая - не трогаю")
        continue
    правки.append((r, новое))

print(f"копий к правке: {len(правки)}")
for r, новое in правки:
    print(f"\n#{r['id']} {str(r['company_name'])[:34]} -> {r['email']}")
    print("  стало (хвост):", новое[-330:].replace("\n", " ")[:300])

if not КАТИТЬ:
    print("\nсухой прогон. Катить - --katit")
    raise SystemExit(0)

поправлено = одобрено = 0
for r, новое in правки:
    try:
        store.confirm_update_letter(int(r["id"]), body=новое)
        поправлено += 1
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{r['id']} текст не записался: {str(ex)[:90]}")
        continue
    try:
        ок = store.confirm_decide(int(r["id"]), status="approved",
                                  decided_by="разбор копий 20.08")
        if ок is False:
            continue
        одобрено += 1
        rec = store.get_recipient(r["recipient_id"])
        if r["message_id"] and rec is not None:
            store.reschedule_message(
                int(r["message_id"]),
                next_slot(окно, recipient_tz_name(окно, rec), сейчас))
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{r['id']} не одобрилось: {str(ex)[:90]}")
print(f"\nпоправлено: {поправлено} | одобрено в отправку: {одобрено}")
