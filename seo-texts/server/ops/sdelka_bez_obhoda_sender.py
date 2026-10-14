# -*- coding: utf-8 -*-
"""sender.py: запрет по активной сделке направления — без обхода «Отправить всё равно» (владелец 14.10)."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\sender.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "АКТИВНАЯ СДЕЛКА НАПРАВЛЕНИЯ — БЕЗ ОБХОДА" in т:
    print("=== СДЕЛКА БЕЗ ОБХОДА: SENDER: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('        div_reason = None if force else self.division_block(\n            recipient, mailbox_id, message=message)\n', '        # АКТИВНАЯ СДЕЛКА НАПРАВЛЕНИЯ — БЕЗ ОБХОДА (владелец 14.10): force\n        # снимает гейт направлений, но не запрет по сделке в работе.\n        if force:\n            try:\n                from sender.sdelki_napr import blok as _sdelka\n                _mb = self._mailbox_cfg(mailbox_id)\n                with self.store._lock:\n                    _сд = _sdelka(self.store._conn, getattr(recipient, "inn", None),\n                                  getattr(_mb, "division", None))\n            except Exception:  # noqa: BLE001\n                _сд = None\n            if _сд:\n                self.store.mark_skipped(message.id, "division_gate_block:deal_in_division:" + _сд)\n                raise SuppressedError("сделка в работе: " + _сд)\n        div_reason = None if force else self.division_block(\n            recipient, mailbox_id, message=message)\n')]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== СДЕЛКА БЕЗ ОБХОДА: SENDER: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
for с, н in ПАРЫ:
    т = т.replace(с, н)
io.open(ПУТЬ, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== СДЕЛКА БЕЗ ОБХОДА: SENDER: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== СДЕЛКА БЕЗ ОБХОДА: SENDER: ПРИМЕНЕНО ===")
