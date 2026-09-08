# -*- coding: utf-8 -*-
"""Поднять пороги заслона по спам-отказам в sender.yaml.

Владелец 08.09: «приоткрой потолок по спаму, чтобы ушли ещё 130-150 писем
сегодня». Сейчас ключей в конфиге нет и работают умолчания: 2 отказа на
ящик и 5 на направление за сутки. Сегодня по направлению уже 5, то есть
СЛЕДУЮЩИЙ отказ снова погасит весь Meyer.

Считаем по факту: при наблюдаемой доле отказов около 4% на 150 писем
придётся ещё примерно 6 отказов, вместе с сегодняшними это 11. Ставим порог
направления 15 - хватит на партию и всё ещё остановит настоящий обвал.
Порог ящика 4: одна опальная учётка гасит себя, а не всех. Минимум разных
ящиков 3 - чтобы направление душили только при общей беде.

Правка хирургическая, по якорю, с копией рядом. Панель читает конфиг при
старте, поэтому пороги вступят в силу только после перезапуска службы -
это действие владельца.

    python podnyat_porog_otkazov.py            # показать
    python podnyat_porog_otkazov.py --primenit
"""
import io
import os
import shutil
import sys
import time

П = r"C:\sender\sender.yaml"
ЯКОРЬ = "  min_volume: 50"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
ДОБАВКА = (
    "\n"
    "  # Заслон по отказам почтовика «подозрение на спам» (sender/otkaz_spam.py).\n"
    "  # Умолчания 2/5/2 останавливали направление на шестом отказе за сутки;\n"
    "  # владелец 08.09 попросил приоткрыть, чтобы за день ушло 130-150 писем.\n"
    "  otkaz_stop_yashchik: 4\n"
    "  otkaz_stop_napravlenie: 15\n"
    "  otkaz_min_yashchikov: 3\n")

т = io.open(П, encoding="utf-8", errors="replace").read()
есть = [к for к in ("otkaz_stop_yashchik", "otkaz_stop_napravlenie",
                    "otkaz_min_yashchikov") if к in т]
print("ключи заслона уже в файле: %s" % (", ".join(есть) or "нет"))
if есть:
    print("правка не нужна или её надо делать руками — выхожу")
    raise SystemExit(0)
if ЯКОРЬ not in т:
    print("якорь %r не найден — не трогаю файл" % ЯКОРЬ)
    raise SystemExit(2)
if т.count(ЯКОРЬ) != 1:
    print("якорь встречается %d раз — не трогаю файл" % т.count(ЯКОРЬ))
    raise SystemExit(2)

новый = т.replace(ЯКОРЬ, ЯКОРЬ + ДОБАВКА)
print("")
print("--- что добавится после строки %r ---" % ЯКОРЬ)
for с in ДОБАВКА.strip("\n").splitlines():
    print("   " + с)

if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Применить — --primenit")
    raise SystemExit(0)

копия = П + ".bak-" + str(int(time.time()))
shutil.copy2(П, копия)
with io.open(П, "w", encoding="utf-8") as ф:
    ф.write(новый)
    ф.flush()
    os.fsync(ф.fileno())

# ПРОВЕРКА ТЕМ ЖЕ ЗАГРУЗЧИКОМ, ЧТО У ПАНЕЛИ. PyYAML в этом окружении нет
# (первая попытка правки на нём и откатилась), а sender.config разбирает
# конфиг своим парсером - он и есть источник истины для панели.
ок = True
try:
    sys.path.insert(0, r"C:\sender")
    from sender.config import Config, _load_yaml                # noqa: E402
    d = _load_yaml(io.open(П, encoding="utf-8").read())
    g = (d or {}).get("gates") or {}
    print("")
    print("разбор конфига: otkaz_stop_yashchik=%s, otkaz_stop_napravlenie=%s, "
          "otkaz_min_yashchikov=%s"
          % (g.get("otkaz_stop_yashchik"), g.get("otkaz_stop_napravlenie"),
             g.get("otkaz_min_yashchikov")))
    if int(g.get("otkaz_stop_napravlenie") or 0) != 15:
        ок = False
    # и целиком, как это делает панель на старте
    c = Config.load(П)
    print("Config.load: ящиков %d, пороги из конфига %s / %s"
          % (len(c.mailboxes()), c.get("gates.otkaz_stop_yashchik", None),
             c.get("gates.otkaz_stop_napravlenie", None)))
except Exception as ex:                                         # noqa: BLE001
    ок = False
    print("КОНФИГ НЕ ЧИТАЕТСЯ: %s: %s" % (type(ex).__name__, str(ex)[:140]))
# Кроме разбора - структурная сверка: правка обязана быть ЧИСТОЙ ВСТАВКОЙ,
# всё остальное побайтно прежним.
if ок:
    было_строк = т.splitlines()
    стало_строк = io.open(П, encoding="utf-8").read().splitlines()
    добавлено = [с for с in стало_строк if с not in было_строк]
    лишние = [с for с in было_строк if с not in стало_строк]
    print("строк было %d, стало %d; пропало прежних строк: %d"
          % (len(было_строк), len(стало_строк), len(лишние)))
    if лишние:
        ок = False
        for с in лишние[:5]:
            print("   ПРОПАЛА: %s" % с[:80])
if not ок:
    shutil.copy2(копия, П)
    print("ОТКАТИЛ на %s" % копия)
    raise SystemExit(1)

print("")
print("=" * 74)
print("=== ПОРОГИ ЗАСЛОНА ПОДНЯТЫ ===")
print("копия прежнего файла: %s" % копия)
print("ВСТУПЯТ В СИЛУ ПОСЛЕ ПЕРЕЗАПУСКА ПАНЕЛИ: панель читает конфиг на старте")
