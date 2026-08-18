# -*- coding: utf-8 -*-
"""Что за службы крутятся и чем именно они запущены."""
import subprocess


def _ps(к, t=120):
    p = subprocess.run(["powershell", "-NoProfile", "-Command", к],
                       capture_output=True, text=True, timeout=t,
                       errors="replace")
    return ((p.stdout or "") + (p.stderr or "")).strip()


print(_ps("Get-CimInstance Win32_Service | Where-Object {$_.Name -match "
          "'sender|rusprom|panel|runner|pixel|avto'} | Select-Object "
          "Name,State,ProcessId,PathName | Format-List")[:4000])
