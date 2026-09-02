# -*- coding: utf-8 -*-
"""Только чтение: как письмо из confirm_reviews попадает в отправку."""
import inspect
import os
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender import store as S  # noqa: E402

print("=== confirm_submit ===")
src = inspect.getsource(S.Store.confirm_submit)
print(src[:1800])

print("\n=== КТО ВЫЗЫВАЕТ confirm_decide / ставит scheduled ===")
корни = [r"C:\sender\sender", r"C:\sender\server"]
для = []
for корень in корни:
    for дп, _, фс in os.walk(корень):
        for ф in фс:
            if not ф.endswith(".py"):
                continue
            п = os.path.join(дп, ф)
            try:
                т = open(п, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            for м in re.finditer(r"confirm_decide|ИМЯ_ОТПРАВИТЕЛЯ|body_rendered\s*=", т):
                стр = т[:м.start()].count("\n") + 1
                для.append("%s:%d %s" % (os.path.relpath(п, r"C:\sender"), стр, м.group(0)))
for x in для[:26]:
    print("  " + x)
print("  всего вхождений: %d" % len(для))
