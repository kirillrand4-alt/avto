# -*- coding: utf-8 -*-
"""Что собрано по Чеко и сколько из этого ещё НЕ заведено в работу.

Отвечаем на вопрос владельца: «там было 20к+ новых ещё доступно» — сколько
осталось на самом деле. Сводка в конце: pl_run отдаёт только хвост.
"""
import csv
import io
import os
import sqlite3
import subprocess
import time
from collections import Counter

КОРЕНЬ = r"C:\seostat\Parser2"
КОДЫ = os.path.join(КОРЕНЬ, "data", "okved-agro.txt")
CSV = os.path.join(КОРЕНЬ, "data", "agro-base.csv")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


# --- что в файле сбора ---------------------------------------------------
всего_строк, инны, по_кодам = 0, set(), Counter()
поля = []
if os.path.exists(CSV):
    # разделитель здесь «;», а первая колонка идёт с BOM — обычный
    # DictReader с запятой склеивает всю строку в одно поле, и счёт ИНН
    # выходит нулевым.
    with io.open(CSV, encoding="utf-8-sig", errors="replace", newline="") as ф:
        ч = csv.DictReader(ф, delimiter=";")
        поля = ч.fieldnames or []
        поле_инн = next((п for п in поля if п.lower() in
                         ("inn", "инн", "innn")), None)
        поле_код = next((п for п in поля if "основной" in п.lower()), None)
        поле_почта = next((п for п in поля if "очт" in п.lower()), None)
        поле_сайт = next((п for п in поля if "айт" in п.lower()), None)
        своя_почта = 0
        for р in ч:
            всего_строк += 1
            и = цифры(р.get(поле_инн)) if поле_инн else ""
            if и:
                инны.add(и)
            if поле_код:
                по_кодам[str(р.get(поле_код) or "")[:10]] += 1
            if поле_почта and str(р.get(поле_почта) or "").strip():
                своя_почта += 1

# --- коды: сколько закрыто -----------------------------------------------
коды_всего = 0
if os.path.exists(КОДЫ):
    коды_всего = len([s for s in io.open(КОДЫ, encoding="utf-8",
                                         errors="replace").read().split()
                      if s.strip()])

# --- сколько из собранного уже в обогащении ------------------------------
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
есть_в_обогащении = set()
мейер_в_обогащении = 0
for и, d in e.execute("SELECT inn, division FROM companies"):
    ц = цифры(и)
    if ц:
        есть_в_обогащении.add(ц)
        if "meyer" in (d or "").lower():
            мейер_в_обогащении += 1
# сколько собранных уже имеют почту
с_почтой = 0
if инны:
    try:
        e.execute("CREATE TEMP TABLE _sob(inn TEXT PRIMARY KEY)")
        e.executemany("INSERT OR IGNORE INTO _sob VALUES (?)",
                      [(и,) for и in инны])
        с_почтой = e.execute(
            "SELECT COUNT(DISTINCT c.inn) FROM companies c "
            "  JOIN _sob s ON s.inn = c.inn "
            " WHERE c.best_email IS NOT NULL AND c.best_email <> ''"
        ).fetchone()[0]
    except Exception:                                          # noqa: BLE001
        pass
e.close()

новые = инны - есть_в_обогащении

# --- живо ли ежедневное задание ------------------------------------------
задача = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-ScheduledTask | Where-Object { $_.TaskName -like '*Agro*' -or "
     "$_.TaskName -like '*Okved*' } | ForEach-Object { \"$($_.TaskName) = "
     "$($_.State)\" }"],
    capture_output=True, text=True, timeout=90).stdout.strip()
инфо = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-ScheduledTaskInfo -TaskName 'AgroOkvedCollectDaily' "
     "-ErrorAction SilentlyContinue | ForEach-Object { \"последний запуск: "
     "$($_.LastRunTime); итог: $($_.LastTaskResult); следующий: "
     "$($_.NextRunTime)\" }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

print("=" * 66)
print("=== СВОДКА: СБОР ПО ЧЕКО ===")
print("файл сбора: %s" % CSV)
if os.path.exists(CSV):
    print("   размер %d Б, изменён %s"
          % (os.path.getsize(CSV),
             time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(CSV)))))
print("   строк в файле:            %8d" % всего_строк)
print("   уникальных ИНН:           %8d" % len(инны))
print("   кодов ОКВЭД в задании:    %8d" % коды_всего)
print("   кодов реально встречено:  %8d" % len(по_кодам))
print("   строк с почтой в файле:   %8d" % своя_почта)
print("")
print("=== СКОЛЬКО ИЗ ЭТОГО УЖЕ В РАБОТЕ ===")
print("   уже есть в обогащении:    %8d" % len(инны & есть_в_обогащении))
print("   из них с почтой:          %8d" % с_почтой)
print("   ЕЩЁ НЕ ЗАВЕДЕНЫ ВОВСЕ:    %8d   <- это и есть «новые»" % len(новые))
print("")
print("для справки: мейеровских компаний в обогащении всего %d"
      % мейер_в_обогащении)
print("")
print("=== ЕЖЕДНЕВНЫЙ СБОР ===")
print(задача if задача else "   задачи с таким именем нет")
print(инфо if инфо else "   сведений о запусках нет")
