# -*- coding: utf-8 -*-
"""SPF, DKIM и DMARC по всем нашим доменам: мейеровские против компрессорных.

Письмо с v.ivanov@optic-sort.ru упало у Gmail в спам (проверено владельцем
26.08). При 1.2% отклика у Meyer против 2.3% у КЦ первым делом смотрим не
тексты, а конверт: подпись домена и политику.
"""
import subprocess

ДОМЕНЫ = ["optic-sort.ru", "zernosort.ru", "sort-systems.ru",
          "kompressor-air-trade.ru", "kompressor-air-expert.ru",
          "kompressor-pro-expert.ru", "kompressor-pro-trade.ru",
          "kompressor-expert.ru", "compressor-air-expert.ru",
          "compressor-store.ru"]
# Селекторы: у Яндекса штатный «mail», у Mail.ru — «mailru», плюс частые.
СЕЛЕКТОРЫ = ["mail", "mailru", "default", "dkim", "selector1", "yandex"]


def txt(имя):
    try:
        out = subprocess.run(["nslookup", "-type=TXT", имя, "8.8.8.8"],
                             capture_output=True, text=True, timeout=25)
        строки = []
        for с in (out.stdout or "").splitlines():
            if "text =" in с or '"' in с:
                строки.append(" ".join(с.split())[:200])
        return строки
    except Exception as ex:                                   # noqa: BLE001
        return ["ошибка: %s" % str(ex)[:60]]


for д in ДОМЕНЫ:
    print("")
    print("=== %s ===" % д)
    spf = [с for с in txt(д) if "spf" in с.lower()]
    print("   SPF:   %s" % (spf[0] if spf else "НЕТ"))
    dmarc = [с for с in txt("_dmarc." + д) if "DMARC" in с.upper()]
    print("   DMARC: %s" % (dmarc[0] if dmarc else "НЕТ"))
    нашли = []
    for сел in СЕЛЕКТОРЫ:
        строки = [с for с in txt("%s._domainkey.%s" % (сел, д))
                  if "v=DKIM" in с or "p=" in с]
        if строки:
            нашли.append("%s (%s)" % (сел, строки[0][:60]))
    print("   DKIM:  %s" % ("; ".join(нашли) if нашли else "НЕ НАЙДЕН по "
                            + ", ".join(СЕЛЕКТОРЫ)))
