# -*- coding: utf-8 -*-
"""Копия нашего письма на новый адрес с подстановкой имени (владелец 09.11: «просто копию с подстановкой
его имени»): тот же ящик, та же тема, тот же текст, меняется только обращение. Отдельным письмом,
без цитаты (цитата была бы тем же текстом).
    pismo_kopiya_imya.py <messages.id> <новый_адрес> "<старое обращение>" "<новое обращение>" [--katit]"""
import re, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
мид, КОМУ, СТАР, НОВ = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db")); к = st._conn
mb, subj, rid = к.execute("SELECT mailbox_id, subject, recipient_id FROM messages WHERE id=?", (мид,)).fetchone()
inn = (к.execute("SELECT inn FROM recipients WHERE id=?", (rid,)).fetchone() or [None])[0]
тело = (к.execute("SELECT COALESCE(edited_body, body) FROM confirm_reviews WHERE message_id=? ORDER BY id DESC LIMIT 1", (мид,)).fetchone() or [""])[0]
# 11.11: в карточке может стоять метка ИМЯ_ОТПРАВИТЕЛЯ и «С уважением,» — берём то, что реально ушло, без подписи
if "ИМЯ_ОТПРАВИТЕЛЯ" in (тело or "") or not тело:
    тело = (к.execute("SELECT body_rendered FROM messages WHERE id=?", (мид,)).fetchone() or [""])[0] or тело
тело = re.split(r"\n\s*С уважением,", тело or "")[0].rstrip()
if тело.count(СТАР) != 1: sys.exit("обращение «%s» встречается %d раз — не трогаю" % (СТАР, тело.count(СТАР)))
ТЕКСТ = тело.replace(СТАР, НОВ, 1)
print("с", mb, "→", КОМУ, "| тема:", subj, "| ИНН", inn); print(ТЕКСТ)
if "--katit" in sys.argv:
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=subj, body=ТЕКСТ, in_reply_to=None,
                                  thread_id="kopiya-%d-%s" % (мид, КОМУ), recipient_id=None, inn=inn,
                                  panel={"mailbox_id": mb, "vruchnuyu": "копия письма %d на новый адрес по указанию клиента (владелец 09.11)" % мид})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: копия на новый адрес)"))
