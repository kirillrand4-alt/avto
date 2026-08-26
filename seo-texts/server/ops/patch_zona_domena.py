# -*- coding: utf-8 -*-
"""Привязка ответа из другой зоны того же домена. Хирургически, --katit."""
import base64
import io
import json
import os
import py_compile
import sys
import time

Д = json.loads(base64.b64decode("eyJtZXRvZCI6ICIgICAgIyDQlNC+0LzQtdC90Ysg0LLRgtC+0YDQvtCz0L4g0YPRgNC+0LLQvdGPLCDQvdCwINC60L7RgtC+0YDRi9GFINGB0LjQtNGP0YIg0LLRgdC1INC/0L7QtNGA0Y/QtDog0YHQvtCy0L/QsNC00LXQvdC40LUg0LjQvNC10L3QuFxuICAgICMg0YLQsNC8INC90LjRh9C10LPQviDQvdC1INC30L3QsNGH0LjRgi5cbiAgICBf0J7QkdCp0JjQlV/QktCi0J7QoNCr0JUgPSBmcm96ZW5zZXQoe1wibWFpbFwiLCBcInlhbmRleFwiLCBcImdvb2dsZVwiLCBcImdtYWlsXCIsIFwibGlzdFwiLFxuICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIFwiYmtcIiwgXCJpbmJveFwiLCBcInJhbWJsZXJcIiwgXCJvdXRsb29rXCIsIFwibGl2ZVwifSlcblxuICAgIGRlZiBfcmVjaXBpZW50X2J5X2lteWFfZG9tZW5hKHNlbGYsIGZyb21fYWRkcjogc3RyKSAtPiBPcHRpb25hbFtpbnRdOlxuICAgICAgICBcIlwiXCLQotCwINC20LUg0LrQvtC90YLQvtGA0LAg0LIg0LTRgNGD0LPQvtC5INC30L7QvdC1OiBzbWstYWx0ZXJuYXRpdmEuY29tINC/0YDQvtGC0LjQsiAucnUuXG5cbiAgICAgICAgMjYuMDggwqvQodCc0Jog0JDQu9GM0YLQtdGA0L3QsNGC0LjQstCwwrsg0L/RgNC40YHQu9Cw0LvQsCDRgtC10YXQt9Cw0LTQsNC90LjQtSDQvdCwINC/0L3QtdCy0LzQvtGB0LjRgdGC0LXQvNGDIC1cbiAgICAgICAg0LTQsNCy0LvQtdC90LjQtSwg0YDQsNGB0YXQvtC0LCDQutC70LDRgdGB0Ysg0YfQuNGB0YLQvtGC0YssINGH0YLQviDRgdGC0L7QuNGCINGB0LXQudGH0LDRgSAtINGBINGP0YnQuNC60LBcbiAgICAgICAgY2hlcm5vdkBzbWstYWx0ZXJuYXRpdmEuQ09NLCDQsCDQv9C40YHQsNC70Lgg0LzRiyDQvdCwIHBvc3RAc21rLWFsdGVybmF0aXZhLlJVLlxuICAgICAgICDQndC4INCy0LXRgtC60LAsINC90Lgg0LDQtNGA0LXRgSwg0L3QuCDQtNC+0LzQtdC9INC90LUg0YHQvtGI0LvQuNGB0YwsINC4INCz0L7RgNGP0YfQtdC1INC/0LjRgdGM0LzQviDQu9C10LPQu9C+XG4gICAgICAgIMKr0LLRhdC+0LTRj9GJ0LjQvCDQstC90LUg0L/QtdGA0LXQv9C40YHQutC4wrsg0LHQtdC3INC60L7QvNC/0LDQvdC40LguXG5cbiAgICAgICAg0KHQstC10YDRj9C10Lwg0JjQnNCvINC00L7QvNC10L3QsCDQsdC10Lcg0LfQvtC90Ysg0Lgg0YLRgNC10LHRg9C10LwsINGH0YLQvtCx0Ysg0YHQvtCy0L/QsNC70LAg0YDQvtCy0L3QviDQvtC00L3QsFxuICAgICAgICDQutC+0LzQv9Cw0L3QuNGPOiDCq2FsdGVybmF0aXZhLnJ1wrsg0LggwqthbHRlcm5hdGl2YS5jb23CuyDRgNCw0LfQvdGL0YUg0YTQuNGA0Lwg0YLQsNC6INC90LVcbiAgICAgICAg0YHQutC70LXRj9GC0YHRjywg0L/QvtGC0L7QvNGDINGH0YLQviDQuNC80Y8g0YMg0L3QuNGFINGC0L7QttC1INGA0LDQt9C90L7QtS5cbiAgICAgICAgXCJcIlwiXG4gICAgICAgINCw0LTRgNC10YEgPSBzdHIoZnJvbV9hZGRyIG9yIFwiXCIpLnN0cmlwKCkubG93ZXIoKVxuICAgICAgICBpZiBcIkBcIiBub3QgaW4g0LDQtNGA0LXRgTpcbiAgICAgICAgICAgIHJldHVybiBOb25lXG4gICAgICAgINC00L7QvNC10L0gPSDQsNC00YDQtdGBLnJzcGxpdChcIkBcIiwgMSlbLTFdXG4gICAgICAgINGH0LDRgdGC0LggPSDQtNC+0LzQtdC9LnNwbGl0KFwiLlwiKVxuICAgICAgICBpZiBsZW4o0YfQsNGB0YLQuCkgPCAyOlxuICAgICAgICAgICAgcmV0dXJuIE5vbmVcbiAgICAgICAg0LjQvNGPID0g0YfQsNGB0YLQuFstMl1cbiAgICAgICAgIyDQmtC+0YDQvtGC0LrQvtC1INC40LvQuCDQvtCx0YnQtdC1INC40LzRjyDRgdC60LvQtdC40YIg0YfRg9C20LjRhTogwqttYWlsLnJ1wrsg0LggwqttYWlsLmNvbcK7LlxuICAgICAgICBpZiBsZW4o0LjQvNGPKSA8IDUgb3Ig0LjQvNGPIGluIHNlbGYuX9Ce0JHQqdCY0JVf0JLQotCe0KDQq9CVOlxuICAgICAgICAgICAgcmV0dXJuIE5vbmVcbiAgICAgICAgZmluZGVyID0gZ2V0YXR0cihzZWxmLl9zdG9yZSwgXCJyZWNpcGllbnRzX2J5X2RvbWFpbl9uYW1lXCIsIE5vbmUpXG4gICAgICAgIGlmIG5vdCBjYWxsYWJsZShmaW5kZXIpOlxuICAgICAgICAgICAgcmV0dXJuIE5vbmVcbiAgICAgICAgdHJ5OlxuICAgICAgICAgICAg0YHRgtGA0L7QutC4ID0gZmluZGVyKNC40LzRjykgb3IgW11cbiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjogICMgbm9xYTogQkxFMDAxIC0g0YHQsdC+0Lkg0L/QvtC40YHQutCwINC90LUg0YDQvtC90Y/QtdGCINC/0YDQuNGR0LxcbiAgICAgICAgICAgIGxvZ2dlci5leGNlcHRpb24oXCJyZWNpcGllbnRzX2J5X2RvbWFpbl9uYW1lIGZhaWxlZCBmb3IgJXNcIiwg0LjQvNGPKVxuICAgICAgICAgICAgcmV0dXJuIE5vbmVcbiAgICAgICAgaWYgbm90INGB0YLRgNC+0LrQuDpcbiAgICAgICAgICAgIHJldHVybiBOb25lXG5cbiAgICAgICAgZGVmINC/0L7Qu9C1KHIsINC6KTpcbiAgICAgICAgICAgIHJldHVybiByLmdldCjQuikgaWYgaXNpbnN0YW5jZShyLCBkaWN0KSBlbHNlIGdldGF0dHIociwg0LosIE5vbmUpXG5cbiAgICAgICAg0LjQvdC90YsgPSB7c3RyKNC/0L7Qu9C1KHIsIFwiaW5uXCIpIG9yIFwiXCIpLnN0cmlwKCkgZm9yIHIgaW4g0YHRgtGA0L7QutC4fVxuICAgICAgICDQuNC90L3Riy5kaXNjYXJkKFwiXCIpXG4gICAgICAgIGlmIGxlbijQuNC90L3RiykgPiAxOlxuICAgICAgICAgICAgbG9nZ2VyLmluZm8oXCLQv9GA0LjQstGP0LfQutCwINC/0L4g0LjQvNC10L3QuCDQtNC+0LzQtdC90LAgJXMg0L/RgNC+0L/Rg9GJ0LXQvdCwOiDQutC+0LzQv9Cw0L3QuNC5ICVkXCIsXG4gICAgICAgICAgICAgICAgICAgICAgICDQuNC80Y8sIGxlbijQuNC90L3RiykpXG4gICAgICAgICAgICByZXR1cm4gTm9uZVxuICAgICAgICByaWQgPSDQv9C+0LvQtSjRgdGC0YDQvtC60LhbMF0sIFwiaWRcIilcbiAgICAgICAgcmV0dXJuIGludChyaWQpIGlmIHJpZCBlbHNlIE5vbmVcblxuIiwgInN0b3IiOiAiICAgIGRlZiByZWNpcGllbnRzX2J5X2RvbWFpbl9uYW1lKHNlbGYsIG5hbWU6IHN0cikgLT4gbGlzdFtkaWN0XTpcbiAgICAgICAgXCJcIlwi0J/QvtC70YPRh9Cw0YLQtdC70LgsINGDINGH0YzQtdCz0L4g0LTQvtC80LXQvdCwINGC0LDQutC+0LUg0LbQtSDQmNCc0K8sINC90L4g0LfQvtC90LAg0LvRjtCx0LDRjy5cblxuICAgICAgICDQndGD0LbQvdCwINC00LvRjyDQvtGC0LLQtdGC0L7QsiDRgSDQtNGA0YPQs9C+0Lkg0LfQvtC90Ysg0YLQvtC5INC20LUg0LrQvtC90YLQvtGA0Ys6IDI2LjA4IMKr0KHQnNCaXG4gICAgICAgINCQ0LvRjNGC0LXRgNC90LDRgtC40LLQsMK7INC90LDQv9C40YHQsNC70LAg0YEgc21rLWFsdGVybmF0aXZhLmNvbSwg0LAg0L/QuNGB0LDQu9C4INC80Ysg0L3QsFxuICAgICAgICBzbWstYWx0ZXJuYXRpdmEucnUuINCg0LXRiNC10L3QuNC1IMKr0Y3RgtC+INC+0LTQvdCwINC60L7QvNC/0LDQvdC40Y/CuyDQv9GA0LjQvdC40LzQsNC10YJcbiAgICAgICAg0LLRi9C30YvQstCw0Y7RidC40Lk6INC+0L0g0YHQstC10YDRj9C10YIg0JjQndCdINC4INC+0YLRgdC10LrQsNC10YIg0LrQvtGA0L7RgtC60LjQtSDQuCDQvtCx0YnQuNC1INC40LzQtdC90LAuXG4gICAgICAgIFwiXCJcIlxuICAgICAgICDQuNC80Y8gPSBzdHIobmFtZSBvciBcIlwiKS5zdHJpcCgpLmxvd2VyKClcbiAgICAgICAgaWYgbGVuKNC40LzRjykgPCA1OlxuICAgICAgICAgICAgcmV0dXJuIFtdXG4gICAgICAgIHdpdGggc2VsZi5fbG9jazpcbiAgICAgICAgICAgIHJvd3MgPSBzZWxmLl9jb25uLmV4ZWN1dGUoXG4gICAgICAgICAgICAgICAgXCJTRUxFQ1QgKiBGUk9NIHJlY2lwaWVudHMgV0hFUkUgbG93ZXIoZG9tYWluKSBMSUtFID8gXCJcbiAgICAgICAgICAgICAgICBcIiBPUiBsb3dlcihlbWFpbCkgTElLRSA/IE9SREVSIEJZIGlkXCIsXG4gICAgICAgICAgICAgICAgKNC40LzRjyArIFwiLiVcIiwgXCIlQFwiICsg0LjQvNGPICsgXCIuJVwiKSkuZmV0Y2hhbGwoKVxuICAgICAgICByZXR1cm4gW2RpY3QocikgZm9yIHIgaW4gcm93c11cblxuIn0=").decode("utf-8"))
КАТИТЬ = "--katit" in sys.argv
W = r"C:\sender\sender\imap_watcher.py"
S = r"C:\sender\sender\store.py"
ЯКОРЬ_W = "    def _process_event(self, ev: InboundEvent, mailbox_id: str) -> None:"
ЯКОРЬ_ФОЛБЭК = """        if recipient_id is None and kind != "dsn":
            recipient_id = self._recipient_by_domain(from_addr)"""
