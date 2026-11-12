# -*- coding: utf-8 -*-
"""Сеть сервера для пробы: адаптеры, DNS-серверы, MX через DoH, соединение с MX mail.ru на 25 порт. Только чтение."""
import json, smtplib, subprocess, urllib.request
ps = lambda к: subprocess.run(["powershell", "-NoProfile", "-Command", к], capture_output=True, text=True, errors="replace", timeout=60).stdout.strip()
print("адаптеры:\n" + ps("Get-NetAdapter | Where Status -eq 'Up' | Select -Property Name,InterfaceDescription | Format-Table -HideTableHeaders | Out-String -Width 200"))
print("DNS:\n" + ps("Get-DnsClientServerAddress -AddressFamily IPv4 | Where {$_.ServerAddresses} | Select InterfaceAlias,ServerAddresses | Format-Table -HideTableHeaders | Out-String -Width 200"))
print("маршрут по умолчанию:\n" + ps("Get-NetRoute -DestinationPrefix 0.0.0.0/0 | Select InterfaceAlias,NextHop,RouteMetric | Format-Table -HideTableHeaders | Out-String"))
try:
    д = json.load(urllib.request.urlopen("https://dns.google/resolve?name=mail.ru&type=MX", timeout=20))
    mx = sorted(д.get("Answer", []), key=lambda a: a["data"])[0]["data"].split()[-1].rstrip(".")
    print("DoH MX mail.ru:", mx)
    s = smtplib.SMTP(mx, 25, timeout=30, local_hostname="parsercompressor.online"); print("баннер/EHLO:", s.ehlo()[0]); s.quit()
except Exception as ex: print("DoH/SMTP:", repr(ex)[:200])
try: print("внешний IP:", urllib.request.urlopen("https://api.ipify.org", timeout=20).read().decode())
except Exception as ex: print("ipify:", repr(ex)[:100])
