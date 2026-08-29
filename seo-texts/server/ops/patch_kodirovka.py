# -*- coding: utf-8 -*-
"""Кодировка письма: строгий utf-8 пробуем первым."""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\imap_watcher.py"
МЕТКА = "ЗАЯВЛЕННАЯ КОДИРОВКА ВРЁТ"
ЗАМЕНЫ = json.loads(r'''[["        charset = (part.get_content_charset() or \"\").lower()\n        tries = [charset] if charset else []\n        tries += [\"utf-8\", \"cp1251\", \"koi8-r\", \"iso-8859-5\"]", "        charset = (part.get_content_charset() or \"\").lower()\n        # ЗАЯВЛЕННАЯ КОДИРОВКА ВРЁТ ЧАЩЕ, ЧЕМ КАЖЕТСЯ, и однобайтовая ложь\n        # необратима на глаз: cp1251 «расшифрует» ЛЮБЫЕ байты без ошибки, и\n        # письмо в utf-8 с шапкой windows-1251 превращается в «РњС‹ СЂР°РґС‹\n        # РїСЂРёРІРµС‚СЃС‚РІРѕРІР°С‚СЊ» — так в ленте 29.08 выглядели письма\n        # texno-gm.com. Обратное невозможно: русский текст в cp1251 корректным\n        # utf-8 не бывает. Поэтому строгий utf-8 пробуем ПЕРВЫМ, и только если\n        # он не сошёлся — верим заголовку.\n        try:\n            return payload.decode(\"utf-8\")\n        except UnicodeDecodeError:\n            pass\n        tries = [charset] if charset else []\n        tries += [\"cp1251\", \"koi8-r\", \"iso-8859-5\"]"]]''')

т = io.open(ПУТЬ, encoding="utf-8").read()
if МЕТКА in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (т.count(стар), стар[:70]))
        raise SystemExit(1)
было = т
for стар, нов in ЗАМЕНЫ:
    т = т.replace(стар, нов)
бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(было); f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т); f.flush(); os.fsync(f.fileno())
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % ex)
    raise SystemExit(1)
print("готово: %d -> %d знаков, бэкап %s" % (len(было), len(т), os.path.basename(бэк)))
