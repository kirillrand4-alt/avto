# -*- coding: utf-8 -*-
"""Вместе с карточкой поднимаем и ПИСЬМО.

25.08: «ON CONFLICT DO NOTHING» молча выбрасывал текст. Компания вернулась
в пул генерации, ей написали новое письмо, очередь отдала ту же СНЯТУЮ
карточку и ничего в неё не записала — 632 оплаченных письма легли в никуда.
Второй слой беды: ConfirmSend.submit возвращал жёсткое "pending" вместо
статуса из базы, поэтому генератор считал постановку удачной и печатал «ОК».

Две правки: снятую карточку оживляем свежим холодным письмом (живую и
отправленную НЕ трогаем — у них своя жизнь), и статус отдаём фактический.

    pl_run.py ochered_ozhivlyaet.py            # вхолостую
    pl_run.py ochered_ozhivlyaet.py primenit   # применить
"""
import base64
import io
import json
import os
import py_compile
import shutil
import sys
import time

КОРЕНЬ = r"C:\sender\sender"
ПРИМЕНИТЬ = "primenit" in sys.argv[1:]
ГРУЗ_B64 = (
    "eyJwYXRjaGVzIjogW3siZmlsZSI6ICJzdG9yZS5weSIsICJhIjogIklDQWdJQ0FnSUNBZ0lDQWdJ"
    "Q0FnSUNBZ0lDQWdJdEMvMExqUmdkR00wTHpRdmlEUXY5QzEwWURRdGRDLzBMalJnZEN3MEwzUXZp"
    "d2cwTHJRc05HQTBZTFF2dEdIMExyUXNDRFF2dEMyMExqUXN0QzcwTFhRdmRDd0lpd2dibTkzWDJs"
    "emJ5d0tJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnYVc1MEtISnZkMXNpYVdRaVhTa3BLUT09"
    "IiwgInIiOiAiSUNBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0l0Qy8wTGpSZ2RHTTBMelF2aURR"
    "djlDMTBZRFF0ZEMvMExqUmdkQ3cwTDNRdml3ZzBMclFzTkdBMFlMUXZ0R0gwTHJRc0NEUXZ0QzIw"
    "TGpRc3RDNzBMWFF2ZEN3SWl3Z2JtOTNYMmx6Ynl3S0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0lD"
    "QWdhVzUwS0hKdmQxc2lhV1FpWFNrcEtRb2dJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0l5RFFrdENjMEpY"
    "UW9kQ2kwSlVnMEtFZzBKclFrTkNnMEtMUW50Q24wSnJRbnRDWklOQ2YwSjdRbE5DZDBKalFuTkNR"
    "MEpYUW5DRFFtQ0RRbjlDWTBLSFFyTkNjMEo0dUlOQ2UwTGJRdU5DeTBMalJndEdNSU5DKzBMVFF2"
    "ZEdEQ2lBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0FqSU5DNjBMRFJnTkdDMEw3Umg5QzYwWU1nMEx6UXNO"
    "QzcwTDQ2SU5HQjBZTFJnTkMrMExyUXNDRFF2OUM0MFlIUmpOQzgwTEFnMEw3UmdkR0MwTERRdTlD"
    "dzBZSFJqQ0RRc2RHTElITnVlV0YwYjNrc0lOQzRDaUFnSUNBZ0lDQWdJQ0FnSUNBZ0lDQWpJTkMr"
    "MEwvUXRkR0EwTERSZ3RDKzBZQWcwTC9RdnRDMDBZTFFzdEMxMFlEUXR0QzAwTERRdXlEUXNkR0xJ"
    "TkdDMEw0c0lOR0gwTFhRczlDK0lOQ3cwTExSZ3RDKzBMN1JndEMvMFlEUXNOQ3kwTHJRc0NEUXZk"
    "QzFJTkN5MExqUXROQzQwWUl1Q2lBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0JwWmlCdFpYTnpZV2RsWDJs"
    "a09nb2dJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0lDQWdJR052Ym00dVpYaGxZM1YwWlNnS0lDQWdJQ0Fn"
    "SUNBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnSWxWUVJFRlVSU0J0WlhOellXZGxjeUJUUlZRZ2MzUmhk"
    "SFZ6UFNkd1pXNWthVzVuWDNKbGRtbGxkeWNzSUNJS0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0lD"
    "QWdJQ0FnSWlBZ0lDQWdJQ0JzWVhOMFgyVnljbTl5UFU1VlRFd3NJSFZ3WkdGMFpXUmZZWFE5UHlB"
    "aUNpQWdJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnSUNJZ1YwaEZVa1VnYVdROVB5QkJUa1Fn"
    "YzNSaGRIVnpQU2R6YTJsd2NHVmtKeUlzQ2lBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0lDQWdJ"
    "Q2h1YjNkZmFYTnZMQ0JwYm5Rb2JXVnpjMkZuWlY5cFpDa3BLUT09In1dfQ==")

груз = json.loads(base64.b64decode(ГРУЗ_B64).decode("utf-8"))
тексты = {}
for п in груз["patches"]:
    путь = os.path.join(КОРЕНЬ, п["file"])
    т = io.open(путь, encoding="utf-8").read()
    якорь = base64.b64decode(п["a"]).decode("utf-8")
    замена = base64.b64decode(п["r"]).decode("utf-8")
    if "ВМЕСТЕ С КАРТОЧКОЙ ПОДНИМАЕМ" in т:
        print("%s: правка уже стоит" % п["file"])
        continue
    н = т.count(якорь)
    print("%s: якорь найден %d раз" % (п["file"], н))
    if н != 1:
        raise SystemExit("ОТМЕНА: якорь должен встречаться ровно один раз")
    тексты[путь] = т.replace(якорь, замена)

if not тексты:
    print("править нечего")
    raise SystemExit(0)
if not ПРИМЕНИТЬ:
    print("\nвхолостую. Применить — primenit")
    raise SystemExit(0)

метка = time.strftime("%Y%m%d-%H%M%S")
записаны = []
try:
    for путь, текст in тексты.items():
        shutil.copy2(путь, путь + ".bak-" + метка)
        io.open(путь, "w", encoding="utf-8", newline="").write(текст)
        py_compile.compile(путь, doraise=True)
        записаны.append(путь)
        print("правлен %s (копия .bak-%s)" % (os.path.basename(путь), метка))
except Exception as e:  # noqa: BLE001
    print("СБОЙ: %s — откатываю" % e)
    for путь in записаны:
        shutil.copy2(путь + ".bak-" + метка, путь)
    raise
print("\nготово. Панель подхватит после Restart-Service SenderPanel -Force")
