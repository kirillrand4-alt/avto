# -*- coding: utf-8 -*-
"""Правка оркестратора: подбор ящика знает направление письма и уважает
закреплённый ящик. С бэкапом, компиляцией и откатом при любой ошибке.

argv: проба | делать
"""
import datetime as dt
import io
import py_compile
import shutil
import sys

ПУТЬ = r"C:\sender\sender\orchestrator.py"
ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
МАРКЕР = "закреплённый за письмом ящик сильнее подбора"

ЯКОРЬ = """                        # pick_mailbox: часы тика передаём, если сендер их принимает
                        if self._accepts_now(self.sender.pick_mailbox):
                            mailbox_id = self.sender.pick_mailbox(recipient, campaign, now=now)
                        else:
                            mailbox_id = self.sender.pick_mailbox(recipient, campaign)
"""

ЗАМЕНА = '''                        # pick_mailbox: часы тика передаём, если сендер их принимает.
                        # MESSAGE ТОЖЕ. Без него подбор не знает НАПРАВЛЕНИЯ письма и
                        # предлагает ящик чужого направления, а send() зовёт тот же
                        # division_block УЖЕ С message и хоронит письмо mark_skipped
                        # ('division_gate_block') — терминально, без второй попытки.
                        # На партии вебинара (кампания 12) так сгорали 52 письма из
                        # 175: подбор давал компрессорный ящик под Meyer-письмо.
                        # Заплатку 17.08 написали в сам гейт, но до подбора она не
                        # доехала — слои судили по разным признакам.
                        #
                        # И закреплённый за письмом ящик сильнее подбора: письмо
                        # написано от имени конкретного менеджера (44 письма Ирины
                        # Кузнецовой в той же партии), с чужого ящика его слать
                        # нельзя. Ящик занят или на паузе — ждём свой, чужой не
                        # подставляем: release ниже вернёт письмо в очередь к
                        # следующему тику.
                        pinned = getattr(message, "mailbox_id", None)
                        if pinned:
                            try:
                                _можно = self.sender.can_send_now(pinned, now=now)
                            except TypeError:
                                _можно = self.sender.can_send_now(pinned)
                            mailbox_id = pinned if _можно else None
                        else:
                            _kw = {}
                            if self._accepts_now(self.sender.pick_mailbox):
                                _kw["now"] = now
                            try:
                                import inspect as _insp
                                _берёт = "message" in _insp.signature(
                                    self.sender.pick_mailbox).parameters
                            except (TypeError, ValueError):
                                _берёт = False   # фейк в тестах по старой сигнатуре
                            if _берёт:
                                _kw["message"] = message
                            mailbox_id = self.sender.pick_mailbox(
                                recipient, campaign, **_kw)
'''

исх = io.open(ПУТЬ, encoding="utf-8").read()
if МАРКЕР in исх:
    print("правка уже стоит, ничего не делаю")
    raise SystemExit(0)
if исх.count(ЯКОРЬ) != 1:
    print("ЯКОРЬ НЕ НАЙДЕН или неоднозначен (%d совпадений) — правку не применяю"
          % исх.count(ЯКОРЬ))
    raise SystemExit(1)
print("якорь найден, ровно одно совпадение")

if not ДЕЛАТЬ:
    print("будет заменено %d строк на %d" % (len(ЯКОРЬ.splitlines()),
                                             len(ЗАМЕНА.splitlines())))
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
    print("КОМПИЛЯЦИЯ УПАЛА, откатил из бэкапа: %s" % str(ex)[:200])
    raise SystemExit(1)

нов = io.open(ПУТЬ, encoding="utf-8").read()
print("маркер на месте: %s" % (МАРКЕР in нов))
print("вызовов pick_mailbox с message: %d" % нов.count("_kw[\"message\"] = message"))
