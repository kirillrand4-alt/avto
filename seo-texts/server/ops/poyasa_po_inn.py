# -*- coding: utf-8 -*-
"""Часовой пояс получателя по коду региона в ИНН + пересчёт срока писем.

Владелец 13.10: «да, проставь пояса и пересчитай время». У 963 из 991 письма
кампании 14 в расписании recipients.tz пустой → окно считалось по Москве.
Первые две цифры российского ИНН — код региона постановки на учёт.

Что делаем:
  1) recipients.tz пустой, ИНН российский (10/12 цифр, не 00…), почта не
     .kz/.by/.uz/.kg, группа «Россия 9000» или письмо в кампании 14 →
     tz по коду региона (Москва для европейской зоны — явно);
  2) письма кампании 14 в статусе scheduled — срок заново через
     auto_send.next_slot по поясу получателя (то же, что делает панель);
  3) всё старое — в _ops/poyasa-po-inn.jsonl (fsync) для отката.

    poyasa_po_inn.py            — сухой прогон (сколько и куда)
    poyasa_po_inn.py --primenit — применить
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender import auto_send  # noqa: E402

ПРИМЕНИТЬ = "--primenit" in sys.argv
ПОЯС = {}
for коды, зона in (
        (("39",), "Europe/Kaliningrad"),
        (("63", "18"), "Europe/Samara"), (("64",), "Europe/Saratov"),
        (("73",), "Europe/Ulyanovsk"), (("30",), "Europe/Astrakhan"),
        (("34",), "Europe/Volgograd"), (("43",), "Europe/Kirov"),
        (("02", "45", "56", "59", "66", "72", "74", "86", "89"), "Asia/Yekaterinburg"),
        (("55",), "Asia/Omsk"),
        (("54",), "Asia/Novosibirsk"), (("22", "04"), "Asia/Barnaul"),
        (("42",), "Asia/Novokuznetsk"), (("70",), "Asia/Tomsk"),
        (("24", "19", "17"), "Asia/Krasnoyarsk"),
        (("38", "03"), "Asia/Irkutsk"),
        (("75",), "Asia/Chita"), (("28", "14"), "Asia/Yakutsk"),
        (("25", "27", "79"), "Asia/Vladivostok"),
        (("49",), "Asia/Magadan"), (("65",), "Asia/Sakhalin"),
        (("41",), "Asia/Kamchatka"), (("87",), "Asia/Anadyr")):
    for к in коды:
        ПОЯС[к] = зона
ЕВРОПА_МСК = {"%02d" % i for i in range(1, 100)} - set(ПОЯС) - {"00", "80", "81", "84", "85", "88", "90", "93", "94", "95", "96", "98", "99"}


def пояс_по_инн(inn):
    ц = "".join(c for c in str(inn or "") if c.isdigit())
    if len(ц) not in (10, 12) or ц.startswith("00"):
        return None
    к = ц[:2]
    return ПОЯС.get(к) or ("Europe/Moscow" if к in ЕВРОПА_МСК else None)


cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
окно = auto_send.window_from(store, cfg)
print("окно отправки: %s" % окно)
for з in set(ПОЯС.values()):
    auto_send._zone(з)  # упадёт, если зоны нет в tzdata
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
в14 = {р[0] for р in c.execute("SELECT DISTINCT recipient_id FROM messages WHERE campaign_id=14")}
правки_tz = []
for р in c.execute("SELECT id, inn, lower(email) e, extra_json FROM recipients WHERE tz IS NULL OR tz=''"):
    if str(р["e"] or "").rsplit(".", 1)[-1] in ("kz", "by", "uz", "kg"):
        continue
    if р["id"] not in в14 and "Россия 9000" not in str(р["extra_json"] or ""):
        continue
    з = пояс_по_инн(р["inn"])
    if з:
        правки_tz.append((р["id"], з))
print("пояс проставим получателям: %d; по зонам: %s"
      % (len(правки_tz), dict(Counter(з for _, з in правки_tz).most_common())))

новый_tz = dict(правки_tz)
теперь = datetime.now(timezone.utc)
перенос = []
for р in c.execute("SELECT m.id, m.recipient_id, m.scheduled_at, r.tz FROM messages m "
                   "JOIN recipients r ON r.id=m.recipient_id "
                   "WHERE m.campaign_id=14 AND m.status='scheduled'"):
    tz = новый_tz.get(р["recipient_id"]) or р["tz"]
    if not tz:
        continue
    зона = auto_send.recipient_tz_name(окно, {"tz": tz})
    срок = auto_send.next_slot(окно, зона, теперь)
    было = auto_send._parse_iso(р["scheduled_at"])
    # переносим, только если старый срок вне окна ЕГО зоны: раньше начала
    # (Калининград в 08:00 по-местному) или позже, чем можно (восток: 09:00
    # МСК = после обеда у них)
    if было is None or abs((было - срок).total_seconds()) >= 60:
        if было is None or not auto_send.within_window_now(окно, зона, было) or срок < было:
            перенос.append((р["id"], р["scheduled_at"], срок, зона))
print("писем кампании 14 перенесём: %d" % len(перенос))
print("   новые сроки (час UTC): %s" % dict(sorted(Counter(
    с.strftime("%Y-%m-%dT%H") for _, _, с, _ in перенос).items())))
print("   по зонам: %s" % dict(Counter(з for *_, з in перенос).most_common()))

if ПРИМЕНИТЬ:
    with io.open(r"C:\sender\_ops\poyasa-po-inn.jsonl", "a", encoding="utf-8") as ж:
        ж.write(json.dumps({"ts": int(time.time()), "tz_было_пусто": [i for i, _ in правки_tz],
                            "сроки_было": [(i, б) for i, б, _, _ in перенос]},
                           ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    with c:
        c.executemany("UPDATE recipients SET tz=? WHERE id=? AND (tz IS NULL OR tz='')",
                      [(з, i) for i, з in правки_tz])
        c.executemany("UPDATE messages SET scheduled_at=?, updated_at=? WHERE id=? AND status='scheduled'",
                      [(с.strftime("%Y-%m-%dT%H:%M:%S"), теперь.strftime("%Y-%m-%dT%H:%M:%S"), i)
                       for i, _, с, _ in перенос])
    print("=== ПОЯСА: ПРИМЕНЕНО (откат — _ops/poyasa-po-inn.jsonl) ===")
else:
    print("=== ПОЯСА: СУХОЙ ПРОГОН ===")
