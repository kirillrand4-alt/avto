# -*- coding: utf-8 -*-
"""Живёт ли ссылка отписки: служба, порт, ответ по HTTP, ссылка в письме."""
import io
import json
import re
import sqlite3
import subprocess
import urllib.request

print("=== настройки unsub в sender.yaml ===")
т = io.open(r"C:\sender\sender.yaml", encoding="utf-8", errors="replace").read()
for с in т.splitlines():
    if re.search(r"unsub|track|pixel|otpisk", с, re.I):
        print("   " + с.rstrip()[:150])

print("")
print("=== служба SenderPixel ===")
out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-Service SenderPixel | Format-List Name,Status,StartType; "
     "(Get-CimInstance Win32_Service -Filter \"Name='SenderPixel'\").PathName"],
    capture_output=True, text=True, timeout=60)
print((out.stdout or "").strip()[:800])

print("")
print("=== кто слушает порты 8092/8093/8080 ===")
out2 = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in "
     "@(80,443,8080,8090,8091,8092,8093) } | Select-Object LocalAddress,LocalPort,"
     "OwningProcess | Format-Table -AutoSize | Out-String -Width 120"],
    capture_output=True, text=True, timeout=60)
print((out2.stdout or "").strip()[:1200])

print("")
print("=== ссылка отписки из последнего отправленного письма ===")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
r = c.execute("SELECT id, body FROM confirm_reviews WHERE status='sent' "
              "ORDER BY id DESC LIMIT 1").fetchone()
ссылка = None
if r:
    м = re.search(r"https?://[^\s\"'<>]+", str(r["body"] or ""))
    for u in re.findall(r"https?://[^\s\"'<>)]+", str(r["body"] or "")):
        if "parsercompressor.online/u" in u or "unsub" in u.lower():
            ссылка = u
            break
    print("   письмо #%s, ссылок в теле: %d" % (
        r["id"], len(re.findall(r"https?://", str(r["body"] or "")))))
    print("   ссылка отписки: %s" % (ссылка or "в теле не нашлась"))
c.close()

ссылка = ссылка or "https://mail.parsercompressor.online/u/proverka"
if ссылка:
    print("")
    print("=== проверяем ссылку живьём ===")
    try:
        req = urllib.request.Request(ссылка, headers={"User-Agent": "Mozilla/5.0 (proverka)"})
        with urllib.request.urlopen(req, timeout=20) as о:
            тело = о.read(400).decode("utf-8", "replace")
        print("   код %s, начало ответа: %s" % (о.status, " ".join(тело.split())[:200]))
    except Exception as ex:                                   # noqa: BLE001
        print("   НЕ ОТВЕТИЛА: %r" % ex)
