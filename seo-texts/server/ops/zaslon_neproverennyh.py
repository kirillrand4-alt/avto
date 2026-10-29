# -*- coding: utf-8 -*-
"""Включить заслон непроверенного адреса автоотправки: auto_send.hold_unprobed_hours
в C:\\sender\\sender.yaml (по коду выключен по умолчанию). Замер 29.10: из 119 отбивок
за неделю 98 — адреса без пробы до отправки (вердикт «нет ящика» записала уже
сама отбивка). Письмо ждёт вердикта пробы до N часов, потом уходит как есть.
Бэкап .bak-zaslon-<время>, проверка чтением Config, откат при сбое; --otkat.
Нужен Restart-Service.   zaslon_neproverennyh.py [часов=24] [--primenit | --otkat]"""
import glob
import io
import re
import shutil
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

П = r"C:\sender\sender.yaml"
Ч = next((a for a in sys.argv[1:] if a.isdigit()), "24")
if "--otkat" in sys.argv:
    б = sorted(glob.glob(П + ".bak-zaslon-*"))[-1]
    shutil.copy2(б, П)
    print("откат из", б)
    sys.exit()
т = io.open(П, encoding="utf-8").read()
if re.search(r"(?m)^[ \t]+hold_unprobed_hours:", т):
    print("ключ уже есть:", re.search(r"(?m)^[ \t]+hold_unprobed_hours:.*$", т).group(0))
    sys.exit()
м = re.search(r"(?m)^auto_send:[ \t]*\n", т)
строка = "  hold_unprobed_hours: %s   # 29.10: не слать адрес без вердикта пробы до %s ч\n" % (Ч, Ч)
if м:
    новый = т[:м.end()] + строка + т[м.end():]
    print("секция auto_send есть — добавлю ключ")
else:
    новый = т.rstrip("\n") + "\n\nauto_send:\n" + строка
    print("секции auto_send нет — допишу в конец")
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
б = П + ".bak-zaslon-%d" % int(time.time())
shutil.copy2(П, б)
io.open(П, "w", encoding="utf-8").write(новый)
try:
    знач = Config.load(П).get("auto_send.hold_unprobed_hours")
    assert float(знач) == float(Ч), знач
    print("ПРИМЕНЕНО: auto_send.hold_unprobed_hours =", знач, "| бэкап", б, "| нужен Restart-Service SenderPanel -Force")
except Exception as ex:  # noqa: BLE001
    shutil.copy2(б, П)
    print("сбой, откат:", ex)
