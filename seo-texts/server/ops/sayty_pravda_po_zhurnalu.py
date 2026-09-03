# -*- coding: utf-8 -*-
"""Настоящее ли отсутствие сайта — по журналу, без обращений к Чеко.

Если у компании пусто в site_checko, но есть телефон или почта, значит
страница контактов бралась и разбиралась, и сайта у неё правда нет. Если
пусто ВСЁ разом — страница не далась, и такую надо переспросить.
"""
import io
import json
import sqlite3
from collections import Counter

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
свежие = {str(r[0]) for r in c.execute(
    "SELECT inn FROM requisites WHERE src='checko-sbor-agro'")}
c.close()

разрез = Counter()
примеры = {}
for с in io.open(r"C:\sender\server\checko_finansy.jsonl", encoding="utf-8",
                 errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    if z.get("сбой"):
        разрез["не достучались вовсе"] += 1
        continue
    и = str(z.get("inn") or "")
    if и not in свежие:
        continue
    сайт = str(z.get("site_checko") or "").strip()
    тел = str(z.get("phones_checko") or "").strip()
    почта = str(z.get("emails_checko") or "").strip()
    выр = str(z.get("revenue_rub") or "").strip()
    if сайт:
        к = "САЙТ ЕСТЬ"
    elif тел or почта:
        к = "сайта нет, но контакты есть — отсутствие настоящее"
    elif выр not in ("", "0"):
        к = "ни сайта, ни контактов, но выручка есть — карточка бралась"
    else:
        к = "пусто всё — страница не далась, надо переспросить"
    разрез[к] += 1
    примеры.setdefault(к, []).append(
        "%s тел=%s почта=%s выр=%s"
        % (и, (тел or "—")[:18], (почта or "—")[:22], (выр or "—")[:12]))

print("=" * 82)
print("=== СВОДКА: НАСТОЯЩЕЕ ЛИ ОТСУТСТВИЕ САЙТА (свежий агро-сбор) ===")
всего = sum(в for к, в in разрез.items() if к != "не достучались вовсе")
for к, в in разрез.most_common():
    доля = (100.0 * в / всего) if всего and к != "не достучались вовсе" else 0
    print("   %-56s %6d  %s" % (к, в, ("(%4.1f%%)" % доля) if доля else ""))
print("")
for к, спис in примеры.items():
    print("--- %s" % к)
    for с in спис[:3]:
        print("      " + с)
