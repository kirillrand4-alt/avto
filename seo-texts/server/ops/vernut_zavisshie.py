# -*- coding: utf-8 -*-
"""Вернуть в очередь письма, зависшие в «sending» больше суток (владелец 22.10:
«верни»; 4 — Россия 9000, 3 — второе касание, взяты 14–20.10). Перед
возвратом — сверка с send_log: если письмо по факту ушло, НЕ возвращаем
(иначе дубль), только печатаем. Возврат — штатный store.release_message
(sending → scheduled). Журнал _ops/vernut-zavisshie.jsonl. Без --primenit — счёт."""
import io
import json
import sys
from datetime import datetime, timedelta

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
# --chasov=N: порог зависания в часах (по умолчанию сутки); 28.10 — 9 писем,
# оборванных перезапуском службы 27.10 в 10:58, висят 18 часов
_ч = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--chasov=")), "24"))
гр = (datetime.utcnow() - timedelta(hours=_ч)).strftime("%Y-%m-%dT%H:%M:%S")
ряды = st._conn.execute("SELECT id, campaign_id, claimed_at, scheduled_at FROM messages WHERE status='sending' "
                        "AND COALESCE(claimed_at, updated_at) < ?", (гр,)).fetchall()
ж = io.open(r"C:\sender\_ops\vernut-zavisshie.jsonl", "a", encoding="utf-8")
for mid, cid, cl, sa in ряды:
    ушло = st._conn.execute("SELECT ts FROM send_log WHERE message_id=? AND outcome='sent'", (mid,)).fetchone()
    if ушло:
        print("#%d к%s — УЖЕ УШЛО %s, не возвращаю" % (mid, cid, ушло[0]))
        continue
    print("#%d к%s взято %s → в очередь" % (mid, cid, cl))
    if "--primenit" in sys.argv:
        st.release_message(mid)
        ж.write(json.dumps({"id": mid, "campaign": cid, "claimed_at": str(cl), "scheduled_at": str(sa)}) + "\n")
ж.close()
print("всего зависших:", len(ряды), "| ПРИМЕНЕНО" if "--primenit" in sys.argv else "| СУХОЙ ПРОГОН")
