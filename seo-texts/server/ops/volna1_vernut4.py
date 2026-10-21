# -*- coding: utf-8 -*-
"""Вернуть 4 компании «ФСА волна 1» в генерацию Meyer (владелец 21.10: «верни 4»).
* «Русбейкер», «Бахетле-1» — Meyer писал 26–28.08 (больше 30 дней);
* «Благо-Барнаул» — писал только КЦ 27.08 (Meyer после КЦ разрешён);
* Нижнекамский молочный комбинат — адрес с сегментом «кц» с прошлой загрузки.
Заслон повтора (_povtor_razreshen) решает по extra.division получателя —
ставим «meyer»; Нижнекамскому ещё сегмент и target_division meyer. Пишет
_ops/spisok-volna1-vernut.json (id получателей). Журнал — volna1-vernut.jsonl."""
import io
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
АДРЕСА = ["info@rusbakery.ru", "komm@bahetle.com", "blago@gcblago.ru", "nmk@kama-milk.ru"]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = time.strftime("%Y-%m-%dT%H:%M:%S")
ids = []
with c, io.open(r"C:\sender\_ops\volna1-vernut.jsonl", "a", encoding="utf-8") as ж:
    for a in АДРЕСА:
        r = c.execute("SELECT id, segment, extra_json FROM recipients WHERE lower(email)=?", (a,)).fetchone()
        if not r:
            print("нет получателя:", a)
            continue
        x = json.loads(r[2] or "{}")
        ж.write(json.dumps({"id": r[0], "segment": r[1], "extra": r[2]}, ensure_ascii=False) + "\n")
        x["division"] = "meyer"
        x["target_division"] = "meyer"
        x["target_division_istochnik"] = "ФСА волна 1, владелец 21.10: «верни 4»"
        c.execute("UPDATE recipients SET segment='meyer', extra_json=?, updated_at=? WHERE id=?",
                  (json.dumps(x, ensure_ascii=False), т, r[0]))
        ids.append(r[0])
json.dump(ids, io.open(r"C:\sender\_ops\spisok-volna1-vernut.json", "w"))
print("получатели:", ids)
from sender.config import Config            # noqa: E402
from sender.confirm import ConfirmSend      # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, st, Suppression(st))
for a in АДРЕСА:
    inn = c.execute("SELECT inn FROM recipients WHERE lower(email)=?", (a,)).fetchone()
    print("заслон теперь:", a, cs._guard(inn=inn[0] if inn else None, email=a))