ДОБАВКА = """
        if recipient_id is None and kind != "dsn":
            recipient_id = self._recipient_by_imya_domena(from_addr)"""
ЯКОРЬ_S = """    def iter_recipients(
        self, *, valid_status: Optional[str] = None, provider: Optional[str] = None,"""


def правка(путь, пары, метка):
    имя = os.path.basename(путь)
    т = io.open(путь, encoding="utf-8").read()
    if метка in т:
        print("%-18s правка уже стоит" % имя)
        return
    for як, новое, куда in пары:
        n = т.count(як)
        print("   %-18s якорь найден раз: %d" % (имя, n))
        if n != 1:
            raise SystemExit("якорь должен быть ровно один")
        т = т.replace(як, (новое + як) if куда == "до" else (як + новое))
    if not КАТИТЬ:
        print("   сухой прогон, станет %d знаков" % len(т))
        return
    копия = "%s.bak-%d" % (путь, int(time.time()))
    io.open(копия, "w", encoding="utf-8", newline="").write(
        io.open(путь, encoding="utf-8").read())
    with io.open(путь, "w", encoding="utf-8", newline="") as f:
        f.write(т)
        f.flush()
        os.fsync(f.fileno())
    py_compile.compile(путь, doraise=True)
    print("   поставлен %s (.bak %s)" % (имя, os.path.basename(копия)))


print("=== imap_watcher ===")
правка(W, [(ЯКОРЬ_W, Д["metod"], "до"), (ЯКОРЬ_ФОЛБЭК, ДОБАВКА, "после")],
       "_recipient_by_imya_domena")
print("=== store ===")
правка(S, [(ЯКОРЬ_S, Д["stor"], "до")], "recipients_by_domain_name")
if not КАТИТЬ:
    print("\nсухой прогон. Катить: --katit")
