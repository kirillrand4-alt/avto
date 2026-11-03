# -*- coding: utf-8 -*-
"""Владелец 03.11: копии Meyer 16.10 на martiushov@ легли в спам — отправить в их
треды такие же напоминания, как идут клиентам (одно шаблон, одно заход), с того же
ящика. Текст — последнее отправленное напоминание этого ящика нужной версии.
    napominanie_vladelcu.py [--katit]"""
import json, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
КАТИТЬ = "--katit" in sys.argv
ПАРЫ = [(22920, "шаблон")] if "--vtoroe" in sys.argv else [(22919, "заходы"), (22920, "шаблон")]
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = st._conn
deps = build_deps(cfg, st, dry_run=not КАТИТЬ)
for mid, версия in ПАРЫ:
    m = c.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject, recipient_id FROM messages WHERE id=?", (mid,)).fetchone()
    mb, rfc, thr, subj, rid = m
    усл = "panel_json LIKE '%заходы%'" if версия == "заходы" else "panel_json NOT LIKE '%заходы%'"
    о = c.execute("SELECT id, COALESCE(edited_body, body) FROM confirm_reviews WHERE kind='reply' AND status='sent' "
                  "AND panel_json LIKE '%napominanie%' AND panel_json LIKE ? AND " + усл + " ORDER BY decided_at DESC LIMIT 1",
                  ('%"mailbox_id": "' + mb + '"%',)).fetchone()
    if not о:
        print(mid, mb, "нет образца", версия); continue
    print("=" * 60); print("#%s  %s → martiushov@prokompressor.ru  [%s, образец #%s]\nТема: Re: %s\n\n%s" % (mid, mb, версия, о[0], subj, о[1]))
    if КАТИТЬ:
        р = deps.confirm.submit_reply(reply_to="martiushov@prokompressor.ru", subject="Re: " + subj, body=о[1],
                                      in_reply_to=rfc, thread_id=thr or ("kopiya-vladelcu-%d" % mid), recipient_id=rid, inn=None,
                                      panel={"mailbox_id": mb, "vruchnuyu": "напоминание владельцу 03.11 (проверка спама)"})
        print("карточка", р.review_id, р.status, "created", р.created)
        if р.status == "pending":
            print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: напоминание владельцу)"))
