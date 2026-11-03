# -*- coding: utf-8 -*-
"""Владелец 03.11: проверка «текст или домен» — напоминания обеих версий (шаблон и
заход) владельцу на martiushov@ со всех ящиков Meyer, где есть образцы.
Мирошниченко/Кузнецова — крест-накрест в их же тредах копий 16.10 (с цитатой);
остальные ящики — без треда (Re: без цитаты, отмечено в плане).
    spam_test_krest.py            — план
    spam_test_krest.py --n=K      — отправить K-й пункт плана"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
N = next((int(a[4:]) for a in sys.argv if a.startswith("--n=")), None)
КОМУ = next((a[7:] for a in sys.argv if a.startswith("--komu=")), "martiushov@prokompressor.ru")
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = st._conn
ТРЕД = {"i.kuznetsova@sort-systems.ru": (22920, "заходы"), "a.miroshnichenko@optic-sort.ru": (22919, "шаблон")}
ящики = sorted({r[0] for r in c.execute(
    "SELECT json_extract(panel_json,'$.mailbox_id') FROM confirm_reviews WHERE kind='reply' AND status='sent' "
    "AND panel_json LIKE '%napominanie%' AND decided_at >= '2026-11-03'") if r[0]})
план = []
for mb in ящики:
    версии = [ТРЕД[mb][1]] if mb in ТРЕД else ["шаблон", "заходы"]
    for в in версии:
        усл = "LIKE '%заходы%'" if в == "заходы" else "NOT LIKE '%заходы%'"
        о = c.execute("SELECT id, subject, COALESCE(edited_body, body) FROM confirm_reviews WHERE kind='reply' AND status='sent' "
                      "AND panel_json LIKE '%napominanie%' AND json_extract(panel_json,'$.mailbox_id')=? AND panel_json " + усл +
                      " ORDER BY decided_at DESC LIMIT 1", (mb,)).fetchone()
        if о:
            план.append((mb, в, о))
for i, (mb, в, о) in enumerate(план):
    print("%2d  %-38s %-7s образец #%s  %s" % (i, mb, в, о[0], "в треде копии" if mb in ТРЕД else "без треда"))
if N is None:
    sys.exit(0)
mb, в, (oid, subj, тело) = план[N]
deps = build_deps(cfg, st, dry_run=False)
if mb in ТРЕД and КОМУ.startswith("martiushov@"):
    m = c.execute("SELECT rfc_message_id, thread_id, subject, recipient_id FROM messages WHERE id=?", (ТРЕД[mb][0],)).fetchone()
    irt, thr, subj, rid = m[0], (m[1] or "kopiya-krest-%d" % ТРЕД[mb][0]), "Re: " + m[2], m[3]
else:
    irt, thr, rid = None, "spam-test-%s-%s-%s" % (КОМУ, mb, в), None
р = deps.confirm.submit_reply(reply_to=КОМУ, subject=subj, body=тело, in_reply_to=irt, thread_id=thr, recipient_id=rid, inn=None,
                              panel={"mailbox_id": mb, "vruchnuyu": "спам-тест владельцу 03.11 (%s → %s)" % (в, КОМУ)})
print("карточка", р.review_id, р.status, р.created)
if р.status == "pending":
    print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: спам-тест)"))
