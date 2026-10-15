# -*- coding: utf-8 -*-
"""confirm: правило повтора владельца (30 дней на тот же адрес, 5 дней на другой,
без живого ответа) — и для писем КЦ, не только Meyer (владелец 15.10: письма
«КЦ тест» не уходили в автоотправку с удержанием recent_contact). Письмо одного
направления после письма другого — разрешено сразу, как и было у Meyer.
Правка по якорям."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\confirm.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "_див_повтора" in т:
    print("=== ПОВТОР КЦ: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('''                if str(ex.get("division") or "") != "meyer":
                    return False''', '''                _див_повтора = str(ex.get("division") or "")
                if _див_повтора not in ("meyer", "kc"):
                    return False'''),
        ('''                камп = last.get("campaign_id")
                if камп is not None:
                    if int(камп) in self._КЦ_КАМПАНИИ:
                        return True
                    имя = c.execute("SELECT name FROM campaigns WHERE id=?", (камп,)).fetchone()
                    if имя and "КЦ" in str(имя[0] or ""):
                        return True''', '''                камп = last.get("campaign_id")
                if камп is not None:
                    имя = c.execute("SELECT name FROM campaigns WHERE id=?", (камп,)).fetchone()
                    _прошлое_кц = (int(камп) in self._КЦ_КАМПАНИИ
                                   or bool(имя and "КЦ" in str(имя[0] or "")))
                    # другое направление писало — повтор разрешён сразу
                    if _прошлое_кц != (_див_повтора == "kc"):
                        return True''')]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:100]))
        print("=== ПОВТОР КЦ: НЕ ПРИМЕНЕНО ===")
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
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== ПОВТОР КЦ: ПРИМЕНЕНО ===")
