# -*- coding: utf-8 -*-
"""Таблица в письме: выбор части и разбор. Три файла, --katit."""
import base64
import io
import json
import os
import py_compile
import shutil
import sys
import time

Д = json.loads(base64.b64decode("eyJleHRyYWN0IjogIiAgICAgICAgZnJvbSBzZW5kZXIucGlzbW9fdl90ZWtzdCBpbXBvcnQgbHVjaHNoZWVfdGVsbywgdl90ZWtzdFxuICAgICAgICBpZiBtc2cuaXNfbXVsdGlwYXJ0KCk6XG4gICAgICAgICAgICAjINCn0JDQodCi0Jgg0JHQldCg0IHQnCDQntCR0JUg0Jgg0JLQq9CR0JjQoNCQ0JXQnC4g0KLQtdC60YHRgtC+0LLQsNGPINC+0LHRi9GH0L3QviDQu9GD0YfRiNC1LCDQvdC+INC60L7Qs9C00LAg0LJcbiAgICAgICAgICAgICMg0L/QuNGB0YzQvNC1INCi0JDQkdCb0JjQptCQLCBPdXRsb29rINC60LvQsNC00ZHRgiDQsiBwbGFpbiDQtdGRINC+0LHQu9C+0LzQutC4OiDRj9GH0LXQudC60Lgg0L/QvlxuICAgICAgICAgICAgIyDRgdGC0YDQvtC60LDQvCwg0YDQsNC30LTQtdC70LjRgtC10LvRjCAtINGC0LDQsdGD0LvRj9GG0LjRjy4gMjYuMDgg0YLQtdGF0LfQsNC00LDQvdC40LUgwqvQodCc0JpcbiAgICAgICAgICAgICMg0JDQu9GM0YLQtdGA0L3QsNGC0LjQstCwwrsg0YLQsNC6INC4INGH0LjRgtCw0LvQvtGB0Ywg0YHRgtC+0LvQsdC40LrQvtC8INC40Lcg0YHQu9C+0LIgwqtOb8K7LFxuICAgICAgICAgICAgIyDCq9Ce0L/QuNGB0LDQvdC40LXCuywgwqvQlNCw0LLQu9C10L3QuNC1LMK7LCDCq9Cc0J/QsMK7LiDQkiBIVE1MINGB0YLRgNGD0LrRgtGD0YDQsCDRhtC10LvQsC5cbiAgICAgICAgICAgIHBsYWluID0gaHRtbCA9IFwiXCJcbiAgICAgICAgICAgIGZvciBwYXJ0IGluIG1zZy53YWxrKCk6XG4gICAgICAgICAgICAgICAg0YLQuNC/ID0gcGFydC5nZXRfY29udGVudF90eXBlKClcbiAgICAgICAgICAgICAgICBpZiDRgtC40L8gPT0gXCJ0ZXh0L3BsYWluXCIgYW5kIG5vdCBwbGFpbjpcbiAgICAgICAgICAgICAgICAgICAgcGxhaW4gPSBzZWxmLl9kZWNvZGVfcGFydChwYXJ0KVxuICAgICAgICAgICAgICAgIGVsaWYg0YLQuNC/ID09IFwidGV4dC9odG1sXCIgYW5kIG5vdCBodG1sOlxuICAgICAgICAgICAgICAgICAgICBodG1sID0gc2VsZi5fZGVjb2RlX3BhcnQocGFydClcbiAgICAgICAgICAgINGC0LXQu9C+ID0gbHVjaHNoZWVfdGVsbyhwbGFpbiwgaHRtbClcbiAgICAgICAgICAgIGlmINGC0LXQu9C+OlxuICAgICAgICAgICAgICAgIHJldHVybiDRgtC10LvQvlxuICAgICAgICBlbHNlOlxuICAgICAgICAgICAgcmV0dXJuIHZfdGVrc3Qoc2VsZi5fZGVjb2RlX3BhcnQobXNnKSlcbiJ9").decode("utf-8"))
КАТИТЬ = "--katit" in sys.argv

ЦЕЛИКОМ = (
    (r"C:\sender\sender\pismo_v_tekst.py", r"C:\sender\_ops\_novyy_pismo_v_tekst.py",
     "luchshee_telo"),
    (r"C:\sender\sender\mailbrowser.py", r"C:\sender\_ops\_novyy_mailbrowser.py",
     "luchshee_telo"),
)
W = r"C:\sender\sender\imap_watcher.py"
СТАРОЕ_W = '''        from sender.pismo_v_tekst import v_tekst
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    txt = self._decode_part(part)
                    if txt:
                        return txt
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    txt = v_tekst(self._decode_part(part))
                    if txt:
                        return txt
        else:
            return v_tekst(self._decode_part(msg))
'''

for боевой, новый, метка in ЦЕЛИКОМ:
    имя = os.path.basename(боевой)
    т = io.open(боевой, encoding="utf-8", errors="replace").read()
    нт = io.open(новый, encoding="utf-8", errors="replace").read()
    if метка in т:
        print("%-20s правка уже стоит" % имя)
        continue
    свои = set(нт.splitlines())
    пропало = [с for с in т.splitlines() if с.strip() and с not in свои]
    if пропало:
        print("%-20s ЗАТРЁМ %d строк — не трогаю" % (имя, len(пропало)))
        for с in пропало[:6]:
            print("     " + с[:130])
        continue
    print("%-20s боевой целиком в заготовке (%d -> %d)" % (имя, len(т), len(нт)))
    if not КАТИТЬ:
        continue
    копия = "%s.bak-%d" % (боевой, int(time.time()))
    shutil.copy2(боевой, копия)
    shutil.copy2(новый, боевой)
    py_compile.compile(боевой, doraise=True)
    print("   поставлен (.bak %s)" % os.path.basename(копия))

т = io.open(W, encoding="utf-8").read()
if "luchshee_telo" in т:
    print("imap_watcher.py     правка уже стоит")
else:
    n = т.count(СТАРОЕ_W)
    print("imap_watcher.py     якорь найден раз: %d" % n)
    if n != 1:
        raise SystemExit("якорь должен быть ровно один")
    if КАТИТЬ:
        копия = "%s.bak-%d" % (W, int(time.time()))
        io.open(копия, "w", encoding="utf-8", newline="").write(т)
        with io.open(W, "w", encoding="utf-8", newline="") as f:
            f.write(т.replace(СТАРОЕ_W, Д["extract"]))
            f.flush()
            os.fsync(f.fileno())
        py_compile.compile(W, doraise=True)
        print("   поставлен (.bak %s)" % os.path.basename(копия))
if not КАТИТЬ:
    print("\nсухой прогон. Катить: --katit")
