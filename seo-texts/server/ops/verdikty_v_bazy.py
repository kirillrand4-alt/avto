# -*- coding: utf-8 -*-
"""«Наш это или нет» — по каждой компании во ВСЕЙ базе (владелец 13.10:
«чтобы потом по всей базе была информация, наш это или нет»).

Где лежит:
  * enrich.db/companies: verdikt_rusprom (покупатель | не покупатель | неясно),
    verdikt_napr (мейер | кц | оба | никуда | не мейер), verdikt_pochemu,
    verdikt_istochnik, verdikt_ts — отдельные поля, чужой nash_priznak не трогаем;
  * obzvon-index.db/kompaniya_verdikt(inn, rusprom, napr, pochemu, istochnik, ts).
Кто решил важнее: владелец > реестр > линза (по письму) > гейт > предкласс.
Решение источника ниже рангом прежнее не перетирает.

Модуль: obnovit([{inn, rusprom?, napr?, pochemu?, istochnik}]) — зовёт генератор.
Запуск: verdikty_v_bazy.py [--primenit] — сбор накопленного: гейт
(sender.db/target_verdicts), журналы прогонов (отсев предкласса, брак
«не покупатель»/«переставить на кц», годные письма Meyer), реестр «не наш».
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

РАНГ = {"владелец": 5, "реестр": 4, "линза": 3, "письмо": 3, "гейт": 2, "предкласс": 1}
КОЛОНКИ = ("verdikt_rusprom", "verdikt_napr", "verdikt_pochemu", "verdikt_istochnik", "verdikt_ts")


def _готовить(cx, ox):
    есть = {р[1] for р in cx.execute("PRAGMA table_info(companies)")}
    for к in КОЛОНКИ:
        if к not in есть:
            cx.execute("ALTER TABLE companies ADD COLUMN %s TEXT" % к)
    ox.execute("CREATE TABLE IF NOT EXISTS kompaniya_verdikt (inn TEXT PRIMARY KEY, rusprom TEXT, napr TEXT, "
               "pochemu TEXT, istochnik TEXT, ts TEXT)")


def obnovit(записи, *, применить=True):
    """Слить решения в обе базы. → Counter исходов."""
    св = Counter()
    if not записи:
        return св
    cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
    ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
    _готовить(cx, ox)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    for з in записи:
        инн = "".join(c for c in str(з.get("inn") or "") if c.isdigit())
        if not инн:
            continue
        ист = з.get("istochnik") or "предкласс"
        было = cx.execute("SELECT verdikt_rusprom, verdikt_napr, verdikt_pochemu, verdikt_istochnik "
                          "FROM companies WHERE inn=?", (инн,)).fetchone()
        if было is None:
            св["нет компании в обогащении"] += 1
            continue
        if было[3] and РАНГ.get(было[3], 0) > РАНГ.get(ист, 0):
            св["оставлено решение старше рангом"] += 1
            continue
        rus = з.get("rusprom") or было[0]
        napr = з.get("napr") or было[1]
        поч = (з.get("pochemu") or было[2] or "")[:300]
        if (rus, napr, поч, ист) == tuple(было):
            св["без изменений"] += 1
            continue
        св["записано: %s" % ист] += 1
        if применить:
            cx.execute("UPDATE companies SET verdikt_rusprom=?, verdikt_napr=?, verdikt_pochemu=?, "
                       "verdikt_istochnik=?, verdikt_ts=? WHERE inn=?", (rus, napr, поч, ист, ts, инн))
            ox.execute("INSERT INTO kompaniya_verdikt (inn, rusprom, napr, pochemu, istochnik, ts) VALUES "
                       "(?,?,?,?,?,?) ON CONFLICT(inn) DO UPDATE SET rusprom=excluded.rusprom, napr=excluded.napr, "
                       "pochemu=excluded.pochemu, istochnik=excluded.istochnik, ts=excluded.ts",
                       (инн, rus, napr, поч, ист, ts))
    if применить:
        cx.commit()
        ox.commit()
    cx.close()
    ox.close()
    return св


if __name__ == "__main__":
    ПРИМЕНИТЬ = "--primenit" in sys.argv
    записи = []
    c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
    for inn, v, chem, poch in c.execute("SELECT inn, verdict, chem, pochemu FROM target_verdicts"):
        записи.append({"inn": inn, "rusprom": v, "pochemu": " ".join(x for x in (chem, poch) if x),
                       "istochnik": "гейт"})
    print("гейт: %d" % len(записи))
    n0 = len(записи)
    for журнал in (r"C:\sender\_ops\gen-partiya-935.jsonl", r"C:\sender\_ops\gen-rossiya-9000.jsonl"):
        if not os.path.exists(журнал):
            continue
        for с in io.open(журнал, encoding="utf-8", errors="replace"):
            try:
                z = json.loads(с)
            except Exception:  # noqa: BLE001
                continue
            инн = z.get("inn")
            if z.get("этап") == "предкласс_отсев":
                записи.append({"inn": инн, "napr": "не мейер" if z.get("направление") == "meyer" else "не кц",
                               "pochemu": "предклассификатор: другое направление", "istochnik": "предкласс"})
            elif z.get("этап") == "итог":
                б = " ".join(str(x) for x in (z.get("брак") or []))
                if z.get("ок") and z.get("направление") == "meyer":
                    записи.append({"inn": инн, "rusprom": "покупатель", "napr": "мейер",
                                   "pochemu": "письмо Meyer прошло все проверки", "istochnik": "письмо"})
                elif "переставить на kc" in б:
                    записи.append({"inn": инн, "rusprom": "покупатель", "napr": "кц",
                                   "pochemu": б.split("НЕ ПОКУПАТЕЛЬ:", 1)[-1].strip()[:200], "istochnik": "линза"})
                elif "НЕ ПОКУПАТЕЛЬ" in б and z.get("направление") == "meyer":
                    записи.append({"inn": инн, "napr": "не мейер",
                                   "pochemu": б.split("НЕ ПОКУПАТЕЛЬ:", 1)[-1].strip()[:200], "istochnik": "линза"})
    print("из журналов прогонов: %d" % (len(записи) - n0))
    n1 = len(записи)
    try:
        sys.path.insert(0, r"C:\sender")
        from sender.ne_nash import build_ne_nash
        for инн in build_ne_nash().набор(None) or []:
            записи.append({"inn": инн, "rusprom": "не покупатель", "pochemu": "реестр «не наш адресат»",
                           "istochnik": "реестр"})
    except Exception as е:  # noqa: BLE001
        print("реестр «не наш» не прочитан: %s" % str(е)[:100])
    print("реестр: %d" % (len(записи) - n1))
    # порядок: сначала младшие источники, старшие перетрут
    записи.sort(key=lambda з: РАНГ.get(з["istochnik"], 0))
    св = obnovit(записи, применить=ПРИМЕНИТЬ)
    for к, n in св.most_common():
        print("   %-40s %d" % (к, n))
    if ПРИМЕНИТЬ:
        cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
        print("в базе теперь: покупатель Руспрома %s; направление %s" % (
            dict(cx.execute("SELECT verdikt_rusprom, count(*) FROM companies WHERE verdikt_rusprom IS NOT NULL GROUP BY 1").fetchall()),
            dict(cx.execute("SELECT verdikt_napr, count(*) FROM companies WHERE verdikt_napr IS NOT NULL GROUP BY 1").fetchall())))
    print("=== ВЕРДИКТЫ В БАЗЫ: %s ===" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "сухой прогон"))
