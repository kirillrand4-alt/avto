# -*- coding: utf-8 -*-
"""Диагностика 12.10: почему не уходят письма кампании #14 (только чтение).

1) smtp.yandex.ru:465/587/25 по всем A-записям, несколько попыток;
2) правила файрвола codex_* — привязки (программа/пользователь/порты/адреса);
3) служба SenderPanel: учётка, бинарь, параметры; кто запускает раннер;
4) хэши живых файлов sender\\*.py (сверка с репо).
Ничего не меняет.
"""
import hashlib
import os
import socket
import subprocess
import time

ИТОГ = []


def пробить(ip, порт, тайм=8):
    t = time.time()
    try:
        s = socket.create_connection((ip, порт), timeout=тайм)
        try:
            s.settimeout(5)
            баннер = s.recv(120) if порт != 465 else b"(tls)"
        except Exception:  # noqa: BLE001
            баннер = b"?"
        s.close()
        return "ОК %.1fс %s" % (time.time() - t, баннер[:40].decode("latin1", "replace").strip())
    except Exception as e:  # noqa: BLE001
        return "СБОЙ %.0fс %s" % (time.time() - t, type(e).__name__)


def ps(cmd, лимит=2500):
    p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, encoding="cp866",
                       errors="replace", timeout=120)
    return ((p.stdout or "") + (p.stderr or ""))[:лимит]


import sys
ТОЛЬКО_СЕТЬ = "net" in sys.argv
print("### 1. СЕТЬ")
for хост in ("smtp.yandex.ru", "smtp.yandex.com", "smtp.ya.ru"):
    try:
        ips = sorted({a[4][0] for a in socket.getaddrinfo(хост, 465)})
    except Exception as e:  # noqa: BLE001
        print("  %s DNS-сбой %s" % (хост, e))
        continue
    print("  %s -> %s" % (хост, ", ".join(ips)))
    for ip in ips:
        if ":" in ip:
            continue
        for порт in (465, 587, 25):
            рез = [пробить(ip, порт) for _ in range(2 if порт == 465 else 1)]
            print("     %s:%d  %s" % (ip, порт, " | ".join(рез)))
            if порт == 465:
                ИТОГ.append("%s:465 %s" % (ip, рез[-1][:12]))
for хост, порт in (("mx.yandex.ru", 25), ("imap.yandex.ru", 993),
                   ("smtp.mail.ru", 465), ("smtp.gmail.com", 465)):
    print("  контроль %s:%d -> %s" % (хост, порт, пробить(хост, порт)))

if ТОЛЬКО_СЕТЬ:
    print(ps(r"""foreach ($i in 101732,126996) { $p=Get-CimInstance Win32_Process -Filter "ProcessId=$i"; if ($p) { "  pid={0} {1}" -f $i,($p.CommandLine).Substring(0,[Math]::Min(300,$p.CommandLine.Length)) } }""", 1200))
    print(ps("Resolve-DnsName smtp.yandex.ru -Type A | ForEach-Object { $_.IPAddress }; Test-NetConnection 77.88.21.158 -Port 465 -InformationLevel Detailed | Out-String", 1500))
    print("=== ИТОГ: " + "; ".join(ИТОГ))
    raise SystemExit(0)
