# -*- coding: utf-8 -*-
"""Последние N писем из журнала целиком — чтобы посмотреть заходы глазами."""
import io
import json
import re
import sys

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
N = int(next((a for a in sys.argv[1:] if a.isdigit()), "3"))


def _т(s):
    s = re.sub(r"<br\s*/?>", "\n", str(s or ""), flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


строки = []
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                                  # noqa: BLE001
        continue
    if z.get("этап") == "итог" and (z.get("тело") or z.get("тело_брака")):
        строки.append(z)

for z in строки[-N:]:
    метка = "ГОДНО" if z.get("тело") else "БРАК"
    print(f"\n{'='*72}\n[{метка}] {z.get('имя')}")
    б = z.get("брак")
    if б:
        т = б if isinstance(б, str) else "; ".join(map(str, б))
        print(f"причина: {т[:150]}")
    print("=" * 72)
    print(f"ТЕМА: {z.get('тема') or z.get('тема_брака')}")
    print(_т(z.get("тело") or z.get("тело_брака")))
