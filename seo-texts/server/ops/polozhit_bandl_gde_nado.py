# -*- coding: utf-8 -*-
"""Положить собранный бандл туда, откуда панель его реально отдаёт.

Служба поднята с --static-dir C:\\sender\\web\\dist, а собирается фронт в
C:\\sender\\sender\\web\\dist — это разные каталоги. Я собрал во второй, и
после перезапуска лента осталась прежней: панель отдавала старый бандл от
24.08.

Копируем свежий dist в боевой каталог, старый складываем рядом с меткой
времени. Служба читает файлы на каждый запрос — перезапуск не нужен, но
браузеру надо обновить страницу без кэша (имя файла бандла сменилось, так
что подхватится само).
"""
import os
import shutil
import sys
import time

ОТКУДА = r"C:\sender\sender\web\dist"
КУДА = r"C:\sender\web\dist"
ДЕЛАТЬ = "primenit" in sys.argv[1:]


def свод(каталог):
    if not os.path.isdir(каталог):
        return "нет каталога"
    файлы = []
    for корень, _д, имена in os.walk(каталог):
        for и in имена:
            п = os.path.join(корень, и)
            файлы.append((os.path.relpath(п, каталог), os.path.getsize(п),
                          time.strftime("%d.%m %H:%M",
                                        time.localtime(os.path.getmtime(п)))))
    return файлы


for имя, к in (("собрано", ОТКУДА), ("боевой", КУДА)):
    print("=== %s: %s ===" % (имя, к))
    с = свод(к)
    if isinstance(с, str):
        print("   %s" % с)
        continue
    for отн, размер, когда in sorted(с):
        print("   %-40s %9d  %s" % (отн, размер, когда))

if not ДЕЛАТЬ:
    print("\nвхолостую. Скопировать — primenit")
    raise SystemExit(0)

метка = time.strftime("%Y%m%d-%H%M%S")
бэкап = КУДА + ".bak-" + метка
shutil.copytree(КУДА, бэкап)
print("\nстарый бандл сохранён: %s" % бэкап)
for корень, _д, имена in os.walk(ОТКУДА):
    for и in имена:
        исток = os.path.join(корень, и)
        цель = os.path.join(КУДА, os.path.relpath(исток, ОТКУДА))
        os.makedirs(os.path.dirname(цель), exist_ok=True)
        shutil.copy2(исток, цель)
# старые ассеты с чужими именами убираем: иначе каталог растёт бесконечно,
# а index.html всё равно ссылается только на свежие.
свежие = {os.path.relpath(os.path.join(к, и), ОТКУДА)
          for к, _д, имена in os.walk(ОТКУДА) for и in имена}
убрано = 0
for корень, _д, имена in os.walk(КУДА):
    for и in имена:
        отн = os.path.relpath(os.path.join(корень, и), КУДА)
        if отн not in свежие:
            os.remove(os.path.join(корень, и))
            убрано += 1
print("скопировано файлов: %d, убрано устаревших: %d" % (len(свежие), убрано))
print("\nтеперь в боевом каталоге:")
for отн, размер, когда in sorted(свод(КУДА)):
    print("   %-40s %9d  %s" % (отн, размер, когда))
