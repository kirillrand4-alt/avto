# -*- coding: utf-8 -*-
"""Жалоба — это отчёт ARF, а не слово «спам» в тексте. Хирургически.

Катить: --katit
"""
import base64
import io
import json
import os
import py_compile
import sys
import time

Д = json.loads(base64.b64decode("eyJ3YXRjaGVyIjogIiAgICAjINCv0YnQuNC60Lgg0YHQu9GD0LbQsSDQttCw0LvQvtCxOiDQv9C40YHRjNC80L4g0L7RgiDQvdC40YUg4oCUINC20LDQu9C+0LHQsCDQvdC10LfQsNCy0LjRgdC40LzQviDQvtGCINGC0LXQutGB0YLQsC5cbiAgICBf0K/QqdCY0JrQmF/QltCQ0JvQntCRID0gZnJvemVuc2V0KHtcImFidXNlXCIsIFwiZmJsXCIsIFwiY29tcGxhaW50c1wiLCBcImZlZWRiYWNrXCIsXG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgICBcImFidXNlLXJlcG9ydFwiLCBcInNwYW0tcmVwb3J0XCJ9KVxuXG4gICAgZGVmIF9pc19jb21wbGFpbnQoc2VsZiwgbXNnOiBFbWFpbE1lc3NhZ2UsIHN1YmplY3Q6IHN0ciwgYm9keTogc3RyKSAtPiBib29sOlxuICAgICAgICBcIlwiXCLQltCw0LvQvtCx0LAg0L3QsCDRgdC/0LDQvCDigJQg0Y3RgtC+INCe0KLQp9CB0KIgKEFSRiksINCwINC90LUg0YHQu9C+0LLQviDCq9GB0L/QsNC8wrsg0LIg0YLQtdC60YHRgtC1LlxuXG4gICAgICAgINCg0LDQvdGM0YjQtSDQt9C00LXRgdGMINGB0YLQvtGP0Lsg0L/QvtC40YHQuiDQv9C+0LTRgdGC0YDQvtC6IGFidXNlfHNwYW18Y29tcGxhaW50fGZlZWRiYWNrLXR5cGVcbiAgICAgICAg0L/QviDRgtC10LzQtSDQuCDRgtC10LvRgywg0Lgg0Y3RgtC+0LPQviDRhdCy0LDRgtCw0LvQviwg0YfRgtC+0LHRiyDQv9C+0YXQvtGA0L7QvdC40YLRjCDQttC40LLRg9GOINC60L7QvNC/0LDQvdC40Y46XG4gICAgICAgIDI2LjA4INCf0JDQniDCq9Cb0YPQutC+0LnQu8K7INC90LDQv9C40YHQsNC70L4gwqvQtNCw0L3QvdGL0Lkg0LLQvtC/0YDQvtGBINC90LUg0L7RgtC90L7RgdC40YLRgdGPINC6XG4gICAgICAgINC60L7QvNC/0LXRgtC10L3RhtC40Lgg0YHQu9GD0LbQsdGLINGC0LXRhdC90LjRh9C10YHQutC+0Lkg0L/QvtC00LTQtdGA0LbQutC4wrsg0Lgg0L/QtdGA0LXRh9C40YHQu9C40LvQviDQotCg0Jgg0LTRgNGD0LPQuNGFXG4gICAgICAgINGB0LLQvtC40YUg0LDQtNGA0LXRgdCwLCDQsCDQsiDRgtC10LrRgdGC0LUg0LjRhSDQutC+0YDQv9C+0YDQsNGC0LjQstC90L7Qs9C+INCx0LDQvdC90LXRgNCwINC90LDRiNC70L7RgdGMINGB0LvQvtCy0L5cbiAgICAgICAgwqvRgdC/0LDQvMK7LiDQn9C40YHRjNC80L4g0YPRiNC70L4g0LIg0LbQsNC70L7QsdGLLCBhZHJlc3Mg0LDQstGC0L7QvNCw0YLQvtC8INC70ZHQsyDQsiDRgdGC0L7Qvy3Qu9C40YHRglxuICAgICAgICAoaW1hcC5hdXRvX3N1cHByZXNzX29uX2NvbXBsYWludCksINC60LDRgNGC0L7Rh9C60LAg0LvQuNC00LAg0L3QtSDQt9Cw0LLQtdC70LDRgdGMIC0g0LhcbiAgICAgICAg0LrQvtC80L/QsNC90LjQuCDRgSDQstGL0YDRg9GH0LrQvtC5INCyINGC0YDQuNC70LvQuNC+0L3RiyDQvNGLINCx0L7Qu9GM0YjQtSDQvdC1INC/0LjRiNC10Lwg0L3QuNC60L7Qs9C00LAuXG5cbiAgICAgICAg0J/RgNC40LfQvdCw0ZHQvCDQttCw0LvQvtCx0L7QuSDRgtC+0LvRjNC60L4g0LzQsNGI0LjQvdC90YvQtSDQv9GA0LjQt9C90LDQutC4OiDRhNC+0YDQvNCw0YIgQVJGLCDQt9Cw0LPQvtC70L7QstC+0LpcbiAgICAgICAg0L7RgtGH0ZHRgtCwINC40LvQuCDQv9C40YHRjNC80L4g0YHQviDRgdC70YPQttC10LHQvdC+0LPQviDRj9GJ0LjQutCwINC20LDQu9C+0LEuINCn0LXQu9C+0LLQtdC6LCDQvdCw0L/QuNGB0LDQstGI0LjQuVxuICAgICAgICDRgdC70L7QstC+IMKr0YHQv9Cw0LzCuywg0LbQsNC70L7QsdGLINC90LUg0L/QvtC00LDQstCw0LsuXG4gICAgICAgIFwiXCJcIlxuICAgICAgICBpZiBtc2cuZ2V0X2NvbnRlbnRfdHlwZSgpID09IFwibWVzc2FnZS9mZWVkYmFjay1yZXBvcnRcIjpcbiAgICAgICAgICAgIHJldHVybiBUcnVlXG4gICAgICAgIHRyeTpcbiAgICAgICAgICAgIGZvciDRh9Cw0YHRgtGMIGluIG1zZy53YWxrKCk6XG4gICAgICAgICAgICAgICAgaWYg0YfQsNGB0YLRjC5nZXRfY29udGVudF90eXBlKCkgPT0gXCJtZXNzYWdlL2ZlZWRiYWNrLXJlcG9ydFwiOlxuICAgICAgICAgICAgICAgICAgICByZXR1cm4gVHJ1ZVxuICAgICAgICBleGNlcHQgRXhjZXB0aW9uOiAgIyBub3FhOiBCTEUwMDEgLSDQutGA0LjQstC+0LkgTUlNRSDQvdC1INC00L7Qu9C20LXQvSDRgNC+0L3Rj9GC0Ywg0L/RgNC40ZHQvFxuICAgICAgICAgICAgcGFzc1xuICAgICAgICBpZiBtc2cuZ2V0KFwiRmVlZGJhY2stVHlwZVwiKSBvciBtc2cuZ2V0KFwiWC1BYnVzZS1SZXBvcnRcIik6XG4gICAgICAgICAgICByZXR1cm4gVHJ1ZVxuICAgICAgICDQv9C10YLQu9GPID0gc3RyKG1zZy5nZXQoXCJYLUxvb3BcIiwgXCJcIikgb3IgXCJcIikuc3RyaXAoKS5sb3dlcigpXG4gICAgICAgIGlmINC/0LXRgtC70Y8uc3RhcnRzd2l0aChcImFidXNlXCIpOlxuICAgICAgICAgICAgcmV0dXJuIFRydWVcbiAgICAgICAg0L7RgtC/0YDQsNCy0LjRgtC10LvRjCA9IHNlbGYuX2V4dHJhY3RfZW1haWwobXNnLmdldChcIkZyb21cIiwgXCJcIikgb3IgXCJcIilcbiAgICAgICAgaWYg0L7RgtC/0YDQsNCy0LjRgtC10LvRjC5zcGxpdChcIkBcIiwgMSlbMF0gaW4gc2VsZi5f0K/QqdCY0JrQmF/QltCQ0JvQntCROlxuICAgICAgICAgICAgcmV0dXJuIFRydWVcbiAgICAgICAgIyDQnNCw0YjQuNC90L3QsNGPINGH0LDRgdGC0YwgQVJGLCDQv9GA0LjQtdGF0LDQstGI0LDRjyDRgtC10LrRgdGC0L7QvC5cbiAgICAgICAgcmV0dXJuIFwiZmVlZGJhY2stdHlwZTpcIiBpbiAoYm9keSBvciBcIlwiKS5sb3dlcigpXG5cbiIsICJzbG92YW1pIjogIiAgICAjIDUuNy4xINC4IMKrYmxvY2tlZMK7IOKAlCDRjdGC0L4g0J/QntCb0JjQotCY0JrQkCDRgdC10YDQstC10YDQsCDQv9C+0LvRg9GH0LDRgtC10LvRjywg0LAg0L3QtSDQvdCw0LbQsNGC0LDRj1xuICAgICMg0LrQvdC+0L/QutCwIMKr0KHQv9Cw0LzCuzog0LrQvtGA0L/QvtGA0LDRgtC40LLQvdGL0Lkg0L/QtdGA0LjQvNC10YLRgCAocmVsYXkwMC5ha2tlcm1hbm4ucnUsXG4gICAgIyBoY29hdGluZ3MucnUpINGA0LXQttC10YIg0LLQvdC10YjQvdGO0Y4g0L/QvtGH0YLRgyDQvdCwINC/0L7QtNGF0L7QtNC1LiDQn9GA0LXQttC90Y/RjyDRhNC+0YDQvNGD0LvQuNGA0L7QstC60LBcbiAgICAjIMKr0L/QvtC70YPRh9Cw0YLQtdC70Ywg0L/RgNC40L3Rj9C7INC30LAg0YHQv9Cw0LzCuyDRh9C40YLQsNC70LDRgdGMINC60LDQuiDQv9C+0YHRgtGD0L/QvtC6INGH0LXQu9C+0LLQtdC60LAg0Lgg0L/Rg9Cz0LDQu9CwXG4gICAgIyDQt9GA0Y8uINCd0LDRgdGC0L7Rj9GJ0LjQuSDRgdC/0LDQvC3QstC10YDQtNC40LrRgiDQv9C+0YfRgtC+0LLQuNC60LAg0L7RgdGC0LDQstC70Y/QtdC8INC+0YLQtNC10LvRjNC90L7QuSDRgdGC0YDQvtC60L7QuS5cbiAgICAoclwiYmxhY2tsaXN0fGxpc3RlZCBpbnxkbnNibHxzcGFtaGF1c3xzcGFtLT9zY29yZXxcIlxuICAgICByXCLQv9GA0LjQt9C90LDQvVxcdyog0YHQv9Cw0LzQvtC8fGNsYXNzaWZpZWQgYXMgc3BhbVwiLFxuICAgICBcItC/0L7Rh9GC0L7QstC40Log0YHRh9GR0Lsg0L/QuNGB0YzQvNC+INGB0L/QsNC80L7QvFwiKSxcbiAgICAoclwiNVxcLjdcXC4xfGJsb2NrZWR8c2VjdXJpdHkgcmVhc29ufHBvbGljeSByZWplY3Rpb25cIixcbiAgICAgXCLRgdC10YDQstC10YAg0L/QvtC70YPRh9Cw0YLQtdC70Y8g0L7RgtC60LvQvtC90LjQuyDQv9C+INGB0LLQvtC40Lwg0L/RgNCw0LLQuNC70LDQvFwiKSxcbiJ9").decode("utf-8"))
КАТИТЬ = "--katit" in sys.argv

