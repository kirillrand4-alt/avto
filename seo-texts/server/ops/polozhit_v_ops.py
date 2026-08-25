# -*- coding: utf-8 -*-
"""Перенести скрипт из server\\ops в C:\\sender\\_ops и сверить с ним соседей.

Отцеплённый запуск умеет стартовать только из _ops, а панельная выкладка
кладёт файлы в server\\ops. Заодно показываем, не разошёлся ли partiya_gen
между двумя каталогами: гонять старую копию — верный способ не понять,
почему прогон ведёт себя не так.
"""
import hashlib
import os
import shutil
import sys

ИСТОК = r"C:\sender\server\ops"
ЦЕЛЬ = r"C:\sender\_ops"
ИМЕНА = [а for а in sys.argv[1:] if not а.startswith("-")]


def хеш(п):
    return hashlib.sha1(open(п, "rb").read()).hexdigest()[:12] if os.path.exists(п) else "нет"


for имя in ("partiya_gen.py",):
    a, b = os.path.join(ИСТОК, имя), os.path.join(ЦЕЛЬ, имя)
    print("%-20s server\\ops %s | _ops %s %s"
          % (имя, хеш(a), хеш(b), "СОВПАДАЮТ" if хеш(a) == хеш(b) else "РАЗОШЛИСЬ"))

for имя in ИМЕНА:
    a = os.path.join(ИСТОК, имя)
    if not os.path.exists(a):
        print("нет файла %s" % a)
        continue
    b = os.path.join(ЦЕЛЬ, имя)
    shutil.copy2(a, b)
    print("положено: %s (%s)" % (b, хеш(b)))
