# -*- coding: utf-8 -*-
"""Совпадает ли серверный api/app.py с репозиторным и есть ли якоря."""
import hashlib
import io

п = r"C:\sender\sender\api\app.py"
т = io.open(п, encoding="utf-8").read()
print("серверный app.py: %d Б, sha1 %s, строк %d"
      % (len(т.encode("utf-8")), hashlib.sha1(т.encode("utf-8")).hexdigest()[:12],
         len(т.splitlines())))

ЯКОРЯ = {
    "novoe:set_mailbox": '''        if ящик:
            with suppress(Exception):
                deps.confirm.set_mailbox(int(rid), ящик, operator=p.username)
        _проверить_срочно(адрес)''',
    "lead_reply:возврат": '''        if res.status == "skipped":
            raise HTTPException(status_code=409,
                                detail=f"заслон: {res.reason or 'skipped'}")
        return {"ok": True, "review_id": res.review_id, "created": res.created}''',
}
for имя, я in ЯКОРЯ.items():
    n = т.count(я)
    print("   %-22s вхождений: %d %s" % (имя, n,
                                         "ок" if n == 1 else "ПРОБЛЕМА"))