print("")
print("### 2. ФАЙРВОЛ codex*")
print(ps(r"""
$r = Get-NetFirewallRule | Where-Object { $_.DisplayName -like '*codex*' -or $_.Name -like '*codex*' }
foreach ($x in $r) {
 $a = $x | Get-NetFirewallApplicationFilter
 $s = $x | Get-NetFirewallSecurityFilter
 $p = $x | Get-NetFirewallPortFilter
 $ad = $x | Get-NetFirewallAddressFilter
 $i = $x | Get-NetFirewallInterfaceTypeFilter
 "RULE {0} en={1} dir={2} act={3} prof={4} store={5}" -f $x.DisplayName,$x.Enabled,$x.Direction,$x.Action,$x.Profile,$x.PolicyStoreSourceType
 "  prog={0} pkg={1} svc={2}" -f $a.Program,$a.Package,($x|Get-NetFirewallServiceFilter).Service
 "  localUser={0} remoteUser={1} owner={2} auth={3}" -f $s.LocalUser,$s.RemoteUser,$x.Owner,$s.Authentication
 "  proto={0} rport={1} lport={2} raddr={3} iface={4}" -f $p.Protocol,($p.RemotePort -join ','),($p.LocalPort -join ','),(($ad.RemoteAddress -join ',').Substring(0,[Math]::Min(80,($ad.RemoteAddress -join ',').Length))),$i.InterfaceType
}
""", 3000))
print(ps(r"""
$r = Get-NetFirewallRule | Where-Object { $_.DisplayName -like '*codex*' }
foreach ($x in $r) { $s = $x | Get-NetFirewallSecurityFilter
 if ($s.LocalUser -and $s.LocalUser -ne 'Any') {
  try { $sd = New-Object System.Security.AccessControl.RawSecurityDescriptor $s.LocalUser
   foreach ($ace in $sd.DiscretionaryAcl) { $sid=$ace.SecurityIdentifier
    try { $n=$sid.Translate([System.Security.Principal.NTAccount]).Value } catch { $n='?' }
    "  {0}: ACE {1} {2} -> {3}" -f $x.DisplayName,$ace.AceQualifier,$sid,$n } } catch { "  sddl parse err" } } }
""", 1200))
print("  профили: " + " ".join(ps("Get-NetFirewallProfile | ForEach-Object { $_.Name+':en='+$_.Enabled+',out='+$_.DefaultOutboundAction }").split()))

print("")
print("### 3. СЛУЖБА И ПРОЦЕССЫ")
print(ps(r"""
Get-CimInstance Win32_Service -Filter "Name='SenderPanel'" | ForEach-Object { "svc state={0} start={1} user={2}`n  path={3}" -f $_.State,$_.StartMode,$_.StartName,$_.PathName }
$k='HKLM:\SYSTEM\CurrentControlSet\Services\SenderPanel\Parameters'
if (Test-Path $k) { $p=Get-ItemProperty $k; "  nssm app={0}`n  args={1}`n  dir={2}" -f $p.Application,$p.AppParameters,$p.AppDirectory }
"runner whoami: " + (whoami)
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | ForEach-Object {
  $o = Invoke-CimMethod -InputObject $_ -MethodName GetOwner
  "  pid={0} ppid={1} user={2}\{3} start={4}`n     {5}" -f $_.ProcessId,$_.ParentProcessId,$o.Domain,$o.User,$_.CreationDate,($_.CommandLine -replace '(?i)(token|pass\w*)=\S+','$1=***').Substring(0,[Math]::Min(160,$_.CommandLine.Length)) }
""", 3500))
print(ps(r"""Get-NetTCPConnection -State SynSent,Established -ErrorAction SilentlyContinue | Where-Object { $_.RemotePort -in 25,465,587 } | ForEach-Object { "  tcp {0}:{1} -> {2}:{3} {4} pid={5}" -f $_.LocalAddress,$_.LocalPort,$_.RemoteAddress,$_.RemotePort,$_.State,$_.OwningProcess }""", 1500))

print("")
print("### 4. ХЭШИ ЖИВОГО КОДА")
for ф in ("orchestrator.py", "auto_send.py", "sender.py", "store.py", "confirm.py",
          "gates.py", "warmup.py", "ramp.py", "cadence.py", "wiring.py",
          "postoffice.py", "cli.py", "config.py", os.path.join("api", "app.py")):
    п = os.path.join(r"C:\sender\sender", ф)
    if os.path.exists(п):
        д = open(п, "rb").read()
        print("  %s %d %s %s" % (hashlib.sha256(д).hexdigest()[:16], len(д), ф,
                                time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(п)))))
print("")
print("=== ИТОГ: " + "; ".join(ИТОГ))
