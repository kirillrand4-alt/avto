# -*- coding: utf-8 -*-
import json, os, subprocess, time
time.sleep(150)
p = r'C:\seostat\drop\zenno\demon.out'
хв = [s.strip() for s in open(p, encoding='utf-8', errors='replace')][-3:]
out = subprocess.run(['powershell','-NoProfile','-Command',
  "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
  "Where-Object {$_.CommandLine -like '*enrich_contacts*'} | "
  "%{ $_.ProcessId.ToString() + ' ' + $_.CreationDate }"],
  capture_output=True, text=True, timeout=90)
print(json.dumps({
 'gotovo': len(os.listdir(r'C:\seostat\drop\zenno\gotovo')),
 'кэш': len(os.listdir(r'C:\seostat\drop\pagecache')),
 'enrich_contacts_живые': [x.strip() for x in out.stdout.splitlines() if x.strip()],
 'демон': [s[:260] for s in хв]}, ensure_ascii=False, indent=1))
