# -*- coding: utf-8 -*-
"""Потолок разных адресов компании за 90 дней (confirm.company_contacts_per_period).

Владелец 12.10: этим 42 компаниям «мы всё равно собираемся писать», вариант 1 —
поднять потолок. Правка sender.yaml по тексту (комментарии целы), бэкап
.bak-<ts>, проверка загрузкой Config, откат при сбое. Панель читает конфиг при
старте: для подтверждения в панели нужен Restart-Service SenderPanel.

    potolok_adresov.py            — показать секцию confirm
    potolok_adresov.py --stavit N — поставить N
"""
import io
import re
import shutil
import sys
import time

ПУТЬ = r"C:\sender\sender.yaml"
т = io.open(ПУТЬ, encoding="utf-8").read()
строки = т.splitlines(True)
i0 = next((i for i, с in enumerate(строки) if re.match(r"^confirm:\s*(#.*)?$", с)), None)
if i0 is None:
    print("секции confirm: нет")
    print("=== ПОТОЛОК: НЕ НАЙДЕНО ===")
    sys.exit(0)
i1 = next((i for i in range(i0 + 1, len(строки)) if re.match(r"^\S", строки[i])), len(строки))
if "--stavit" not in sys.argv:
    print("".join(строки[i0:i1]))
    print("=== ПОТОЛОК: ПОКАЗАНО ===")
    sys.exit(0)
n = int(sys.argv[sys.argv.index("--stavit") + 1])
ключ = [i for i in range(i0 + 1, i1) if re.match(r"^\s+company_contacts_per_period\s*:", строки[i])]
отступ = re.match(r"^(\s+)", next((с for с in строки[i0 + 1:i1] if с.strip()), "  x")).group(1)
if ключ:
    строки[ключ[0]] = re.sub(r":\s*[^#\n]*", ": %d " % n, строки[ключ[0]], count=1)
else:
    строки.insert(i0 + 1, "%scompany_contacts_per_period: %d   # владелец 12.10: 42 компании, писать сейчас\n" % (отступ, n))
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8").write("".join(строки))
try:
    sys.path.insert(0, r"C:\sender")
    from sender.config import Config
    знач = Config.load(ПУТЬ).get("confirm.company_contacts_per_period")
    assert int(знач) == n, знач
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== ПОТОЛОК: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s; теперь confirm.company_contacts_per_period = %s" % (бэкап, знач))
print("=== ПОТОЛОК: ПОСТАВЛЕН ===")
