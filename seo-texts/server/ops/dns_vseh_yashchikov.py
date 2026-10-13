# -*- coding: utf-8 -*-
"""SPF / DMARC / DKIM всех доменов, с которых шлём (по ящикам sender.yaml)."""
import re
import subprocess
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
домены = sorted({str(getattr(м, "login", "")).split("@")[-1] for м in cfg.mailboxes()})


def txt(имя):
    р = subprocess.run(["nslookup", "-type=TXT", имя, "8.8.8.8"], capture_output=True, text=True, timeout=20)
    вывод = р.stdout.replace("\r", "")
    return " ".join(re.findall(r'"([^"]*)"', вывод))


for д in домены:
    _т = txt(д)
    spf = ["v=spf1 " + _т.split("v=spf1", 1)[1].split("yandex-verification")[0].strip()] if "v=spf1" in _т else []
    dmarc = txt("_dmarc." + д)
    dkim = txt("mail._domainkey." + д) or txt("mailru._domainkey." + д)
    print("%-28s SPF: %-38s DMARC: %-40s DKIM: %s" % (д, (spf[0] if spf else txt(д))[:38] or "НЕТ",
          dmarc[:40] or "НЕТ", "есть" if "DKIM1" in dkim else "НЕТ"))
print("=== DNS ЯЩИКОВ ===")
