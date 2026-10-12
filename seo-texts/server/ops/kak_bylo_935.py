# -*- coding: utf-8 -*-
"""Как шла партия 935: вход, время, цена письма — по журналу драйвера.
И сколько адресов партий «Россия 9000»/«Белорусь 1000» ещё не проверено."""
import io
import json
import sqlite3
from collections import defaultdict

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
по_дню = defaultdict(lambda: defaultdict(float))
ключи = set()
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if z.get("цена_$") is None:
        continue
    ключи |= set(z)
    день = str(z.get("ts") or z.get("время") or z.get("дата") or "")[:10] or "?"
    д = по_дню[день]
    д["попыток"] += 1
    д["годных"] += 1 if z.get("тело") else 0
    д["цена"] += float(z.get("цена_$") or 0)
    д["вход"] += int(z.get("вход") or z.get("вход_токенов") or 0)
    д["кэш_зап"] += int(z.get("вход_кэш_запись") or 0)
    д["кэш_чт"] += int(z.get("вход_кэш_чтение") or 0)
    д["выход"] += int(z.get("выход") or z.get("выход_токенов") or 0)
    д["вызовов"] += int(z.get("вызовов") or 0)
    д["сек"] += float(z.get("сек") or z.get("секунд") or 0)
print("поля записи: %s" % ", ".join(sorted(ключи))[:600])
print("")
print("%-11s %6s %6s %9s %9s %8s %8s %8s %6s"
      % ("день", "попыт", "годн", "$/годное", "вход/поп", "кэш_чт", "выход", "вызовов", "сек"))
for день in sorted(по_дню):
    д = по_дню[день]
    n = д["попыток"] or 1
    print("%-11s %6d %6d %9.3f %9d %8d %8d %8.1f %6.0f"
          % (день, д["попыток"], д["годных"],
             д["цена"] / max(1, д["годных"]),
             (д["вход"] + д["кэш_зап"] + д["кэш_чт"]) / n, д["кэш_чт"] / n,
             д["выход"] / n, д["вызовов"] / n, д["сек"] / n))

print("")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
вердикт = {р[0]: р[1] for р in c.execute(
    "SELECT lower(email), verdict FROM addr_probe")}
for г in ("Россия 9000", "Белорусь 1000"):
    всего = smtp = мертв = 0
    for р in c.execute("SELECT lower(email) e, extra_json x FROM recipients "
                       "WHERE extra_json LIKE ?", ("%" + г + "%",)):
        try:
            if г not in (json.loads(р["x"] or "{}") or {}).get("gruppy", []):
                continue
        except Exception:  # noqa: BLE001
            continue
        всего += 1
        в = вердикт.get(р["e"])
        if в and в not in ("нет MX", "битый адрес"):
            smtp += 1
        if в in ("нет ящика", "нет MX", "битый адрес"):
            мертв += 1
    print("%-14s адресов %5d | SMTP-проба есть у %5d | без SMTP-пробы %5d | мёртвых %d"
          % (г, всего, smtp, всего - smtp, мертв))
print("=== КАК БЫЛО 935 ===")
