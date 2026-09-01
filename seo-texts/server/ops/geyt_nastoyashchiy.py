# -*- coding: utf-8 -*-
"""Настоящий промпт гейта на 8 компаниях с паспортом + канал рассуждения."""
import io
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider                                            # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.target_gate import TargetGate                      # noqa: E402

s = io.open(r"C:\sender\gen_provider.py", encoding="utf-8",
            errors="replace").read()
i = s.find("class _Msg")
print("=== _Msg ===")
print(s[i:i + 900] if i >= 0 else "класса _Msg нет")
i2 = s.find("think_parts")
while i2 > 0:
    стр = s[max(0, s.rfind("\n", 0, i2)):s.find("\n", i2)]
    if "_Msg(" in стр or "return" in стр or "thinking=" in стр:
        print("   ...", стр.strip()[:150])
    i2 = s.find("think_parts", i2 + 1)

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=90)
e.row_factory = sqlite3.Row
кол = [r[1] for r in e.execute("PRAGMA table_info(companies)")]
print("")
print("=== КОЛОНКИ companies ===")
print("   " + ", ".join(кол))

поле_пасп = next((к for к in ("site_facts", "pasport", "passport",
                              "site_pasport", "facts") if к in кол), None)
поле_деят = next((к for к in ("activity", "deyatelnost", "okved_name",
                              "site_desc") if к in кол), None)
print("   паспорт -> %s ; деятельность -> %s" % (поле_пасп, поле_деят))

записи = []
if поле_пасп:
    зап = ("SELECT inn, name, okved, %s AS pasport, %s AS activity "
           "  FROM companies WHERE division LIKE '%%meyer%%' "
           "   AND %s IS NOT NULL AND length(%s) > 400 LIMIT 8"
           % (поле_пасп, поле_деят or "''", поле_пасп, поле_пасп))
    записи = [dict(r) for r in e.execute(зап)]
e.close()

перехват = {}


def ловец(промпт):
    перехват.setdefault("промпт", промпт)
    raise RuntimeError("промпт пойман")


cfg = Config.load(r"C:\sender\sender.yaml")
гейт = TargetGate(cfg.get("service.db_path", r"C:\sender\sender.db"), ловец)
try:
    гейт._партия(записи, "продавец")
except Exception:                                              # noqa: BLE001
    pass

итог = ["компаний в пачке: %d" % len(записи)]
промпт = перехват.get("промпт")
if not промпт:
    итог.append("промпт поймать не удалось")
else:
    системный, тело = gen_provider.razrezat_promt(промпт)
    итог.append("промпт: %d знаков (system %d, тело %d)"
                % (len(промпт), len(системный or ""), len(тело)))
    for потолок, усилие in ((2000, "medium"), (2000, "low"), (8000, "medium")):
        t0 = time.time()
        try:
            msg = gen_provider._raw_stream(
                [{"role": "user", "content": тело}], "claude-sonnet-4-6",
                потолок, thinking=False, effort=усилие, system=системный)
            текст = "".join(b.text for b in msg.content
                            if getattr(b, "type", "") == "text")
            думание = ""
            for b in msg.content:
                думание += str(getattr(b, "thinking", "") or "")
            думание = думание or str(getattr(msg, "thinking", "") or "")
            u = getattr(msg, "usage", None)
            вых = int(getattr(u, "output_tokens", 0) or 0)
            стоп = getattr(msg, "stop_reason", "?")
            порог = max(2000, int(потолок * 0.35))
            срыв = вых >= порог and len(текст) < вых
            ок_json = False
            try:
                json.loads(текст[текст.find("{"):текст.rfind("}") + 1])
                ок_json = True
            except Exception:                                  # noqa: BLE001
                pass
            итог.append(
                "потолок %5d %-7s %5.1fс выход %5d знаков %5d думания %5d "
                "(%.2f зн/ток) стоп=%-11s JSON=%-3s -> %s"
                % (потолок, усилие, time.time() - t0, вых, len(текст),
                   len(думание), (len(текст) / вых if вых else 0), стоп,
                   "да" if ок_json else "НЕТ", "СРЫВ" if срыв else "ок"))
        except Exception as ex:                                # noqa: BLE001
            итог.append("потолок %5d %-7s ОШИБКА %s"
                        % (потолок, усилие, str(ex)[:120]))

print("")
print("=" * 62)
print("=== СВОДКА: НАСТОЯЩИЙ ВЫЗОВ ГЕЙТА ===")
for с in итог:
    print(с)
