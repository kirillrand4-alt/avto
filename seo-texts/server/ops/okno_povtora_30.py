# -*- coding: utf-8 -*-
"""Окно повторного контакта на ТОТ ЖЕ адрес — 30 дней вместо 90 (владелец 23.10:
«на тот же адрес — нет, тут 30 дней оставь»): ключ confirm.recent_contact_days: 30
в C:\\sender\\sender.yaml (секция confirm). Бэкап .bak-okno30-<время>, проверка
чтением Config, откат при сбое; --otkat. Нужен Restart-Service.
    okno_povtora_30.py [--primenit | --otkat]"""
import glob
import io
import re
import shutil
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

П = r"C:\sender\sender.yaml"
if "--otkat" in sys.argv:
    б = sorted(glob.glob(П + ".bak-okno30-*"))[-1]
    shutil.copy2(б, П)
    print("откат из", б)
    sys.exit()
т = io.open(П, encoding="utf-8").read()
м = re.search(r"(?m)^confirm:[ \t]*\n((?:[ \t]+.*\n|\s*\n)*)", т)
if not м:
    print("секции confirm: нет — НЕ ПРИМЕНЕНО")
    sys.exit()
отступ = (re.match(r"[ \t]+", м.group(1)) or re.match("", "")).group(0) or "  "
if re.search(r"(?m)^[ \t]+recent_contact_days:", м.group(1)):
    print("ключ уже есть:", re.search(r"(?m)^[ \t]+recent_contact_days:.*$", м.group(1)).group(0))
    sys.exit()
новый = т[:м.start(1)] + "%srecent_contact_days: 30   # владелец 23.10: тот же адрес — через 30 дней\n" % отступ + т[м.start(1):]
print("вставлю после строки 'confirm:' с отступом %r" % отступ)
if "--primenit" not in sys.argv:
    sys.exit()
б = П + ".bak-okno30-%d" % int(time.time())
shutil.copy2(П, б)
io.open(П, "w", encoding="utf-8").write(новый)
try:
    знач = Config.load(П).get("confirm.recent_contact_days")
    assert int(знач) == 30, знач
except Exception as ex:  # noqa: BLE001
    shutil.copy2(б, П)
    print("сбой, откат:", ex)
    sys.exit()
print("ПРИМЕНЕНО: confirm.recent_contact_days =", знач, "| бэкап", б)
