# -*- coding: utf-8 -*-
"""Довезти копию отправленного письма в «Отправленные» самого ящика.

Владелец 25.08: «когда я пишу ответ, этого ответа нету в ящике» — и в итоге
отвечал руками из веб-почты. SMTP копии у отправителя не оставляет, IMAP
APPEND в проекте не звался нигде: замер живьём дал у
v.melnikov@kompressor-air-expert.ru два письма в «Отправленных» против
четырнадцати ушедших за тот же день по базе.

Везём два куска: новый модуль v_otpravlennye.py целиком (на сервере его
нет, конфликтовать не с чем) и правку send_reply по якорям. Каталог
C:\\sender\\sender делят несколько сессий — .bak, py_compile, откат при сбое.

    pl_run.py kopiya_v_otpravlennye.py            # вхолостую
    pl_run.py kopiya_v_otpravlennye.py primenit   # применить
"""
import base64
import io
import os
import py_compile
import shutil
import sys
import time

КОРЕНЬ = r"C:\sender\sender"
ПРИМЕНИТЬ = "primenit" in sys.argv[1:]

МОДУЛЬ_B64 = (
    "IyAtKi0gY29kaW5nOiB1dGYtOCAtKi0KIiIi0JrQu9Cw0YHRgtGMINC60L7Qv9C40Y4g0L7RgtC/"
    "0YDQsNCy0LvQtdC90L3QvtCz0L4g0L/QuNGB0YzQvNCwINCyINC/0LDQv9C60YMgwqvQntGC0L/R"
    "gNCw0LLQu9C10L3QvdGL0LXCuyDRgdCw0LzQvtCz0L4g0Y/RidC40LrQsC4KCtCf0J7Qp9CV0JzQ"
    "oyDQrdCi0J4g0J3Qo9CW0J3Qni4gU01UUCDQtNC+0YHRgtCw0LLQu9GP0LXRgiDQv9C40YHRjNC8"
    "0L4g0L/QvtC70YPRh9Cw0YLQtdC70Y4g0Lgg0J3QmNCn0JXQk9CeINC90LUg0L7RgdGC0LDQstC7"
    "0Y/QtdGCINGDCtC+0YLQv9GA0LDQstC40YLQtdC70Y86INC60L7Qv9C40Y4g0LIgwqvQntGC0L/R"
    "gNCw0LLQu9C10L3QvdGL0LXCuyDQutC70LDQtNGR0YIg0LLQtdCxLdC40L3RgtC10YDRhNC10LnR"
    "gSDQv9C+0YfRgtC+0LLQuNC60LAsINC60L7Qs9C00LAK0L/QuNGI0LXRiNGMINC+0YLRgtGD0LTQ"
    "sC4g0JzRiyDRiNC70ZHQvCDQvNC40LzQviDQstC10LEt0LjQvdGC0LXRgNGE0LXQudGB0LAg4oCU"
    "INC30L3QsNGH0LjRgiDQsiDRj9GJ0LjQutC1INC90LDRiNC10LPQviDQv9C40YHRjNC80LAK0L3Q"
    "tdGCINCy0L7QstGB0LUuCgrQodCb0KPQp9CQ0JkgMjUuMDguMjAyNi4g0JLQu9Cw0LTQtdC70LXR"
    "hjogwqvQutC+0LPQtNCwINGPINC/0LjRiNGDINC+0YLQstC10YIsINGN0YLQvtCz0L4g0L7RgtCy"
    "0LXRgtCwINC90LXRgtGDINCyCtGP0YnQuNC60LXCuywg0Lgg0LIg0LjRgtC+0LPQtSDQt9Cw0YjR"
    "kdC7INCyINGP0YnQuNC60Lgg0YDRg9C60LDQvNC4LiDQl9Cw0LzQtdGAINC20LjQstGM0ZHQvDog"
    "0YMKdi5tZWxuaWtvdkBrb21wcmVzc29yLWFpci1leHBlcnQucnUg0LIgwqvQntGC0L/RgNCw0LLQ"
    "u9C10L3QvdGL0YXCuyDQtNCy0LAg0L/QuNGB0YzQvNCwLCDQsCDQv9C+INCx0LDQt9C1CtGBINC9"
    "0LXQs9C+INC30LAg0YLQvtGCINC00LXQvdGMINGD0YjQu9C+INGH0LXRgtGL0YDQvdCw0LTRhtCw"
    "0YLRjC4g0J7Qv9C10YDQsNGC0L7RgCDQvtGC0LLQtdGH0LDQtdGCINC60LvQuNC10L3RgtGDINC4"
    "INC90LUg0LLQuNC00LjRggrRgdCy0L7QtdCz0L4g0L7RgtCy0LXRgtCwINGC0LDQvCwg0LPQtNC1"
    "INC/0YDQuNCy0YvQuiDRgdC80L7RgtGA0LXRgtGMOyDQutC70LjQtdC90YIg0L/QvtGC0L7QvCDQ"
    "vtGC0LLQtdGH0LDQtdGCINC90LAg0L/QuNGB0YzQvNC+LArQutC+0YLQvtGA0L7Qs9C+INCyINGP"
    "0YnQuNC60LUg0L3QtdGCLCDQuCDQstC10YLQutCwINCyINC/0L7Rh9GC0L7QstC40LrQtSDRgNCy"
    "0ZHRgtGB0Y8uCgrQmNCc0K8g0J/QkNCf0JrQmCDQndCVINCj0JPQkNCU0KvQktCQ0JXQnC4g0KMg"
    "0K/QvdC00LXQutGB0LAg0L7QvdCwINC/0YDQuNGF0L7QtNC40YIg0LrQsNC6CsKrJkJCNEVRZ1Es"
    "QkVBRU1BUXlCRHNFTlFROUJEMEVTd1ExLcK7IOKAlCDRjdGC0L4gwqvQntGC0L/RgNCw0LLQu9C1"
    "0L3QvdGL0LXCuyDQsiDQvNC+0LTQuNGE0LjRhtC40YDQvtCy0LDQvdC90L7QvApVVEYtNywg0LrQ"
    "vtC00LXQutCwINC00LvRjyDQutC+0YLQvtGA0L7Qs9C+INCyINGB0YLQsNC90LTQsNGA0YLQvdC+"
    "0Lkg0LHQuNCx0LvQuNC+0YLQtdC60LUg0L3QtdGCLiDQn9C+0Y3RgtC+0LzRgyDQuNGJ0LXQvCDQ"
    "v9C+CtGE0LvQsNCz0YMgXFxTZW50INC40Lcg0L7RgtCy0LXRgtCwIExJU1QsINC4INGC0L7Qu9GM"
    "0LrQviDQtdGB0LvQuCDQtdCz0L4g0L3QtdGCIOKAlCDQv9C+INC30L3QsNC60L7QvNGL0Lwg0LjQ"
    "vNC10L3QsNC8LgoK0J3QmNCa0J7Qk9CU0JAg0J3QlSDQoNCe0J3Qr9CV0KIg0J7QotCf0KDQkNCS"
    "0JrQoy4g0J/QuNGB0YzQvNC+INC6INGN0YLQvtC80YMg0LzQuNCz0YMg0YPQttC1INGD0YjQu9C+"
    "OyDQvdC10YPQtNCw0YfQvdCw0Y8g0LrQvtC/0LjRjyDigJQK0Y3RgtC+INC90LXRg9C00L7QsdGB"
    "0YLQstC+LCDQsCDQvdC1INC/0L7RgtC10YDRjy4g0JLRgdC1INC+0YjQuNCx0LrQuCDQs9C70YPR"
    "iNC40Lwg0LfQtNC10YHRjCDQuCDQstC+0LfQstGA0LDRidCw0LXQvCBGYWxzZS4KIiIiCmZyb20g"
    "X19mdXR1cmVfXyBpbXBvcnQgYW5ub3RhdGlvbnMKCmltcG9ydCBiYXNlNjQKaW1wb3J0IGltYXBs"
    "aWIKaW1wb3J0IGxvZ2dpbmcKaW1wb3J0IG9zCmltcG9ydCByZQpmcm9tIGRhdGV0aW1lIGltcG9y"
    "dCBkYXRldGltZSwgdGltZXpvbmUKZnJvbSB0eXBpbmcgaW1wb3J0IEFueSwgT3B0aW9uYWwKCmxv"
    "Z2dlciA9IGxvZ2dpbmcuZ2V0TG9nZ2VyKF9fbmFtZV9fKQoKX9CX0J3QkNCa0J7QnNCr0JUgPSAo"
    "ItC+0YLQv9GA0LDQstC70LXQvdC90YvQtSIsICJzZW50IiwgInNlbnQgaXRlbXMiLCAic2VudCBt"
    "ZXNzYWdlcyIpCgoKZGVmIGRla29kaXJvdmF0KGlteWE6IHN0cikgLT4gc3RyOgogICAgIiIi0JjQ"
    "vNGPINC/0LDQv9C60LggSU1BUCDQuNC3INC80L7QtNC40YTQuNGG0LjRgNC+0LLQsNC90L3QvtCz"
    "0L4gVVRGLTcg0LIg0L7QsdGL0YfQvdGD0Y4g0YHRgtGA0L7QutGDLiIiIgogICAg0LLRi9GFOiBs"
    "aXN0W3N0cl0gPSBbXQogICAg0LHRg9GE0LXRgCA9ICIiCiAgICDQstC90YPRgtGA0LggPSBGYWxz"
    "ZQogICAgZm9yINGB0LjQvCBpbiBzdHIoaW15YSBvciAiIik6CiAgICAgICAgaWYg0LLQvdGD0YLR"
    "gNC4OgogICAgICAgICAgICBpZiDRgdC40LwgPT0gIi0iOgogICAgICAgICAgICAgICAgaWYg0LHR"
    "g9GE0LXRgDoKICAgICAgICAgICAgICAgICAgICDQsSA9INCx0YPRhNC10YAucmVwbGFjZSgiLCIs"
    "ICIvIikKICAgICAgICAgICAgICAgICAgICDQsSArPSAiPSIgKiAoKDQgLSBsZW4o0LEpICUgNCkg"
    "JSA0KQogICAgICAgICAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgICAgICAgICAg0LLR"
    "i9GFLmFwcGVuZChiYXNlNjQuYjY0ZGVjb2RlKNCxKS5kZWNvZGUoInV0Zi0xNi1iZSIpKQogICAg"
    "ICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246ICAjIG5vcWE6IEJMRTAwMSAtINC80YPR"
    "gdC+0YAg0L7RgdGC0LDQstC70Y/QtdC8INC60LDQuiDQtdGB0YLRjAogICAgICAgICAgICAgICAg"
    "ICAgICAgICDQstGL0YUuYXBwZW5kKCImIiArINCx0YPRhNC10YAgKyAiLSIpCiAgICAgICAgICAg"
    "ICAgICBlbHNlOgogICAgICAgICAgICAgICAgICAgINCy0YvRhS5hcHBlbmQoIiYiKQogICAgICAg"
    "ICAgICAgICAg0LHRg9GE0LXRgCwg0LLQvdGD0YLRgNC4ID0gIiIsIEZhbHNlCiAgICAgICAgICAg"
    "IGVsc2U6CiAgICAgICAgICAgICAgICDQsdGD0YTQtdGAICs9INGB0LjQvAogICAgICAgIGVsaWYg"
    "0YHQuNC8ID09ICImIjoKICAgICAgICAgICAg0LLQvdGD0YLRgNC4ID0gVHJ1ZQogICAgICAgIGVs"
    "c2U6CiAgICAgICAgICAgINCy0YvRhS5hcHBlbmQo0YHQuNC8KQogICAgaWYg0LLQvdGD0YLRgNC4"
    "OiAgICAgICAgICAgICAgICAgICAgICAjINC+0LHQvtGA0LLQsNC90L3QsNGPINC/0L7RgdC70LXQ"
    "tNC+0LLQsNGC0LXQu9GM0L3QvtGB0YLRjAogICAgICAgINCy0YvRhS5hcHBlbmQoIiYiICsg0LHR"
    "g9GE0LXRgCkKICAgIHJldHVybiAiIi5qb2luKNCy0YvRhSkKCgpkZWYgX3Jhem9icmF0X2xpc3Qo"
    "0YHRgtGA0L7QutCwOiBBbnkpIC0+IHR1cGxlW3N0ciwgc3RyXToKICAgICIiItCh0YLRgNC+0LrQ"
    "sCDQvtGC0LLQtdGC0LAgTElTVCAtPiAo0YTQu9Cw0LPQuCwg0LjQvNGPINC/0LDQv9C60Lgg0LrQ"
    "sNC6INC10LPQviDQv9C+0L3QuNC80LDQtdGCINGB0LXRgNCy0LXRgCkuIiIiCiAgICDRgiA9INGB"
    "0YLRgNC+0LrQsC5kZWNvZGUoInV0Zi04IiwgInJlcGxhY2UiKSBpZiBpc2luc3RhbmNlKNGB0YLR"
    "gNC+0LrQsCwgYnl0ZXMpIGVsc2Ugc3RyKNGB0YLRgNC+0LrQsCkKICAgINC8ID0gcmUubWF0Y2go"
    "cideXCgoP1A80YTQuz5bXildKilcKVxzKyg/OiJbXiJdKiJ8TklMKVxzKyg/UDzQuNC80Y8+Lisp"
    "JCcsINGCLnN0cmlwKCkpCiAgICBpZiBub3Qg0Lw6CiAgICAgICAgcmV0dXJuICIiLCAiIgogICAg"
    "0LjQvNGPID0g0LwuZ3JvdXAoItC40LzRjyIpLnN0cmlwKCkKICAgIGlmINC40LzRjy5zdGFydHN3"
    "aXRoKCciJykgYW5kINC40LzRjy5lbmRzd2l0aCgnIicpOgogICAgICAgINC40LzRjyA9INC40LzR"
    "j1sxOi0xXQogICAgcmV0dXJuINC8Lmdyb3VwKCLRhNC7IikubG93ZXIoKSwg0LjQvNGPCgoKZGVm"
    "IG5heXRpX3BhcGt1KGltYXA6IEFueSkgLT4gT3B0aW9uYWxbc3RyXToKICAgICIiItCf0LDQv9C6"
    "0LAgwqvQntGC0L/RgNCw0LLQu9C10L3QvdGL0LXCuzog0YHQv9C10YDQstCwINC/0L4g0YTQu9Cw"
    "0LPRgyBcXFNlbnQsINC/0L7RgtC+0Lwg0L/QviDQuNC80LXQvdC4LiIiIgogICAgdHJ5OgogICAg"
    "ICAgINGC0LjQvywg0LTQsNC90L3Ri9C1ID0gaW1hcC5saXN0KCkKICAgIGV4Y2VwdCBFeGNlcHRp"
    "b246ICAjIG5vcWE6IEJMRTAwMQogICAgICAgIHJldHVybiBOb25lCiAgICBpZiDRgtC40L8gIT0g"
    "Ik9LIiBvciBub3Qg0LTQsNC90L3Ri9C1OgogICAgICAgIHJldHVybiBOb25lCiAgICDQv9C+X9C4"
    "0LzQtdC90LggPSBOb25lCiAgICBmb3Ig0YHRgtGA0L7QutCwIGluINC00LDQvdC90YvQtToKICAg"
    "ICAgICDRhNC70LDQs9C4LCDQuNC80Y8gPSBfcmF6b2JyYXRfbGlzdCjRgdGC0YDQvtC60LApCiAg"
    "ICAgICAgaWYgbm90INC40LzRjzoKICAgICAgICAgICAgY29udGludWUKICAgICAgICBpZiAiXFxz"
    "ZW50IiBpbiDRhNC70LDQs9C4OgogICAgICAgICAgICByZXR1cm4g0LjQvNGPCiAgICAgICAgaWYg"
    "0L/Qvl/QuNC80LXQvdC4IGlzIE5vbmUgYW5kIGRla29kaXJvdmF0KNC40LzRjykuc3RyaXAoKS5s"
    "b3dlcigpIGluIF/Ql9Cd0JDQmtCe0JzQq9CVOgogICAgICAgICAgICDQv9C+X9C40LzQtdC90Lgg"
    "PSDQuNC80Y8KICAgIHJldHVybiDQv9C+X9C40LzQtdC90LgKCgpkZWYgcG9sb3poaXQobWJfY2Zn"
    "OiBBbnksIG1pbWVfYnl0ZXM6IGJ5dGVzLCAqLCBrb2dkYTogT3B0aW9uYWxbZGF0ZXRpbWVdID0g"
    "Tm9uZSwKICAgICAgICAgICAgIHRpbWVvdXQ6IGZsb2F0ID0gMjAuMCwgb3BlbmVyOiBBbnkgPSBO"
    "b25lKSAtPiBib29sOgogICAgIiIi0J/QvtC70L7QttC40YLRjCDQv9C40YHRjNC80L4g0LIgwqvQ"
    "ntGC0L/RgNCw0LLQu9C10L3QvdGL0LXCuyDRj9GJ0LjQutCwLiBUcnVlIOKAlCDQu9C10LPQu9C+"
    "LgoKICAgIG9wZW5lciDQvdGD0LbQtdC9INGC0LXRgdGC0LDQvDog0LHQtdC3INC90LXQs9C+INC+"
    "0YLQutGA0YvQstCw0LXQvCDQvdCw0YHRgtC+0Y/RidC10LUgSU1BUDRfU1NMLdGB0L7QtdC00LjQ"
    "vdC10L3QuNC1LgogICAgIiIiCiAgICDQv9Cw0YDQvtC70YwgPSBvcy5nZXRlbnYoZ2V0YXR0ciht"
    "Yl9jZmcsICJwYXNzd29yZF9lbnYiLCAiIikgb3IgIiIsICIiKQogICAgaWYgbm90INC/0LDRgNC+"
    "0LvRjDoKICAgICAgICBsb2dnZXIud2FybmluZygi0LrQvtC/0LjRjyDQsiDQvtGC0L/RgNCw0LLQ"
    "u9C10L3QvdGL0LU6INC90LXRgiDQv9Cw0YDQvtC70Y8gJXMiLAogICAgICAgICAgICAgICAgICAg"
    "ICAgIGdldGF0dHIobWJfY2ZnLCAicGFzc3dvcmRfZW52IiwgIj8iKSkKICAgICAgICByZXR1cm4g"
    "RmFsc2UKICAgIGltYXAgPSBOb25lCiAgICB0cnk6CiAgICAgICAgaWYgb3BlbmVyIGlzIG5vdCBO"
    "b25lOgogICAgICAgICAgICBpbWFwID0gb3BlbmVyKG1iX2NmZykKICAgICAgICBlbHNlOgogICAg"
    "ICAgICAgICBpbWFwID0gaW1hcGxpYi5JTUFQNF9TU0wobWJfY2ZnLmltYXBfaG9zdCwgbWJfY2Zn"
    "LmltYXBfcG9ydCwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHRpbWVvdXQ9"
    "dGltZW91dCkKICAgICAgICAgICAgaW1hcC5sb2dpbihtYl9jZmcubG9naW4sINC/0LDRgNC+0LvR"
    "jCkKICAgICAgICDQv9Cw0L/QutCwID0gbmF5dGlfcGFwa3UoaW1hcCkKICAgICAgICBpZiBub3Qg"
    "0L/QsNC/0LrQsDoKICAgICAgICAgICAgbG9nZ2VyLndhcm5pbmcoItC60L7Qv9C40Y8g0LIg0L7R"
    "gtC/0YDQsNCy0LvQtdC90L3Ri9C1OiDQv9Cw0L/QutCwINC90LUg0L3QsNC50LTQtdC90LAg0YMg"
    "JXMiLAogICAgICAgICAgICAgICAgICAgICAgICAgICBnZXRhdHRyKG1iX2NmZywgIm1haWxib3hf"
    "aWQiLCAiPyIpKQogICAgICAgICAgICByZXR1cm4gRmFsc2UKICAgICAgICDQutC+0LPQtNCwID0g"
    "a29nZGEgb3IgZGF0ZXRpbWUubm93KHRpbWV6b25lLnV0YykKICAgICAgICDRgtC40L8sIF8gPSBp"
    "bWFwLmFwcGVuZCjQv9Cw0L/QutCwLCAiXFxTZWVuIiwKICAgICAgICAgICAgICAgICAgICAgICAg"
    "ICAgICBpbWFwbGliLlRpbWUySW50ZXJuYWxkYXRlKNC60L7Qs9C00LAudGltZXN0YW1wKCkpLAog"
    "ICAgICAgICAgICAgICAgICAgICAgICAgICAgIG1pbWVfYnl0ZXMpCiAgICAgICAgaWYg0YLQuNC/"
    "ICE9ICJPSyI6CiAgICAgICAgICAgIGxvZ2dlci53YXJuaW5nKCLQutC+0L/QuNGPINCyINC+0YLQ"
    "v9GA0LDQstC70LXQvdC90YvQtTogQVBQRU5EINCy0LXRgNC90YPQuyAlcyIsINGC0LjQvykKICAg"
    "ICAgICAgICAgcmV0dXJuIEZhbHNlCiAgICAgICAgcmV0dXJuIFRydWUKICAgIGV4Y2VwdCBFeGNl"
    "cHRpb246ICAjIG5vcWE6IEJMRTAwMSAtINC/0LjRgdGM0LzQviDRg9C20LUg0YPRiNC70L4sINC6"
    "0L7Qv9C40Y8g0L3QtSDRgdC80LXQtdGCINGA0L7QvdGP0YLRjAogICAgICAgIGxvZ2dlci5leGNl"
    "cHRpb24oItC60L7Qv9C40Y8g0LIg0L7RgtC/0YDQsNCy0LvQtdC90L3Ri9C1INC90LUg0LvQtdCz"
    "0LvQsCAoJXMpIiwKICAgICAgICAgICAgICAgICAgICAgICAgIGdldGF0dHIobWJfY2ZnLCAibWFp"
    "bGJveF9pZCIsICI/IikpCiAgICAgICAgcmV0dXJuIEZhbHNlCiAgICBmaW5hbGx5OgogICAgICAg"
    "IGlmIGltYXAgaXMgbm90IE5vbmU6CiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIGlt"
    "YXAubG9nb3V0KCkKICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogICMgbm9xYTogQkxFMDAx"
    "CiAgICAgICAgICAgICAgICBwYXNzCg==")


