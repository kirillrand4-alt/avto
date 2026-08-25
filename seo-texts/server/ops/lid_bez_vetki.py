# -*- coding: utf-8 -*-
"""Ответ без ветки тоже обязан стать карточкой лида.

Карточка заводилась только при непустом thread_id, а корпоративные
почтовики режут References. Сверка 25.08: 129 ответов клиентов против 112
карточек — пятнадцать потерянных, среди них живой интерес «Сафита» («с
удовольствием рассмотрим»). Ключ склейки без ветки push_warm_lead берёт по
адресу — он это умеет сам.

    pl_run.py lid_bez_vetki.py            # вхолостую
    pl_run.py lid_bez_vetki.py primenit   # применить
"""
import base64
import io
import json
import os
import py_compile
import shutil
import sys
import time

ПУТЬ = r"C:\sender\sender\imap_watcher.py"
ПРИМЕНИТЬ = "primenit" in sys.argv[1:]
ГРУЗ_B64 = (
    "eyJwYXRjaGVzIjogW3siYSI6ICJJQ0FnSUNBZ0lDQWdJQ0FnYVdZZ2MyVnNaaTVmY21Wd2JIbGZa"
    "R1Z6YXlCaGJtUWdaWFl1ZEdoeVpXRmtYMmxrT2dvZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnY21WamFY"
    "QnBaVzUwSUQwZ2MyVnNaaTVmYzNSdmNtVXVaMlYwWDNKbFkybHdhV1Z1ZENoeVpXTnBjR2xsYm5S"
    "ZmFXUXBDaUFnSUNBZ0lDQWdJQ0FnSUNBZ0lDQnBaaUJ5WldOcGNHbGxiblE2IiwgInIiOiAiSUNB"
    "Z0lDQWdJQ0FnSUNBZ0l5RFFrZEMxMExjZzBMTFF0ZEdDMExyUXVDRFF1OUM0MExRZzBZTFF2dEMy"
    "MExVZzBMM1JnOUMyMExYUXZTNGcwSmZRdE5DMTBZSFJqQ0RSZ2RHQzBMN1JqOUM3MEw0Z3dxdGhi"
    "bVFnWlhZdWRHaHlaV0ZrWDJsa3dyc3NJTkM0Q2lBZ0lDQWdJQ0FnSUNBZ0lDTWcwTERRc3RHQzBM"
    "N1F2dEdDMExMUXRkR0NJTkMvMExqUmdkR00wTHpRc0N3ZzBZTWcwTHJRdnRHQzBMN1JnTkMrMExQ"
    "UXZpRFF2OUMrMFlmUmd0QyswTExRdU5DNklOR0IwWURRdGRDMzBMRFF1eUJTWldabGNtVnVZMlZ6"
    "TENEUXZkQzFDaUFnSUNBZ0lDQWdJQ0FnSUNNZzBML1F2dEM2MExEUXQ5R0wwTExRc05DNzBZSFJq"
    "eURRdmRDNDBMclF2dEM4MFlNdUlOQ2EwTHZSanRHSElOR0IwTHJRdTlDMTBMblF1dEM0SUhCMWMy"
    "aGZkMkZ5YlY5c1pXRmtJTkN5MEw3UXQ5R00wTHpSa2RHQ0lOQy8wTDRLSUNBZ0lDQWdJQ0FnSUNB"
    "Z0l5RFFzTkMwMFlEUXRkR0IwWU1nNG9DVUlOR0IwTERRdkNEUmc5QzgwTFhRdGRHQ0xnb2dJQ0Fn"
    "SUNBZ0lDQWdJQ0JwWmlCelpXeG1MbDl5WlhCc2VWOWtaWE5yT2dvZ0lDQWdJQ0FnSUNBZ0lDQWdJ"
    "Q0FnY21WamFYQnBaVzUwSUQwZ2MyVnNaaTVmYzNSdmNtVXVaMlYwWDNKbFkybHdhV1Z1ZENoeVpX"
    "TnBjR2xsYm5SZmFXUXBDaUFnSUNBZ0lDQWdJQ0FnSUNBZ0lDQnBaaUJ5WldOcGNHbGxiblE2In0s"
    "IHsiYSI6ICJJQ0FnSUNBZ0lDQnBaaUJ6Wld4bUxsOXlaWEJzZVY5a1pYTnJJR0Z1WkNCeVpXTnBj"
    "R2xsYm5SZmFXUTZDaUFnSUNBZ0lDQWdJQ0FnSUhKbFkybHdhV1Z1ZENBOUlITmxiR1l1WDNOMGIz"
    "SmxMbWRsZEY5eVpXTnBjR2xsYm5Rb2NtVmphWEJwWlc1MFgybGtLUW9nSUNBZ0lDQWdJQ0FnSUNC"
    "cFppQnlaV05wY0dsbGJuUWdZVzVrSUdWMkxuUm9jbVZoWkY5cFpEbz0iLCAiciI6ICJJQ0FnSUNB"
    "Z0lDQnBaaUJ6Wld4bUxsOXlaWEJzZVY5a1pYTnJJR0Z1WkNCeVpXTnBjR2xsYm5SZmFXUTZDaUFn"
    "SUNBZ0lDQWdJQ0FnSUhKbFkybHdhV1Z1ZENBOUlITmxiR1l1WDNOMGIzSmxMbWRsZEY5eVpXTnBj"
    "R2xsYm5Rb2NtVmphWEJwWlc1MFgybGtLUW9nSUNBZ0lDQWdJQ0FnSUNBaklOQ1MwSlhRb3RDYTBK"
    "QWcwSjNRbFNEUW50Q1IwSy9RbDlDUTBLTFFsZENiMEt6UW5kQ1FMaURRbDlDMDBMWFJnZEdNSU5H"
    "QjBZTFF2dEdQMEx2UXZpRENxMkZ1WkNCbGRpNTBhSEpsWVdSZmFXVEN1em9nMEw3Umd0Q3kwTFhS"
    "Z2lEUXNkQzEwTGNLSUNBZ0lDQWdJQ0FnSUNBZ0l5QlNaV1psY21WdVkyVnpJQ2pRdXRDKzBZRFF2"
    "OUMrMFlEUXNOR0MwTGpRc3RDOTBZdlF0U0RRdjlDKzBZZlJndEMrMExMUXVOQzYwTGdnMExqUmhT"
    "RFJnTkMxMExiUmc5R0NLU0RRdmRDMUlOQzMwTERRc3RDKzBMVFF1TkM3Q2lBZ0lDQWdJQ0FnSUNB"
    "Z0lDTWcwTHJRc05HQTBZTFF2dEdIMExyUmd5RFFzdEMrMExMUmdkQzFMaURRb2RDeTBMWFJnTkM2"
    "MExBZ01qVXVNRGc2SURFeU9TRFF2dEdDMExMUXRkR0MwTDdRc2lEUXV0QzcwTGpRdGRDOTBZTFF2"
    "dEN5SU5DLzBZRFF2dEdDMExqUXNpQXhNVElLSUNBZ0lDQWdJQ0FnSUNBZ0l5RFF1dEN3MFlEUmd0"
    "QyswWWZRdGRDNklPS0FsQ0RRdjlHUDBZTFF2ZEN3MExUUmh0Q3cwWUxSakNEUXY5QyswWUxRdGRH"
    "QTBZL1F2ZEM5MFl2UmhTd2cwWUhSZ05DMTBMVFF1Q0RRdmRDNDBZVWcwTGJRdU5DeTBMN1F1U0RR"
    "dU5DOTBZTFF0ZEdBMExYUmdRb2dJQ0FnSUNBZ0lDQWdJQ0FqSU1LcjBLSFFzTkdFMExqUmd0Q3d3"
    "cnNnS01LcjBZRWcwWVBRdE5DKzBMTFF2dEM3MFl6UmdkR0MwTExRdU5DMTBMd2cwWURRc05HQjBZ"
    "SFF2TkMrMFlMUmdOQzQwTHpDdXlrdUlOQ2EwTHZSanRHSElOR0IwTHJRdTlDMTBMblF1dEM0SU5D"
    "eDBMWFF0eURRc3RDMTBZTFF1dEM0Q2lBZ0lDQWdJQ0FnSUNBZ0lDTWdjSFZ6YUY5M1lYSnRYMnhs"
    "WVdRZzBMSFF0ZEdBMFpIUmdpRFF2OUMrSU5DdzBMVFJnTkMxMFlIUmd5NEtJQ0FnSUNBZ0lDQWdJ"
    "Q0FnYVdZZ2NtVmphWEJwWlc1ME9nPT0ifV19")

