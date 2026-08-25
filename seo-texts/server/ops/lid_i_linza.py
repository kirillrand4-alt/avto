# -*- coding: utf-8 -*-
"""Второй ответ дописывает карточку лида; линзы качества — рубильником.

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
    "eyJwYXRjaGVzIjogW3siZmlsZSI6ICJyZXZpZXdfbGVuc2VzLnB5IiwgImEiOiAiSUNBZ0lHMXZa"
    "R1ZzSUQwZ2JXOWtaV3dnYjNJZ0oyTnNZWFZrWlMxdmNIVnpMVFF0T0NjPSIsICJyIjogIklDQWdJ"
    "Q01nMEp6UW50Q1UwSlhRbTlDc0lOQ2IwSmpRbmRDWDBLc2dMU0RRb05DajBKSFFtTkNiMEt6UW5k"
    "Q1kwSnJRbnRDY0xDRFFrQ0RRbmRDVklOQ2YwS0RRa05DUzBKclFudENaSU5DYTBKN1FsTkNRTGlE"
    "UWt0QzcwTERRdE5DMTBMdlF0ZEdHSURJMUxqQTRJTkMvMEw0S0lDQWdJQ01nMExiUmc5R0EwTDNR"
    "c05DNzBZTWcwWWpRdTlHTzBMZlFzRG9nMEx2UXVOQzkwTGZSaXlEUXV0Q3cwWWZRdGRHQjBZTFFz"
    "dEN3SU5HSTBMdlF1Q0RRdmRDd0lOQyswTC9SZzlHQjBMVWcwTC9RdmlBa01DNHdOakVnMExmUXND"
    "RFFzdEdMMExmUXZ0Q3lJTkMvMFlEUXZ0R0MwTGpRc2dvZ0lDQWdJeUFrTUM0d01EY3RNQzR3TVRV"
    "ZzBZTWdjMjl1Ym1WMExDRFFzdEdIMExYUmd0Q3kwTFhSZ05DK0lOQzAwTDdSZ05DKzBMYlF0UzRn"
    "MEp2UXVOQzkwTGZRc0NEUmg5QzQwWUxRc05DMTBZSWcwTFBRdnRHQzBMN1FzdEMrMExVZzBML1F1"
    "TkdCMFl6UXZOQytDaUFnSUNBaklOQy8wTDRnMFlIUXY5QzQwWUhRdXRHRElOQy8wWURRc05DeTBM"
    "alF1eURRdUNEUXZ0R0MwTExRdGRHSDBMRFF0ZEdDSU1LcmIyc3YwTDNRdFNCdmE4SzdJQzBnMFlM"
    "UXZpRFF0dEMxSU5HQTBMWFJpTkMxMEwzUXVOQzFMQ0RSaDlHQzBMNGdNVGd1TURnS0lDQWdJQ01n"
    "MEwvUmdOQzQwTDNSajlDNzBMZ2cwTC9RdmlEUXY5R0EwTDdRc3RDMTBZRFF1dEN3MEx3ZzBMZ2cw"
    "TC9RdmlEUXM5QzEwTG5SZ3RHRElOQ3cwTFRSZ05DMTBZSFFzTkdDMExBdUlOQ2owTHpRdnRDNzBZ"
    "ZlFzTkM5MExqUXRTRFF2ZEMxSU5HQzBZRFF2dEN6MExEUXRkQzhPaURRc2RDMTBMY0tJQ0FnSUNN"
    "Z1RFVk9VMTlOVDBSRlRDRFFzdEdCMFpFZzBMclFzTkM2SU5DeDBZdlF1OUMrTENEUmg5R0QwTGJR"
    "dU5DMUlOQ3kwWXZRdDlDKzBMTFJpeURRc3RDMTBMVFJnOUdDSU5HQjBMWFFzZEdQSU5DLzBMNHQw"
    "TC9SZ05DMTBMYlF2ZEMxMEx6Umd5NEtJQ0FnSUcxdlpHVnNJRDBnYlc5a1pXd2diM0lnYjNNdVpX"
    "NTJhWEp2Ymk1blpYUW9KMHhGVGxOZlRVOUVSVXduS1NCdmNpQW5ZMnhoZFdSbExXOXdkWE10TkMw"
    "NEp3PT0ifSwgeyJmaWxlIjogInN0b3JlLnB5IiwgImEiOiAiSUNBZ0lDQWdJQ0FnSUNBZ2NtOTNJ"
    "RDBnWTI5dWJpNWxlR1ZqZFhSbEtBb2dJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0lsTkZURVZEVkNCcFpD"
    "QkdVazlOSUd4bFlXUnpJRmRJUlZKRklHUmxaSFZ3WDJ0bGVUMC9JaXdnS0dSbFpIVndYMnRsZVN3"
    "cEtTNW1aWFJqYUc5dVpTZ3BDaUFnSUNBZ0lDQWdJQ0FnSUhKbGRIVnliaUJwYm5Rb2NtOTNXeUpw"
    "WkNKZEtTd2dSbUZzYzJVPSIsICJyIjogIklDQWdJQ0FnSUNBZ0lDQWdJeURRa3RDaTBKN1FvTkNl"
    "MEprZzBKN1FvdENTMEpYUW9pRFFsTkNlMEovUW1OQ2gwS3ZRa3RDUTBKWFFvaURRbXRDUTBLRFFv"
    "dENlMEtmUW10Q2pMQ0RRa0NEUW5kQ1ZJTkNmMEtEUW50Q2YwSkRRbE5DUTBKWFFvaTRLSUNBZ0lD"
    "QWdJQ0FnSUNBZ0l3b2dJQ0FnSUNBZ0lDQWdJQ0FqSURJMUxqQTRMakl3TWpZdUlNS3IwS0RRdnRH"
    "QjBZTFF1dEdBMExEUXZjSzdJTkMrMFlMUXN0QzEwWUxRdU5DN0lOQzAwTExRc05DMjBMVFJpem9n"
    "MFlIUXY5QzEwWURRc3RDd0lNS3IwTGpRdmRHQzBMWFJnTkMxMFlFZzBMSWdNZ29nSUNBZ0lDQWdJ"
    "Q0FnSUNBaklOQzYwTDdRdk5DLzBZRFF0ZEdCMFlIUXZ0R0EwTERSaGNLN0xDRFJoOUMxMFlEUXRk"
    "QzNJTkMvMFkvUmd0R01JTkdIMExEUmdkQyswTElnNG9DVUlNS3IwSnpRdGRHRjBMRFF2ZEM0MExv"
    "ZzBKRFF1OUMxMExyUmdkQ3cwTDNRdE5HQUNpQWdJQ0FnSUNBZ0lDQWdJQ01nS3pjZ09UQTVJRGM0"
    "TmpVZ016YzV3cnN1SU5DUzBZTFF2dEdBMEw3UXVTRFF2dEdDMExMUXRkR0NJTkdEMEwvUmtkR0Ew"
    "WUhSanlEUXNpQlBUaUJEVDA1R1RFbERWQ0JFVHlCT1QxUklTVTVIQ2lBZ0lDQWdJQ0FnSUNBZ0lD"
    "TWcwTGdnMEwzUXRTRFF0TkMrMExYUmhkQ3cwTHM2SU5DeUlOQzYwTERSZ05HQzBMN1JoOUM2MExV"
    "ZzBMN1JnZEdDMExEUXU5R0IwWThnMFlMUXZ0QzcwWXpRdXRDK0lOQy8wTFhSZ05DeTBZdlF1U3dn"
    "MEwvUXZ0QzcwTFVnMFlMUXRkQzcwTFhSaE5DKzBMM1FzQW9nSUNBZ0lDQWdJQ0FnSUNBaklOQy8w"
    "WVBSZ2RHQzBMN1F0UzRnMEovUmdOQyswTFRRc05DeTBMWFJoaURRc3RDNDBMVFF0ZEM3SU1LcjBM"
    "alF2ZEdDMExYUmdOQzEwWUhRdmRDK3dyc2cwTGdnMEwzUXRTRFFzdEM0MExUUXRkQzdMQ0RRdXRD"
    "KzBMelJneURRdDlDeTBMN1F2ZEM0MFlMUmpDNEtJQ0FnSUNBZ0lDQWdJQ0FnSXdvZ0lDQWdJQ0Fn"
    "SUNBZ0lDQWpJTkNVMEw3UXY5QzQwWUhSaTlDeTBMRFF0ZEM4SU5HQjBMTFF0ZEdBMFlYUmd5QW8w"
    "WUhRc3RDMTBMYlF0ZEMxSU5DLzBMWFJnTkN5MFl2UXZDa3NJTkdDMExYUXU5QzEwWVRRdnRDOUlO"
    "R0IwWUxRc05DeTBMalF2Q3dnMExYUmdkQzcwTGdnMExYUXM5QytJTkM5MExVS0lDQWdJQ0FnSUNB"
    "Z0lDQWdJeURRc2RHTDBMdlF2aXdnMEx6UXRkR0MwTHJSZ3lEUXY5QyswTFRRdmRDNDBMelFzTkMx"
    "MEx3ZzBZTFF2dEM3MFl6UXV0QytJTkN5MExMUXRkR0EwWVVnMEwvUXZpRFFzdEN3MExiUXZkQysw"
    "WUhSZ3RDNExpRFFvZEdDMExEUmd0R0QwWUVnMEwzUXRRb2dJQ0FnSUNBZ0lDQWdJQ0FqSU5HQzBZ"
    "RFF2dEN6MExEUXRkQzhPaURRdXRDdzBZRFJndEMrMFlmUXV0R0RJTkM4MEw3UXN5RFFzdEMzMFkv"
    "Umd0R01JTkMrMEwvUXRkR0EwTERSZ3RDKzBZQXNJTkM0SU5HQjBMSFJnTkMrMFlIUXVOR0MwWXdn"
    "MExYUmtTRFFzaURDcTlDOTBMN1FzdEdEMFk3Q3V3b2dJQ0FnSUNBZ0lDQWdJQ0FqSU5DMzBMM1Fz"
    "TkdIMExqUmdpRFF2dEdDMEwzUmo5R0MwWXdnMFlNZzBMM1F0ZEN6MEw0ZzBZRFFzTkN4MEw3Umd0"
    "R0RMZ29nSUNBZ0lDQWdJQ0FnSUNCeWIzY2dQU0JqYjI1dUxtVjRaV04xZEdVb0NpQWdJQ0FnSUNB"
    "Z0lDQWdJQ0FnSUNBaVUwVk1SVU5VSUdsa0xDQnVaV1ZrTENCd2FHOXVaU3dnY21Wd2JIbGZhMmx1"
    "WkNCR1VrOU5JR3hsWVdSeklDSUtJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0lDSWdWMGhGVWtVZ1pHVmtk"
    "WEJmYTJWNVBUOGlMQ0FvWkdWa2RYQmZhMlY1TENrcExtWmxkR05vYjI1bEtDa0tJQ0FnSUNBZ0lD"
    "QWdJQ0FnYkdWaFpGOXBaQ0E5SUdsdWRDaHliM2RiSW1sa0lsMHBDaUFnSUNBZ0lDQWdJQ0FnSU5D"
    "OTBMN1FzdEdMMExsZjBZTFF0ZEM2MFlIUmdpQTlJSE4wY2lodVpXVmtJRzl5SUNJaUtTNXpkSEpw"
    "Y0NncENpQWdJQ0FnSUNBZ0lDQWdJTkMvMFlEUXRkQzIwTDNRdU5DNUlEMGdjM1J5S0hKdmQxc2li"
    "bVZsWkNKZElHOXlJQ0lpS1FvZ0lDQWdJQ0FnSUNBZ0lDRFF0TkMrMEwvUXVOR0IwTERSZ3RHTUlE"
    "MGdLTkM5MEw3UXN0R0wwTGxmMFlMUXRkQzYwWUhSZ2lCaGJtUWcwTDNRdnRDeTBZdlF1Vi9SZ3RD"
    "MTBMclJnZEdDSUc1dmRDQnBiaURRdjlHQTBMWFF0dEM5MExqUXVTa0tJQ0FnSUNBZ0lDQWdJQ0Fn"
    "YVdZZzBMVFF2dEMvMExqUmdkQ3cwWUxSakRvS0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnSU5HQjBMTFF2"
    "dEMwSUQwZ0tOQzkwTDdRc3RHTDBMbGYwWUxRdGRDNjBZSFJnaUFySUNKY2JseHVMUzB0SU5DLzBZ"
    "RFF0ZEMwMFl2UXROR0QwWW5RdU5DNUlOQyswWUxRc3RDMTBZSWdMUzB0WEc0aUlDc2cwTC9SZ05D"
    "MTBMYlF2ZEM0MExrcFd6bzJNREF3WFFvZ0lDQWdJQ0FnSUNBZ0lDQmxiSE5sT2dvZ0lDQWdJQ0Fn"
    "SUNBZ0lDQWdJQ0FnMFlIUXN0QyswTFFnUFNEUXY5R0EwTFhRdHRDOTBMalF1UW9nSUNBZ0lDQWdJ"
    "Q0FnSUNEUXN0QzEwWUVnUFNCN0ltaHZkQ0k2SURVc0lDSnBiblJsY21WemRHVmtJam9nTkN3Z0lu"
    "SmxaR2x5WldOMElqb2dNeXdnSW1SbFptVnljbVZrSWpvZ015d0tJQ0FnSUNBZ0lDQWdJQ0FnSUNB"
    "Z0lDQWdJQ0p1WlhWMGNtRnNJam9nTWl3Z0luZHliMjVuWDJOdmJuUmhZM1FpT2lBeUxDQWlZWFYw"
    "YjE5eVpYQnNlU0k2SURFc0NpQWdJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0lDQWlibTkwWDJsdWRHVnla"
    "WE4wWldRaU9pQXhmUW9nSUNBZ0lDQWdJQ0FnSUNEUXZOQzEwWUxRdXRDd0lEMGdjbTkzV3lKeVpY"
    "QnNlVjlyYVc1a0lsMEtJQ0FnSUNBZ0lDQWdJQ0FnYVdZZ2NtVndiSGxmYTJsdVpDQmhibVFnMExM"
    "UXRkR0JMbWRsZENoemRISW9jbVZ3YkhsZmEybHVaQ2tzSURBcElENGcwTExRdGRHQkxtZGxkQ2h6"
    "ZEhJbzBMelF0ZEdDMExyUXNDa3NJREFwT2dvZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnMEx6UXRkR0Mw"
    "THJRc0NBOUlISmxjR3g1WDJ0cGJtUUtJQ0FnSUNBZ0lDQWdJQ0FnMFlMUXRkQzcwTFhSaE5DKzBM"
    "MGdQU0J5YjNkYkluQm9iMjVsSWwwZ2IzSWdjR2h2Ym1VS0lDQWdJQ0FnSUNBZ0lDQWdhV1lnMExU"
    "UXZ0Qy8wTGpSZ2RDdzBZTFJqQ0J2Y2lEUmd0QzEwTHZRdGRHRTBMN1F2U0FoUFNCeWIzZGJJbkJv"
    "YjI1bElsMGdiM0lnMEx6UXRkR0MwTHJRc0NBaFBTQnliM2RiSW5KbGNHeDVYMnRwYm1RaVhUb0tJ"
    "Q0FnSUNBZ0lDQWdJQ0FnSUNBZ0lHTnZibTR1WlhobFkzVjBaU2dLSUNBZ0lDQWdJQ0FnSUNBZ0lD"
    "QWdJQ0FnSUNBaVZWQkVRVlJGSUd4bFlXUnpJRk5GVkNCdVpXVmtQVDhzSUhCb2IyNWxQVDhzSUhK"
    "bGNHeDVYMnRwYm1ROVB5d2dJZ29nSUNBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnSUNJZ0lDQWdJQ0Fn"
    "ZG1WeWMybHZiajEyWlhKemFXOXVLekVzSUhWd1pHRjBaV1JmWVhROVB5QlhTRVZTUlNCcFpEMC9J"
    "aXdLSUNBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0FnSUNBbzBZSFFzdEMrMExRc0lOR0MwTFhRdTlDMTBZ"
    "VFF2dEM5TENEUXZOQzEwWUxRdXRDd0xDQnViM2RmYVhOdkxDQnNaV0ZrWDJsa0tTa0tJQ0FnSUNB"
    "Z0lDQWdJQ0FnSUNBZ0lHTnZibTR1WlhobFkzVjBaU2dLSUNBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0Fn"
    "SUNBaVNVNVRSVkpVSUVsT1ZFOGdiR1ZoWkY5bGRtVnVkSE1nS0d4bFlXUmZhV1FzSUdGamRHbHZi"
    "aXdnWTNKbFlYUmxaRjloZENrZ0lnb2dJQ0FnSUNBZ0lDQWdJQ0FnSUNBZ0lDQWdJQ0pXUVV4VlJW"
    "TWdLRDhzSUNmUXROQyswTC9RdU5HQjBMRFF2U0RRdnRHQzBMTFF0ZEdDSnl3Z1B5a2lMQ0FvYkdW"
    "aFpGOXBaQ3dnYm05M1gybHpieWtwQ2lBZ0lDQWdJQ0FnSUNBZ0lISmxkSFZ5YmlCc1pXRmtYMmxr"
    "TENCR1lXeHpaUT09In1dfQ==")

груз = json.loads(base64.b64decode(ГРУЗ_B64).decode("utf-8"))
тексты = {}
for п in груз["patches"]:
    путь = os.path.join(КОРЕНЬ, п["file"])
    т = io.open(путь, encoding="utf-8").read()
    якорь = base64.b64decode(п["a"]).decode("utf-8")
    замена = base64.b64decode(п["r"]).decode("utf-8")
    if "ВТОРОЙ ОТВЕТ ДОПИСЫВАЕТ" in т or "МОДЕЛЬ ЛИНЗЫ - РУБИЛЬНИКОМ" in т:
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