ЯКОРЬ_ИМПОРТ = ("from sender.vne_bazy import razreshena as "
                "razreshena_vne_bazy  # noqa: E402")
ЗАМЕНА_ИМПОРТ = ("from sender.v_otpravlennye import polozhit as "
                 "polozhit_v_otpravlennye  # noqa: E402\n" + ЯКОРЬ_ИМПОРТ)

ЯКОРЬ_ТЕЛО = """        self._deliver(mb, mb.mailbox_id, to_email, mime_bytes)

        sent_at = datetime.now(timezone.utc)"""
ЗАМЕНА_ТЕЛО = """        self._deliver(mb, mb.mailbox_id, to_email, mime_bytes)

        sent_at = datetime.now(timezone.utc)
        # КОПИЯ В «ОТПРАВЛЕННЫЕ» САМОГО ЯЩИКА. SMTP копии у отправителя не
        # оставляет — её кладёт веб-интерфейс почтовика, когда пишешь оттуда.
        # Владелец 25.08: «когда я пишу ответ, этого ответа нету в ящике», и
        # в итоге отвечал руками из веб-почты. Копия ничего не решает по
        # доставке и потому НИКОГДА не роняет отправку: polozhit глушит свои
        # ошибки сам и возвращает False.
        if self.config.get("imap.kopiya_otvetov_v_otpravlennye", True):
            polozhit_v_otpravlennye(mb, mime_bytes, kogda=sent_at)"""