груз = json.loads(base64.b64decode(ГРУЗ_B64).decode("utf-8"))
текст = io.open(ПУТЬ, encoding="utf-8").read()
if "ВЕТКА НЕ ОБЯЗАТЕЛЬНА" in текст:
    print("правка уже стоит")
    raise SystemExit(0)
новый = текст
for н, п in enumerate(груз["patches"], 1):
    якорь = base64.b64decode(п["a"]).decode("utf-8")
    замена = base64.b64decode(п["r"]).decode("utf-8")
    сколько = новый.count(якорь)
    print("якорь %d: %d раз" % (н, сколько))
    if сколько != 1:
        raise SystemExit("ОТМЕНА: якорь должен встречаться ровно один раз")
    новый = новый.replace(якорь, замена)
if not ПРИМЕНИТЬ:
    print("\nвхолостую. Применить — primenit")
    raise SystemExit(0)
метка = time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(ПУТЬ, ПУТЬ + ".bak-" + метка)
try:
    io.open(ПУТЬ, "w", encoding="utf-8", newline="").write(новый)
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as e:  # noqa: BLE001
    print("СБОЙ: %s — откатываю" % e)
    shutil.copy2(ПУТЬ + ".bak-" + метка, ПУТЬ)
    raise
print("правлен imap_watcher.py (копия .bak-%s)" % метка)
