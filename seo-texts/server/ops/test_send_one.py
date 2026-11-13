# -*- coding: utf-8 -*-
"""Отладка: прогнать штатный AutoSendLoop._send_one по 2 созревшим одобренным письмам кампании 22 живым Sender'ом
(письма одобрены к автоотправке — если всё ок, они реально уйдут, как ушли бы из цикла). Печатает, где письмо
возвращается в очередь (release) или что отвечает отправка. Пароли — из panel.env в процесс, не печатаются."""
import io, os, sqlite3, sys, traceback
from datetime import datetime, timezone
for с in io.open(r"C:\sender\panel.env", encoding="utf-8-sig"):
    if "=" in с and not с.lstrip().startswith("#"):
        к, v = с.split("=", 1); os.environ.setdefault(к.strip(), v.strip().strip('"'))
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.wiring import build_deps
from sender.auto_send import AutoSendLoop, window_from
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(r"C:\sender\sender.db")
d = build_deps(cfg, st, dry_run=False)
print("live_sender:", type(d.live_sender).__name__ if d.live_sender else None)
loop = AutoSendLoop(store=st, config=cfg, live_sender=d.live_sender)
print("enabled:", loop.enabled())
_rel = st.release_message
def отлов(mid, *a, **k):
    print("   RELEASE #%s из: %s" % (mid, " <- ".join("%s:%s" % (os.path.basename(f.filename), f.lineno) for f in traceback.extract_stack()[-4:-1])))
    return _rel(mid, *a, **k)
st.release_message = отлов
now = datetime.now(timezone.utc); win = window_from(st, cfg)
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
ids = [r[0] for r in c.execute("SELECT id FROM messages WHERE status='scheduled' AND campaign_id=22 AND scheduled_at<=? ORDER BY scheduled_at LIMIT 2", (now.strftime('%Y-%m-%dT%H:%M:%S'),))]
for mid in ids:
    with st.transaction() as conn:
        conn.execute("UPDATE messages SET status='sending', claimed_at=? WHERE id=? AND status='scheduled'", (now.isoformat(), mid))
    m = st.get_message(mid); out = {"sent": 0, "released": 0, "skipped": 0, "failed": 0}
    try: loop._send_one(m, win, now, out)
    except Exception as ex: print("   ИСКЛЮЧЕНИЕ:", repr(ex)[:300]); st.release_message(mid)
    print("#%s -> %s | статус теперь: %s" % (mid, out, c.execute("SELECT status, COALESCE(last_error,'') FROM messages WHERE id=?", (mid,)).fetchone()))
