# -*- coding: utf-8 -*-
"""Правка боевого цикла: уважать ящик, закреплённый за письмом.

Подбор ящика в auto_send.py уже знает направление письма (message=m), но
про messages.mailbox_id не знает ничего. У писем, где имя менеджера стоит
прямо в тексте (44 письма Ирины Кузнецовой в кампании 12), это значит
уход с чужого ящика: в теле одно имя, в подписи другое.

С бэкапом, компиляцией и откатом. argv: проба | делать
"""
import datetime as dt
import io
import py_compile
import shutil
import sys

ПУТЬ = r"C:\sender\sender\auto_send.py"
ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
МАРКЕР = "ЗАКРЕПЛЁННЫЙ ЗА ПИСЬМОМ ЯЩИК СИЛЬНЕЕ ПОДБОРА"

ЯКОРЬ = """        mailbox_id = self.sender.pick_mailbox(recipient, campaign, now=now,
                                              message=m)
"""

ЗАМЕНА = '''        #
        # ЗАКРЕПЛЁННЫЙ ЗА ПИСЬМОМ ЯЩИК СИЛЬНЕЕ ПОДБОРА. messages.mailbox_id
        # ставится там, где имя менеджера стоит в САМОМ ТЕКСТЕ письма: в
        # кампании вебинара 44 письма начинаются с «Меня зовут Ирина
        # Кузнецова», и уйти они должны только с её ящика. Подбор про это не
        # знает и вернул бы любой свободный — адресат получил бы одно имя в
        # тексте и другое в подписи. Ящик занят, на паузе или вне окна — ждём
        # свой, чужой не подставляем: release ниже вернёт письмо к следующему
        # тику, как и при обычном отказе подбора.
        pinned = getattr(m, "mailbox_id", None)
        if pinned:
            mailbox_id = pinned if self.sender.can_send_now(
                pinned, now=now) else None
        else:
            mailbox_id = self.sender.pick_mailbox(recipient, campaign, now=now,
                                                  message=m)
'''

исх = io.open(ПУТЬ, encoding="utf-8").read()
if МАРКЕР in исх:
    print("правка уже стоит")
    raise SystemExit(0)
if исх.count(ЯКОРЬ) != 1:
    print("ЯКОРЬ НЕ НАЙДЕН (%d совпадений) — правку не применяю" % исх.count(ЯКОРЬ))
    raise SystemExit(1)
print("якорь найден, ровно одно совпадение")
if not ДЕЛАТЬ:
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

бэкап = ПУТЬ + ".bak-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
shutil.copy2(ПУТЬ, бэкап)
print("бэкап: %s" % бэкап)
io.open(ПУТЬ, "w", encoding="utf-8", newline="").write(исх.replace(ЯКОРЬ, ЗАМЕНА, 1))
try:
    py_compile.compile(ПУТЬ, doraise=True)
    print("компиляция: ок")
except Exception as ex:
    shutil.copy2(бэкап, ПУТЬ)
    print("КОМПИЛЯЦИЯ УПАЛА, откатил: %s" % str(ex)[:200])
    raise SystemExit(1)
print("маркер на месте: %s" % (МАРКЕР in io.open(ПУТЬ, encoding="utf-8").read()))
