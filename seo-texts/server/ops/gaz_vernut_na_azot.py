# -*- coding: utf-8 -*-
"""Вернуть снятые карточки кампании 22, у которых фраза про азот, а станция была кислородной (разнобой газа из
файла ЦА): станция → азотная (gaz_kanon.ОХВАТ["N2"]), вопрос «азотной станции», тема ТЕМЫ["N2"], статус → pending,
сообщение → pending_review. Владелец 11.11 одобрил правки по итогам линз.  gaz_vernut_na_azot.py id,id,... [--primenit]"""
import json, os, random, re, sqlite3, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gaz_kanon as K   # noqa: E402
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = datetime.now(timezone.utc).isoformat(timespec="seconds")
for кид in [int(x) for x in sys.argv[1].split(",")]:
    st, тело, mid, pj = c.execute("SELECT status, body, message_id, panel_json FROM confirm_reviews WHERE id=?", (кид,)).fetchone()
    абз = тело.split("\n\n")
    м = re.search(r"\s(Под такие задачи|Для этого|Под такие процессы|Под резку|Как раз)\b", абз[1])
    абз[1] = абз[1][:м.start()].strip() + " " + random.choice(K.ОХВАТ["N2"])
    абз[3] = абз[3].replace("кислородной станции", "азотной станции")
    новое = "\n\n".join(абз); тема = random.choice(K.ТЕМЫ["N2"])
    д = json.loads(pj or "{}")
    if isinstance(д.get("gaz"), dict): д["gaz"]["gaz"] = "N2"; д["gaz"]["pochineno"] = "возвращено с азотной станцией (11.11)"
    print("#%d (%s)\nТема: %s\n%s\n" % (кид, st, тема, новое))
    if "--primenit" in sys.argv:
        c.execute("UPDATE confirm_reviews SET status='pending', reason=NULL, decided_at=NULL, body=?, subject=?, panel_json=?, updated_at=? WHERE id=?",
                  (новое, тема, json.dumps(д, ensure_ascii=False), т, кид))
        if mid: c.execute("UPDATE messages SET status='pending_review', last_error=NULL WHERE id=? AND status='skipped'", (mid,))
if "--primenit" in sys.argv: c.commit(); print("возвращено")
