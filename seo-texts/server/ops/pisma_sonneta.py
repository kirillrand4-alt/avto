# -*- coding: utf-8 -*-
"""Только соннетовские письма, по номерам — чтобы влезали в хвост вывода."""
import io
import json
import re
import sys

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
номера = [int(a) for a in sys.argv[1:] if a.isdigit()] or [1, 2, 3]


def _т(s):
    s = re.sub(r"<br\s*/?>", "\n", str(s or ""), flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


сон = []
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                                  # noqa: BLE001
        continue
    if "sonnet" in str(z.get("модель") or "") and (
            z.get("тело") or z.get("тело_брака")):
        сон.append(z)
сон = сон[-10:]
print(f"(соннетовских писем в журнале: {len(сон)}; печатаю {номера})\n")
for н in номера:
    if not 1 <= н <= len(сон):
        continue
    z = сон[н - 1]
    метка = "ГОДНО" if z.get("тело") else "БРАК"
    print(f"\n{'='*70}\n{н}. [{метка}] {z.get('имя')}   ${z.get('цена_$')}")
    б = z.get("брак")
    if б:
        т = б if isinstance(б, str) else "; ".join(map(str, б))
        print(f"ПОЧЕМУ БРАК: {т[:200]}")
    print(f"{'='*70}")
    print(f"ТЕМА: {z.get('тема') or z.get('тема_брака')}")
    print(_т(z.get("тело") or z.get("тело_брака")))
