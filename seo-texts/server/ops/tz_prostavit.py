# -*- coding: utf-8 -*-
"""Часовой пояс получателям живых писем КЦ (16) и Meyer (14), у кого его нет
(владелец 16.10: «время по получателю»). Источники по порядку: регион в карточке
(recipients.region / extra), адрес и регион в enrich.db, регион из ИНН (код субъекта),
домен .by/.kz. Найденный пояс пишем в recipients.tz и пересчитываем scheduled_at
у scheduled-писем ближайшим слотом окна в этом поясе (как кнопка «В автоотправку»).
Без --primenit — только счёт."""
import json, sqlite3, sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.regions import region_to_tz
from sender.auto_send import window_from, next_slot, recipient_tz_name
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
win = window_from(st, cfg)
print("окно:", {k: win.get(k) for k in ("tz", "start", "end", "days", "by_recipient_tz")})
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
екол = [r[1] for r in e.execute("PRAGMA table_info(companies)")]
адр_кол = [k for k in ("region", "address", "city", "legal_address", "region_name") if k in екол]
адрес = {}
if адр_кол:
    for r in e.execute("SELECT inn, %s FROM companies" % ", ".join(адр_кол)):
        адрес[str(r[0])] = " ".join(str(x) for x in r[1:] if x)
# код субъекта по первым двум цифрам ИНН -> пояс (кроме московского по умолчанию)
КОД = {"39": "Europe/Kaliningrad", "63": "Europe/Samara", "18": "Europe/Samara", "73": "Europe/Ulyanovsk",
       "64": "Europe/Saratov", "30": "Europe/Astrakhan", "34": "Europe/Volgograd", "43": "Europe/Kirov",
       "02": "Asia/Yekaterinburg", "56": "Asia/Yekaterinburg", "59": "Asia/Yekaterinburg", "66": "Asia/Yekaterinburg",
       "72": "Asia/Yekaterinburg", "74": "Asia/Yekaterinburg", "45": "Asia/Yekaterinburg", "86": "Asia/Yekaterinburg",
       "89": "Asia/Yekaterinburg", "55": "Asia/Omsk", "22": "Asia/Barnaul", "04": "Asia/Barnaul",
       "54": "Asia/Novosibirsk", "70": "Asia/Tomsk", "42": "Asia/Novokuznetsk", "24": "Asia/Krasnoyarsk",
       "19": "Asia/Krasnoyarsk", "17": "Asia/Krasnoyarsk", "38": "Asia/Irkutsk", "03": "Asia/Irkutsk",
       "75": "Asia/Chita", "28": "Asia/Yakutsk", "14": "Asia/Yakutsk", "27": "Asia/Vladivostok",
       "25": "Asia/Vladivostok", "79": "Asia/Vladivostok", "49": "Asia/Magadan", "65": "Asia/Sakhalin",
       "41": "Asia/Kamchatka", "87": "Asia/Anadyr"}
сч, пояс, изм = Counter(), Counter(), []
for rid, inn, region, ex, email, mid, mst in c.execute(
        "SELECT r.id, r.inn, r.region, r.extra_json, r.email, m.id, m.status FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        "WHERE m.status IN ('pending_review','approved','scheduled') AND m.campaign_id IN (14,16) AND (r.tz IS NULL OR r.tz='')"):
    inn = str(inn or ""); tz, ист = None, ""
    try: x = json.loads(ex or "{}")
    except ValueError: x = {}
    for кандидат, имя in ((region, "регион карточки"), (x.get("region") or x.get("city") or x.get("address"), "extra"),
                          (адрес.get(inn), "enrich")):
        tz = region_to_tz(кандидат) if кандидат else None
        if tz: ист = имя; break
    if not tz and len(inn) in (10, 12) and inn[:2] in КОД: tz, ист = КОД[inn[:2]], "код ИНН"
    if not tz and len(inn) in (10, 12): tz, ист = "Europe/Moscow", "код ИНН (Москв. зона)"
    if not tz:
        d = str(email or "").lower().rsplit(".", 1)[-1]
        if d == "by": tz, ист = "Europe/Minsk", "домен .by"
        elif d == "kz": tz, ист = "Asia/Almaty", "домен .kz"
    сч[ист or "не определить"] += 1
    if tz: пояс[tz] += 1; изм.append((rid, tz, mid, mst))
print("источник:", dict(сч)); print("пояса:", пояс.most_common(10))
if "--primenit" in sys.argv:
    now = datetime.now(timezone.utc); n = 0
    with c:
        for rid, tz, mid, mst in изм:
            c.execute("UPDATE recipients SET tz=? WHERE id=? AND (tz IS NULL OR tz='')", (tz, rid))
            if mst == "scheduled":
                слот = next_slot(win, recipient_tz_name(win, {"tz": tz}), now)
                c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'",
                          (слот.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"), mid)); n += 1
    print("пояс проставлен:", len(изм), "| время пересчитано у запланированных:", n)
