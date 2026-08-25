# -*- coding: utf-8 -*-
"""Ночная сверка: ответ без карточки — заводим карточку.

ЗАЧЕМ. 25.08 нашлось пятнадцать ответов клиентов, не попавших в ленту.
Тринадцать объяснились правилом «вежливый отказ — не лид», снятым 24.08.
Два — не объяснились ничем: заголовки целы, получатель известен, в тот же
день карточки заводились. Раз причина не найдена, ставим страховку: любая
будущая дыра, чем бы она ни была вызвана, закроется за сутки сама.

ЧЕМ ЗАВОДИМ. Тем же LeadDesk.push_warm_lead, что зовёт сторож: своя
склейка (по ветке, иначе по адресу), свой срок реакции, свой разбор
пометок. Рукой в таблицу нельзя — карточка выйдет не такой, как все.

ЧЕГО НЕ ДЕЛАЕМ. Не привязываем к компании наугад: ответ без recipient_id
только считаем и показываем в журнале. Ошибиться компанией хуже, чем
оставить карточку ненайденной.

БЕЗОПАСНОСТЬ ПОВТОРА. Склейка идёт по ключу lead:<ветка|адрес>, повторный
прогон карточек не задваивает. Свои ошибки глушим и выходим нулём: сверка
не смеет ронять расписание.

    python nochnaya_sverka_lidov.py            # сухой прогон, ничего не пишет
    python nochnaya_sverka_lidov.py primenit   # завести найденное
    python nochnaya_sverka_lidov.py primenit dney=30
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
import traceback

БАЗА = r"C:\sender\sender.db"
ЖУРНАЛ = r"C:\sender\_ops\sverka-lidov.jsonl"
ДНЕЙ = 7
ДЕЛАТЬ = "primenit" in sys.argv[1:]
for а in sys.argv[1:]:
    if а.startswith("dney="):
        try:
            ДНЕЙ = max(1, int(а.split("=", 1)[1]))
        except ValueError:
            pass


def записать(строка):
    """Durable: итог прогона ложится на диск сразу, с fsync."""
    try:
        os.makedirs(os.path.dirname(ЖУРНАЛ), exist_ok=True)
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ф:
            ф.write(json.dumps(строка, ensure_ascii=False) + "\n")
            ф.flush()
            os.fsync(ф.fileno())
    except Exception:  # noqa: BLE001
        traceback.print_exc()


# Машинная почта, которую в ленту тащить незачем: агрегированные отчёты
# приходят от каждого крупного почтовика раз в сутки, отчёт о недоставке
# разбирает свой обработчик, письмо маяка — наше собственное.
_МАШИННОЕ = re.compile(
    r"dmarc|aggregate report|delivery-status|mail delivery|postmaster|"
    r"undelivered|отчёт о недоставке", re.I)
_КИРИЛЛИЦА = re.compile(r"[а-яё]{4}", re.I)
# Служебные отправители: уведомления почтовиков о входе в аккаунт, роботы
# CRM, отчёты DMARC (приходят zip-вложением, в тексте одна двоичная каша).
# Их в ленту тащить незачем: человек им не писал и отвечать некому.
_СЛУЖЕБНЫЙ = re.compile(
    r"^(no-?reply|noreply|postmaster|mailer-daemon|maildaemon|security|"
    r"notify|notification|dmarc|robot|bot|info@id)", re.I)
_СЛУЖЕБНЫЙ_ДОМЕН = re.compile(
    r"(^|\.)(id\.yandex\.ru|id\.mail\.ru|bitrix24\.ru|google\.com)$", re.I)


def человеческое(текст: str, адрес: str = "") -> bool:
    """Похоже ли «прочее» входящее на письмо живого человека.

    Ответ клиента не всегда приходит веткой: 25.08 «ТЭКО» ответил НОВЫМ
    письмом с личного gmail и темой «Ооо ТЭКО» — сторож не нашёл ни
    In-Reply-To, ни получателя, письмо легло в «other» и в ленту не попало.
    А ответ деловой: «компрессоры мы продаём, если есть интерес по выкупу —
    пишите».
    """
    лок, _, дом = str(адрес or "").partition("@")
    if лок and _СЛУЖЕБНЫЙ.match(лок):
        return False
    if дом and _СЛУЖЕБНЫЙ_ДОМЕН.search(дом):
        return False
    т = str(текст or "")
    if not т.strip() or т.lstrip().startswith("PK"):
        return False          # zip-вложение отчёта, а не письмо
    if _МАШИННОЕ.search(т):
        return False
    return bool(_КИРИЛЛИЦА.search(т))


def найти(c):
    """Ответы за окно, у которых нет карточки ни по получателю, ни по адресу."""
    есть = set()
    for р in c.execute("SELECT recipient_id, thread_id, email FROM leads"):
        if р["recipient_id"]:
            есть.add(("rid", int(р["recipient_id"])))
        if р["thread_id"]:
            есть.add(("тред", str(р["thread_id"])))
        if р["email"]:
            есть.add(("почта", str(р["email"]).strip().lower()))
    найдено = []
    for р in c.execute(
            "SELECT ев.id, ев.event_ts, ев.event_type, ев.recipient_id, "
            "       ев.detail_json FROM events ев "
            " WHERE ев.event_type IN ('reply','reply_auto','other') "
            "   AND ев.event_ts >= datetime('now', ?) ORDER BY ев.id",
            ("-%d days" % ДНЕЙ,)):
        try:
            d = json.loads(р["detail_json"] or "{}")
        except Exception:  # noqa: BLE001
            d = {}
        з = d.get("headers") if isinstance(d.get("headers"), dict) else {}
        откуда = str(з.get("From") or "")
        адрес = откуда.split("<")[-1].strip("<> ").lower() if "@" in откуда else ""
        з = d.get("headers") if isinstance(d.get("headers"), dict) else {}
        откуда = str(з.get("From") or "")
        адрес = откуда.split("<")[-1].strip("<> ").lower() if "@" in откуда else ""
        текст = " ".join(str(d.get("snippet") or "").split())
        if р["event_type"] == "other" and not человеческое(текст, адрес):
            continue          # отчёт почтовика, а не ответ
        rid = р["recipient_id"]
        if rid and ("rid", int(rid)) in есть:
            continue
        if адрес and ("почта", адрес) in есть:
            continue
        найдено.append({
            "событие": р["id"], "когда": р["event_ts"], "тип": р["event_type"],
            "получатель": rid, "адрес": адрес,
            "метка": d.get("reply_kind") or "",
            "текст": текст[:600]})
    return найдено


def main():
    c = sqlite3.connect(БАЗА, timeout=30)
    c.row_factory = sqlite3.Row
    найдено = найти(c)
    без_хозяина = [н for н in найдено if not н["получатель"]]
    print("окно %d дн., ответов без карточки: %d (из них без получателя: %d)"
          % (ДНЕЙ, len(найдено), len(без_хозяина)))
    for н in найдено:
        print("   #%-7s %s %-9s %-26s %s"
              % (н["событие"], str(н["когда"])[:16], н["тип"],
                 (н["адрес"] or "—")[:26], н["текст"][:44]))
    if not ДЕЛАТЬ:
        print("\nсухой прогон. Завести — primenit")
        return
    if not найдено:
        записать({"этап": "сверка", "окно_дней": ДНЕЙ, "найдено": 0,
                  "заведено": 0, "ts": time.time()})
        return

    sys.path.insert(0, r"C:\sender")
    from sender.config import Config      # noqa: E402
    from sender.leaddesk import LeadDesk  # noqa: E402
    from sender.store import Store        # noqa: E402
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(БАЗА)
    десk = LeadDesk(cfg, store)
    заведено = пропущено = 0
    for н in найдено:
        рек = None
        if н["получатель"]:
            try:
                рек = store.get_recipient(int(н["получатель"]))
            except Exception:  # noqa: BLE001
                рек = None
        if рек is None and not н["адрес"]:
            пропущено += 1
            continue
        метка = н["метка"] or {"reply_auto": "auto_reply",
                               "other": "вне переписки"}.get(н["тип"], "reply")
        try:
            lid = десk.push_warm_lead(рек, "", "[%s] %s" % (метка, н["текст"]),
                                      otvetil=н["адрес"] or None)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            lid = None
        if lid:
            заведено += 1
            н["карточка"] = lid
        else:
            пропущено += 1
    записать({"этап": "сверка", "окно_дней": ДНЕЙ, "найдено": len(найдено),
              "заведено": заведено, "пропущено": пропущено,
              "без_получателя": len(без_хозяина),
              "события": [н["событие"] for н in найдено], "ts": time.time()})
    print("\nзаведено карточек: %d, пропущено: %d" % (заведено, пропущено))


try:
    main()
except Exception:  # noqa: BLE001 - сверка не смеет ронять расписание
    traceback.print_exc()
    записать({"этап": "сбой", "ошибка": traceback.format_exc()[-800:],
              "ts": time.time()})
