# -*- coding: utf-8 -*-
"""Разбор суда модели газовых писем (журнал gaz-kc-sud.jsonl): брак фраз по причинам, «не подходит» по отраслям
с примерами (продукция + почему). Только чтение.  gaz_sud_razbor.py [--primerov=N] [--vse > в файл]"""
import csv, io, json, os, re, random, sys, shutil
_ВЫХ = io.open(r"C:\sender\_ops\gaz-sud-razbor.txt", "w", encoding="utf-8")
_print = print
def print(*a, **k):
    _print(*a, file=_ВЫХ)
from collections import Counter, defaultdict
csv.field_size_limit(10 ** 9)
ДРОП = r"C:\seostat\drop\drop-storage"
def читать(имя):
    return list(csv.DictReader(io.open(os.path.join(ДРОП, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))
def цифры(x): return re.sub(r"\D", "", str(x or ""))
база = {цифры(р.get("ИНН")): р for р in читать("CA-ENGER-ZALIVKA.csv") + читать("CA-ENGER-ZALIVKA-kompanii.csv")}
суд = {}
for с in io.open(r"C:\sender\_ops\gaz-kc-sud.jsonl", encoding="utf-8"):
    try: з = json.loads(с); суд[з["inn"]] = з
    except ValueError: pass
N = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--primerov=")), "4"))
random.seed(5)
брак = Counter(з.get("beda") for з in суд.values() if not з.get("ok") and not з.get("konk") and з.get("beda"))
print("БРАК ФРАЗЫ по причинам:", dict(брак.most_common()))
не = defaultdict(list)
for и, з in суд.items():
    if not з.get("ok") and not з.get("konk") and not з.get("beda"):
        не[з.get("otr", "")].append(и)
всего_по = Counter(з.get("otr", "") for з in суд.values())
print("\nНЕ ПОДХОДИТ по отраслям (не подходит / всего судили):")
for отр, сп in sorted(не.items(), key=lambda x: -len(x[1])):
    print("\n%4d / %-4d %s" % (len(сп), всего_по[отр], отр[:70]))
    причины = Counter(re.sub(r"[^а-яё ]", "", (суд[и].get("pochemu") or "").lower()).split(" ")[0] for и in сп)
    for и in random.sample(сп, min(N, len(сп))):
        р = база.get(и, {})
        print("     - %s | %s\n         почему: %s" % ((р.get("Компания") or "")[:50], (р.get("Продукция") or "")[:150], (суд[и].get("pochemu") or "")[:150]))

_ВЫХ.close()
shutil.copy2(r"C:\sender\_ops\gaz-sud-razbor.txt", os.path.join(ДРОП, "gaz-sud-razbor.txt"))
_print("готово: gaz-sud-razbor.txt на дропе")
