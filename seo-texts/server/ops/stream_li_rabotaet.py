# -*- coding: utf-8 -*-
"""Работает ли СТРИМ у шлюза. Мой прошлый замер шёл без стрима и врал.

Конвейер весь на gen_provider._raw_stream. Меряем его напрямую: короткий
вызов, потом гейтоподобный (system + просьба JSON), обе на соннете.
"""
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider                                           # noqa: E402

ОПЫТЫ = (
    ("короткий, без system", [{"role": "user", "content": "ответь: готов"}],
     200, None),
    ("с system, как у линзы",
     [{"role": "user", "content": "Компания: ООО «Ромашка», делает крупы.\n"
                                  "Ответь строго JSON."}],
     2000, "Ты классификатор. Ответ строго JSON: {\"ok\":true}"),
)
for имя, msgs, потолок, sys_ in ОПЫТЫ:
    т0 = time.time()
    try:
        m = gen_provider._raw_stream(msgs, "claude-sonnet-4-6", потолок,
                                     thinking=False,
                                     **({"system": sys_} if sys_ else {}))
        текст = "".join(getattr(b, "text", "")
                        for b in getattr(m, "content", []) or [])
        print("   %-24s ОК за %5.1f с, ответ %r"
              % (имя, time.time() - т0, текст[:60]))
    except Exception as e:                                     # noqa: BLE001
        print("   %-24s ОШИБКА за %5.1f с: %s"
              % (имя, time.time() - т0, str(e)[:120]))

print("\n=== ИТОГ ===")
print("если оба опыта прошли за секунды — стрим жив, и дело в объёме")
print("промпта; если висят — шлюз не отдаёт стрим, и генерация невозможна.")
