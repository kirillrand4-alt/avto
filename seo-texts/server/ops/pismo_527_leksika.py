# -*- coding: utf-8 -*-
"""Что именно вернул ConfirmSend.letter_division на #527 и почему.

Фильтр очереди раскладывает письма так: сначала letter_division (поле
генератора, а если его нет - лексика самого письма), и только если и это
молчит - метка компании из карточки. Владелец видит #527 под фильтром «КЦ»,
хотя письмо про сортировку винограда и ящик подставился Meyer. Значит
лексика молчит, а метка карточки говорит 'kc'.

Печатаем: что вернула функция, какие маркеры каждого направления нашлись в
письме, и текст, по которому она считала.

    python zapusk_svoego_skripta.py ops/pismo_527_leksika.py 527
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ID = int(sys.argv[1]) if len(sys.argv) > 1 else 527

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

with store._lock:
    r = store._conn.execute(
        "SELECT id, subject, body, panel_json FROM confirm_reviews WHERE id=?",
        (ID,)).fetchone()
if not r:
    print(f"письма #{ID} нет")
    raise SystemExit(0)
rid, subj, body, pj = r
try:
    panel = json.loads(pj or "{}")
except Exception:                                               # noqa: BLE001
    panel = {}
row = {"subject": subj, "body": body, "panel": panel}

print(f"#{rid}")
print(f"letter_division() -> {cs.letter_division(row)!r}")
print(f"panel.letter_division = "
      f"{str(panel.get('letter_division'))!r}")
comp = panel.get("company") if isinstance(panel.get("company"), dict) else {}
print(f"карточка.division = {comp.get('division')!r}  <- запасной источник "
      f"фильтра")

letter = panel.get("letter") if isinstance(panel.get("letter"), dict) else {}
текст = " ".join([str(subj or ""), str(body or ""),
                  str(letter.get("subject") or ""),
                  str(letter.get("body") or "")]).lower()
print(f"\nдлина текста для лексики: {len(текст)} знаков")
for напр, маркеры in cs._LETTER_DIV_MARKERS.items():
    нашлись = [m for m in маркеры if m in текст]
    print(f"  {напр}: {len(нашлись)} маркеров {нашлись[:8]}")

print("\n--- тема и тело как есть ---")
print(f"тема: {subj}")
print((body or "")[:1200])
