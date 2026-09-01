# -*- coding: utf-8 -*-
"""Упирается ли ответ гейта в потолок в 2000 токенов. Сводка в конце."""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider                                            # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.target_gate import TargetGate                      # noqa: E402

# восемь настоящих мейеровских компаний с паспортом
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=90)
e.row_factory = sqlite3.Row
кол = {r[1] for r in e.execute("PRAGMA table_info(companies)")}
поле_пасп = ("site_facts" if "site_facts" in кол else
             ("pasport" if "pasport" in кол else None))
поле_деят = ("activity" if "activity" in кол else
             ("okved_name" if "okved_name" in кол else None))
зап = ("SELECT inn, name, okved, %s AS pasport, %s AS activity "
       "  FROM companies WHERE division LIKE '%%meyer%%' "
       "   AND %s IS NOT NULL AND length(%s) > 400 LIMIT 8"
       % (поле_пасп or "''", поле_деят or "''", поле_пасп or "inn",
          поле_пасп or "inn"))
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

итог = []
промпт = перехват.get("промпт")
if not промпт:
    итог.append("промпт поймать не удалось")
else:
    системный, тело = gen_provider.razrezat_promt(промпт)
    итог.append("промпт: %d знаков (system %d, тело %d), компаний %d"
                % (len(промпт), len(системный or ""), len(тело), len(записи)))
    for потолок in (2000, 8000):
        t0 = time.time()
        try:
            msg = gen_provider._raw_stream(
                [{"role": "user", "content": тело}], "claude-sonnet-4-6",
                потолок, thinking=False, effort="medium", system=системный)
            текст = "".join(b.text for b in msg.content
                            if getattr(b, "type", "") == "text")
            u = getattr(msg, "usage", None)
            вых = int(getattr(u, "output_tokens", 0) or 0)
            стоп = getattr(msg, "stop_reason", "?")
            порог = max(2000, int(потолок * 0.35))
            срыв = вых >= порог and len(текст) < вых
            разобрался = False
            try:
                json.loads(текст[текст.find("{"):текст.rfind("}") + 1])
                разобрался = True
            except Exception:                                  # noqa: BLE001
                pass
            итог.append(
                "потолок %5d: %5.1fс выход %5d знаков %5d (%.2f зн/токен) "
                "стоп=%-12s JSON=%s порог_срыва=%d -> %s"
                % (потолок, time.time() - t0, вых, len(текст),
                   (len(текст) / вых if вых else 0), стоп,
                   "да" if разобрался else "НЕТ", порог,
                   "СРЫВ" if срыв else "ок"))
        except Exception as ex:                                # noqa: BLE001
            итог.append("потолок %5d: ОШИБКА %s" % (потолок, str(ex)[:130]))

print("=" * 62)
print("=== СВОДКА: ПОТОЛОК ОТВЕТА ГЕЙТА ===")
for с in итог:
    print(с)
print("")
print("Детектор срыва считает срывом: выход >= max(2000, потолок*0.35) И")
print("знаков текста < токенов выхода. Русский JSON даёт ~1-2 знака на токен,")
print("то есть условие «знаков < токенов» для него выполняется само собой.")
