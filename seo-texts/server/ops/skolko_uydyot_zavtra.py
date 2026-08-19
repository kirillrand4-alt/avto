# -*- coding: utf-8 -*-
"""Сколько писем уйдёт завтра и прошли ли их адреса все проверки.

Владелец: «у всех почт убедись что прошли все проверки из тех что отправятся
завтра» + «напиши число сколько завтра мейер/кц отправятся».

Отправится НЕ вся очередь: потолок дня считается рампом ящиков, и если
одобренных больше ёмкости — остаток переедет. Поэтому считаем оба числа:
что готово и что физически уедет.

Проверки адреса, каждая своим заслоном:
  * приговор пробы (нет ящика / нет MX) — письмо не дойдёт;
  * стоп-лист (suppression) — отписка или жалоба;
  * свежий контакт (<90 дней) — писали недавно;
  * формат адреса и наличие MX у домена;
  * заглушка (info@, mail@ без домена и прочее) — фильтр ловушек.
"""
import re
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.company_card import CompanyCards                     # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.confirm import ConfirmSend                           # noqa: E402
from sender.gates import Gates                                   # noqa: E402
from sender.sender import Sender                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=True,
             cards=CompanyCards(
                 index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                 enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "")
                 or None))
now = datetime.now(timezone.utc)

# ---- ёмкость завтра ------------------------------------------------------ #
ёмкость = Counter()
for mb in cfg.mailboxes():
    div = str(getattr(mb, "division", "") or "").lower()
    напр = "Meyer" if ("meyer" in div or "мейер" in div) else "КЦ"
    st = store.get_mailbox_state(mb.mailbox_id)
    рд = getattr(st, "ramp_day", 0) if st else 0
    ёмкость[напр] += snd._daily_limit(mb.provider, рд + 1, mb.mailbox_id)

# ---- очередь ------------------------------------------------------------- #
АДР = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-Я]{2,}$")
итог = {}
for камп, имя in ((10, "КЦ"), (11, "Meyer")):
    with store._lock:
        строки = store._conn.execute(
            "SELECT c.id, c.email, c.recipient_id, r.inn, "
            "       COALESCE(p.verdict,'') proba, COALESCE(r.mx_provider,'') mx "
            "FROM confirm_reviews c "
            "JOIN messages m ON m.id=c.message_id "
            "LEFT JOIN recipients r ON r.id=c.recipient_id "
            "LEFT JOIN addr_probe p ON p.email=lower(c.email) "
            "WHERE c.campaign_id=? AND c.status IN ('approved','edited') "
            "AND m.status='scheduled'", (камп,)).fetchall()
    беды = Counter()
    чистых = 0
    for r in строки:
        e = str(r["email"] or "").strip().lower()
        плохо = []
        if not АДР.match(e):
            плохо.append("формат адреса")
        if str(r["proba"]) in ("нет ящика", "нет MX"):
            плохо.append(f"приговор пробы: {r['proba']}")
        try:
            причина = cs._guard(inn=str(r["inn"] or ""), email=e)
            if причина:
                плохо.append(f"заслон: {причина.split(':')[0]}")
        except Exception as ex:                                  # noqa: BLE001
            плохо.append(f"заслон не отработал: {str(ex)[:40]}")
        try:
            from sender.lovushki import заглушка
            if заглушка(e):
                плохо.append("адрес-заглушка")
        except Exception:                                        # noqa: BLE001
            pass
        if плохо:
            for p in плохо:
                беды[p] += 1
        else:
            чистых += 1
    итог[имя] = (len(строки), чистых, беды)

print("== ОЧЕРЕДЬ НА ЗАВТРА ==")
for имя in ("Meyer", "КЦ"):
    всего, чистых, беды = итог[имя]
    ём = ёмкость[имя]
    уедет = min(чистых, ём)
    print(f"\n  {имя}")
    print(f"    одобрено и ждёт:      {всего}")
    print(f"    прошли все проверки:  {чистых}")
    print(f"    ёмкость ящиков завтра: {ём}")
    print(f"    -> УЙДЁТ ЗАВТРА:      {уедет}"
          + (f"  (остаток {чистых - уедет} переедет)" if чистых > ём else ""))
    if беды:
        print("    не прошли проверку:")
        for b, n in беды.most_common():
            print(f"      {n:>4}  {b}")
