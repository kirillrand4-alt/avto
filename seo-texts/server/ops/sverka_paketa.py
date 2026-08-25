# -*- coding: utf-8 -*-
"""Хеши файлов пакета на сервере — чтобы знать, что перезапишет выкатка.

Каталог C:\\sender\\sender делят несколько сессий. Прежде чем катить пакет
целиком, надо видеть, где серверный текст разошёлся с песочницей: иначе
чужая правка молча откатится.
"""
import hashlib
import os

КОРЕНЬ = r"C:\sender\sender"
for имя in sorted(os.listdir(КОРЕНЬ)):
    п = os.path.join(КОРЕНЬ, имя)
    if not имя.endswith(".py") or not os.path.isfile(п):
        continue
    b = open(п, "rb").read()
    print("%-28s %8d %s" % (имя, len(b), hashlib.sha1(b).hexdigest()[:12]))
подкаталоги = [д for д in sorted(os.listdir(КОРЕНЬ))
               if os.path.isdir(os.path.join(КОРЕНЬ, д)) and not д.startswith("__")]
print("\nподкаталоги: %s" % ", ".join(подкаталоги))
for д in ("api", "web"):
    п = os.path.join(КОРЕНЬ, д)
    if not os.path.isdir(п):
        continue
    for корень, _д, файлы in os.walk(п):
        for ф in sorted(файлы):
            if not (ф.endswith(".py") or ф.endswith(".js") or ф.endswith(".css")
                    or ф == "index.html"):
                continue
            путь = os.path.join(корень, ф)
            b = open(путь, "rb").read()
            отн = os.path.relpath(путь, КОРЕНЬ)
            print("%-46s %8d %s" % (отн, len(b), hashlib.sha1(b).hexdigest()[:12]))
