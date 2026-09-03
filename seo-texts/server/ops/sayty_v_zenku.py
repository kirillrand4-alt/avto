# -*- coding: utf-8 -*-
"""Положить в очередь зенки сайты, вытянутые ходилкой. Сначала от 30 млн.

Источник — журнал ходилки checko_finansy.jsonl, а НЕ таблица requisites:
ходилка пишет в журнал независимо от базы, и там уже 15 622 выручки, тогда
как перенос в базу ещё идёт. Ждать переноса незачем.

Порядок важен (владелец 03.09: «от 30 млн сначала»): зенка берёт очередь
сверху, поэтому крупные должны лечь первыми.

Повторов не делаем: пропускаем ИНН, которые уже есть в otdano.txt или в
самой очереди. По умолчанию СУХОЙ ПРОГОН.

Запуск: python sayty_v_zenku.py [--primenit] [порог=30000000]
"""
import io
import json
import os
import re
import sys
from collections import Counter

ЖУРНАЛ = r"C:\sender\server\checko_finansy.jsonl"
ZENNO = r"C:\seostat\drop\zenno"
ОЧЕРЕДЬ = os.path.join(ZENNO, "ochered.txt")
ОТДАНО = os.path.join(ZENNO, "otdano.txt")
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
ПОРОГ = 30_000_000
for а in sys.argv[1:]:
    if а.startswith(("порог=", "porog=")):
        try:
            ПОРОГ = int(а.split("=", 1)[1])
        except ValueError:
            pass


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def нормальный_сайт(з):
    з = str(з or "").strip().lower()
    if not з or з in ("-", "нет", "none"):
        return ""
    з = з.split("|")[0].split(",")[0].strip()
    з = re.sub(r"^https?://", "", з).strip("/ ")
    з = з.split("/")[0]
    if not з or "." not in з or " " in з:
        return ""
    return "http://" + з


# --- журнал ходилки ------------------------------------------------------
из_журнала = {}
строк = 0
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    строк += 1
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    if z.get("сбой"):
        continue
    и = цифры(z.get("inn"))
    if not и:
        continue
    сайт = нормальный_сайт(z.get("site_checko"))
    try:
        выр = int(str(z.get("revenue_rub") or "0") or 0)
    except ValueError:
        выр = 0
    if сайт:
        прежний = из_журнала.get(и)
        if not прежний or выр > прежний[1]:
            из_журнала[и] = (сайт, выр)

# --- кого уже отдавали ---------------------------------------------------
было = set()
for п in (ОТДАНО, ОЧЕРЕДЬ):
    if os.path.exists(п):
        for с in io.open(п, encoding="utf-8", errors="replace"):
            и = цифры(с.split(";")[0])
            if и:
                было.add(и)

счёт = Counter()
крупные, прочие = [], []
for и, (сайт, выр) in из_журнала.items():
    if и in было:
        счёт["уже отдавали"] += 1
        continue
    if выр >= ПОРОГ:
        крупные.append((выр, и, сайт))
    else:
        счёт["ниже порога (во вторую очередь)"] += 1
        прочие.append((выр, и, сайт))
крупные.sort(reverse=True)

добавлено = 0
if ПРИМЕНИТЬ and крупные:
    with io.open(ОЧЕРЕДЬ, "a", encoding="utf-8", newline="\n") as ф:
        for выр, и, сайт in крупные:
            ф.write("%s;%s;oba\n" % (и, сайт))
            добавлено += 1
        ф.flush()
        os.fsync(ф.fileno())

в_очереди = 0
if os.path.exists(ОЧЕРЕДЬ):
    в_очереди = sum(1 for с in io.open(ОЧЕРЕДЬ, encoding="utf-8",
                                       errors="replace") if с.strip())

print("=" * 76)
print("=== СВОДКА: САЙТЫ ХОДИЛКИ В ЗЕНКУ ===")
print("режим: %s; порог %s руб" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН",
                                   format(ПОРОГ, ",d")))
print("")
print("строк в журнале ходилки:        %7d" % строк)
print("компаний с сайтом:              %7d" % len(из_журнала))
for к, в in счёт.most_common():
    print("   %-30s %7d" % (к, в))
print("")
print("=== К ЗАГРУЗКЕ ===")
print("   ОТ %s руб (первая очередь):  %7d" % (format(ПОРОГ, ",d"), len(крупные)))
print("   ниже порога (потом):         %7d" % len(прочие))
if ПРИМЕНИТЬ:
    print("")
    print("   ДОПИСАНО В ОЧЕРЕДЬ:          %7d" % добавлено)
print("   строк в ochered.txt сейчас:  %7d" % в_очереди)
print("")
print("первые пять из первой очереди:")
for выр, и, сайт in крупные[:5]:
    print("   %-13s %-40s %s руб" % (и, сайт, format(выр, ",d")))
