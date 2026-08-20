# -*- coding: utf-8 -*-
import json, subprocess, urllib.request
out = subprocess.run(['powershell','-NoProfile','-Command',
  "Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -lt 9100 -and $_.LocalPort -gt 7900} | "
  "%{ $_.LocalPort.ToString() + ' ' + (Get-Process -Id $_.OwningProcess).ProcessName } | Sort-Object -Unique"],
  capture_output=True, text=True, timeout=90)
порты = [x.strip() for x in out.stdout.splitlines() if x.strip()]
d = {'слушают': порты}
for стр in порты:
    п = стр.split()[0]
    for путь in ('/leads/43/dialog', '/'):
        try:
            r = urllib.request.urlopen('http://127.0.0.1:%s%s' % (п, путь), timeout=8)
            d.setdefault('ответы', {})['%s%s' % (п, путь)] = \
                (r.status, r.read()[:120].decode('utf-8', 'replace'))
        except Exception as e:
            d.setdefault('ответы', {})['%s%s' % (п, путь)] = str(e)[:70]
print(json.dumps(d, ensure_ascii=False, indent=1))
