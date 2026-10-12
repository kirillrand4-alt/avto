# -*- coding: utf-8 -*-
"""Какой моделью панель пишет письма и какой проверяет — на живом сервере.

Владелец 12.10: «письма будут писаться на какой модели?». Смотрим не репо,
а то, что реально выполнится: код review_lenses/ai_quota на диске сервера,
конфиг sender.yaml и окружение СЛУЖБЫ SenderPanel (у служебного процесса
своё окружение, не то, что у этого скрипта).
"""
import io
import os
import re
import sys

sys.path.insert(0, r"C:\sender")

print("--- живой код ---")
for имя in ("review_lenses.py", "ai_quota.py", "ai_letter.py"):
    п = os.path.join(r"C:\sender\sender", имя)
    т = io.open(п, encoding="utf-8").read()
    for рег in (r"model = model or os\.environ\.get\('LENS_MODEL'\) or '([^']+)'",
                r"LENS_FALLBACK_MODEL', '([^']+)'",
                r'"ai_quota\.checker_model", "([^"]+)"',
                r'"ai_quota\.best_of", (\d+)',
                r"^УСИЛИЕ\s*=\s*(.+)$"):
        for м in re.finditer(рег, т, re.M):
            print("   %-18s %-48s -> %s" % (имя, рег[:46], м.group(1)))

print("")
print("--- конфиг sender.yaml ---")
from sender.config import Config                                 # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
for к in ("ai_quota.checker_model", "ai_quota.best_of", "ai_quota.model",
          "ai.model", "provider.model", "generation.model"):
    try:
        print("   %-26s = %r" % (к, cfg.get(к, "(нет)")))
    except Exception as e:  # noqa: BLE001
        print("   %-26s ошибка %s" % (к, e))

print("")
print("--- окружение службы SenderPanel (реестр) ---")
try:
    import winreg
    for путь in (r"SYSTEM\CurrentControlSet\Services\SenderPanel",
                 r"SYSTEM\CurrentControlSet\Services\SenderPanel\Parameters"):
        try:
            к = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, путь)
        except OSError:
            continue
        for имя in ("Environment", "AppEnvironmentExtra", "AppEnvironment"):
            try:
                знач, _ = winreg.QueryValueEx(к, имя)
            except OSError:
                continue
            строки = знач if isinstance(знач, list) else str(знач).split("\x00")
            for с in строки:
                if re.match(r"(?i)(LENS_|.*MODEL|PROVIDER_BASE)", str(с)):
                    print("   %s\\%s: %s" % (путь.split("\\")[-1], имя, с))
except Exception as e:  # noqa: BLE001
    print("   реестр не прочитан: %s" % e)

print("")
print("--- окружение этого процесса (для сравнения) ---")
for к in ("LENS_MODEL", "LENS_FALLBACK_MODEL", "PROVIDER_BASE_URL"):
    print("   %-22s = %r" % (к, os.environ.get(к)))
print("")
print("=== МОДЕЛИ ГЕНЕРАЦИИ ===")
