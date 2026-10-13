# -*- coding: utf-8 -*-
"""ai_quota._request передаёт адрес письма (email) — для сверки «имя ↔ ящик».

13.10: из 111 писем кампании 14 с полным именем по имени поздоровались в
одном: _request не отдавал адрес, и _imya_soglasuetsya_s_yashchikom всегда
получал пустую почту. Правка по якорю, бэкап .bak-<ts>, py_compile, откат.
"""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\ai_quota.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "АДРЕС ПИСЬМА (13.10)" in т:
    print("=== EMAIL В ЗАПРОСЕ: УЖЕ БЫЛО ===")
    sys.exit(0)
СТАР = '                "mode": "auto", "extra": extra,\n                "_digest"'
НОВ = '                # АДРЕС ПИСЬМА (13.10). Без него сверка «имя ↔ ящик» в\n                # ai_letter всегда отвечала «не согласуется», и именных\n                # приветствий не было: из 111 писем с полным именем по имени\n                # поздоровались в одном (kudinov@ ↔ «Кудинов Роман»).\n                "email": (getattr(r, "email", "") or "").strip().lower() or None,\n                "mode": "auto", "extra": extra,\n                "_digest"'
if т.count(СТАР) != 1:
    print("якорь: %d" % т.count(СТАР))
    print("=== EMAIL В ЗАПРОСЕ: НЕ ПРИМЕНЕНО ===")
    sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8").write(т.replace(СТАР, НОВ))
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== EMAIL В ЗАПРОСЕ: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== EMAIL В ЗАПРОСЕ: ПРИМЕНЕНО ===")
