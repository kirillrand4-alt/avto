# -*- coding: utf-8 -*-
"""Кого предклассификатор срезал как «другое направление» — поимённо.

На прогоне КЦ он выбросил 166 компаний. Для КЦ это много: сжатый воздух
нужен почти любому производству, и если под нож идут законные адресаты,
дешёвый отсев обходится дороже, чем экономит.
"""
import io
import json
import sys
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
НАПР = next((a for a in sys.argv[1:] if a in ("kc", "meyer")), "kc")
N = int(next((a for a in sys.argv[1:] if a.isdigit()), "30"))

срезаны = []
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") == "предкласс_отсев" and z.get("направление") == НАПР:
        срезаны.append(z)
print(f"срезано предклассификатором ({НАПР}): {len(срезаны)}")
print(f"печатаю последние {min(N, len(срезаны))}:\n")
for z in срезаны[-N:]:
    print(f"  {z.get('inn')}  {str(z.get('имя'))[:60]}")
