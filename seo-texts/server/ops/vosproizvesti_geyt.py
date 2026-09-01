# -*- coding: utf-8 -*-
"""Реальный вызов гейта адресата: сколько токенов выхода, знаков, рассуждения.

Собираем ТОТ ЖЕ промпт, что строит TargetGate на пачке из 8 компаний, и
зовём шлюз напрямую — с полной диагностикой. Сводка в конце.
"""
import io
import os
import re
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider                                            # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402
from sender.target_gate import TargetGate                      # noqa: E402

# --- как строится промпт -------------------------------------------------
t = io.open(r"C:\sender\sender\target_gate.py", encoding="utf-8",
            errors="replace").read()
i = t.find("def _prompt")
if i < 0:
    for кандидат in ("def _build", "def _sprosit", "промпт ="):
        i = t.find(кандидат)
        if i >= 0:
            break
j = t.find("\n    def ", i + 10)
print("=== СБОРКА ПРОМПТА ГЕЙТА ===")
print(t[i:j if j > 0 else i + 3000][:3000])

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
группы = store.recipient_groups().get("по_id") or {}
в_группе = [rid for rid, gr in группы.items() if "Партия 935" in gr]

записи = []
for rid in sorted(в_группе):
    rec = store.get_recipient(rid)
    if not rec:
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    if not inn:
        continue
    записи.append({"inn": inn,
                   "name": str(getattr(rec, "company", "") or
                               getattr(rec, "name", "") or ""),
                   "okved": str(getattr(rec, "okved", "") or ""),
                   "site": str(getattr(rec, "site", "") or "")})
    if len(записи) >= 8:
        break

гейт = TargetGate(cfg.get("service.db_path", r"C:\sender\sender.db"),
                  lambda p: p)
промпт = None
for имя in ("_prompt", "_build_prompt", "_sobrat_prompt"):
    ф = getattr(гейт, имя, None)
    if ф:
        try:
            промпт = ф(записи)
            print("промпт собран методом %s" % имя)
            break
        except Exception as ex:  # noqa: BLE001
            print("метод %s не подошёл: %s" % (имя, str(ex)[:90]))

итог = []
if промпт:
    системный, тело = gen_provider.razrezat_promt(промпт)
    итог.append("длина промпта: %d знаков (system %d, тело %d)"
                % (len(промпт), len(системный or ""), len(тело)))
    for усилие in ("medium", "low"):
        t0 = time.time()
        try:
            msg = gen_provider._raw_stream(
                [{"role": "user", "content": тело}], "claude-sonnet-4-6",
                2000, thinking=False, effort=усилие, system=системный)
            текст = "".join(b.text for b in msg.content
                            if getattr(b, "type", "") == "text")
            думание = "".join(getattr(b, "thinking", "") or "" for b in msg.content)
            u = getattr(msg, "usage", None)
            вх = int(getattr(u, "input_tokens", 0) or 0)
            вых = int(getattr(u, "output_tokens", 0) or 0)
            порог = max(2000, int(2000 * 0.35))
            срыв = вых >= порог and len(текст) < вых
            итог.append(
                "%-7s %5.1fс вход %5d выход %5d знаков %5d думания %5d "
                "стоп=%s -> %s"
                % (усилие, time.time() - t0, вх, вых, len(текст), len(думание),
                   getattr(msg, "stop_reason", "?"), "СРЫВ" if срыв else "ок"))
            итог.append("   знаков на токен выхода: %.2f"
                        % (len(текст) / вых if вых else 0))
            итог.append("   ответ: " + текст.replace("\n", " ")[:220])
        except Exception as ex:  # noqa: BLE001
            итог.append("%-7s ОШИБКА: %s" % (усилие, str(ex)[:140]))
else:
    итог.append("промпт собрать не удалось — методы гейта другие")

print("")
print("=" * 62)
print("=== СВОДКА ===")
print("компаний в пачке: %d" % len(записи))
for с in итог:
    print(с)