W = r"C:\sender\sender\imap_watcher.py"
S = r"C:\sender\sender\sobytiya_slovami.py"

СТАРОЕ_W = '''    def _is_complaint(self, msg: EmailMessage, subject: str, body: str) -> bool:
        content_type = msg.get_content_type()
        if content_type == "message/feedback-report":
            return True
        complaint_markers = ["abuse", "spam", "complaint", "feedback-type"]
        text = (subject + " " + body).lower()
        return any(marker in text for marker in complaint_markers)'''

СТАРОЕ_S = '''    (r"spam|5\\.7\\.1|blacklist|blocked", "получатель принял за спам"),'''


def правка(путь, старое, новое, метка):
    имя = os.path.basename(путь)
    т = io.open(путь, encoding="utf-8").read()
    if метка in т:
        print("%-22s правка уже стоит" % имя)
        return
    n = т.count(старое)
    print("%-22s якорь найден раз: %d" % (имя, n))
    if n != 1:
        raise SystemExit("якорь должен быть ровно один")
    новый = т.replace(старое, новое)
    if not КАТИТЬ:
        print("   сухой прогон: %d -> %d знаков" % (len(т), len(новый)))
        return
    копия = "%s.bak-%d" % (путь, int(time.time()))
    io.open(копия, "w", encoding="utf-8", newline="").write(т)
    with io.open(путь, "w", encoding="utf-8", newline="") as f:
        f.write(новый)
        f.flush()
        os.fsync(f.fileno())
    py_compile.compile(путь, doraise=True)
    print("   поставлен %s (.bak %s)" % (имя, os.path.basename(копия)))


правка(W, СТАРОЕ_W, Д["watcher"].rstrip("\n"), "_ЯЩИКИ_ЖАЛОБ")
правка(S, СТАРОЕ_S, Д["slovami"].rstrip("\n"), "отклонил по своим правилам")
if not КАТИТЬ:
    print("\nсухой прогон. Катить: --katit")