путь_модуля = os.path.join(КОРЕНЬ, "v_otpravlennye.py")
путь_сендера = os.path.join(КОРЕНЬ, "sender.py")
текст = io.open(путь_сендера, encoding="utf-8").read()
есть_модуль = os.path.exists(путь_модуля)
print("модуль на сервере: %s" % ("есть" if есть_модуль else "нет"))
for имя, якорь in (("импорт", ЯКОРЬ_ИМПОРТ), ("тело send_reply", ЯКОРЬ_ТЕЛО)):
    print("якорь %s: %d раз" % (имя, текст.count(якорь)))
если_готово = ("polozhit_v_otpravlennye" in текст)
if если_готово:
    print("правка уже стоит — делать нечего")
    raise SystemExit(0)
if текст.count(ЯКОРЬ_ИМПОРТ) != 1 or текст.count(ЯКОРЬ_ТЕЛО) != 1:
    raise SystemExit("ОТМЕНА: якорь должен встречаться ровно один раз")
новый = текст.replace(ЯКОРЬ_ИМПОРТ, ЗАМЕНА_ИМПОРТ).replace(ЯКОРЬ_ТЕЛО, ЗАМЕНА_ТЕЛО)

if not ПРИМЕНИТЬ:
    print("\nвхолостую. Применить — primenit")
    raise SystemExit(0)

метка = time.strftime("%Y%m%d-%H%M%S")
записан = None
try:
    io.open(путь_модуля, "w", encoding="utf-8", newline="").write(
        base64.b64decode(МОДУЛЬ_B64).decode("utf-8"))
    py_compile.compile(путь_модуля, doraise=True)
    print("положен модуль: %s" % путь_модуля)
    shutil.copy2(путь_сендера, путь_сендера + ".bak-" + метка)
    io.open(путь_сендера, "w", encoding="utf-8", newline="").write(новый)
    записан = путь_сендера
    py_compile.compile(путь_сендера, doraise=True)
    print("правлен sender.py (копия .bak-%s)" % метка)
except Exception as e:  # noqa: BLE001
    print("СБОЙ: %s — откатываю" % e)
    if записан:
        shutil.copy2(записан + ".bak-" + метка, записан)
    if os.path.exists(путь_модуля) and not есть_модуль:
        os.remove(путь_модуля)
    raise
print("\nготово. Подхватится после Restart-Service SenderPanel -Force")
