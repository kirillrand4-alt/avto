# -*- coding: utf-8 -*-
"""Расклинить письма, застрявшие в отправке, и показать просроченные.

Письмо в состоянии 'sending' захвачено циклом и до конца не доведено:
claim берёт только 'scheduled', поэтому само оно не сдвинется никогда.
release_message возвращает его в очередь.

Просроченные (слот в прошлом) цикл берёт первыми — ORDER BY scheduled_at.
Если они стоят, дело не в очереди, и это видно по причине.
"""
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КАТИТЬ = "--katit" in sys.argv
МИНУТ = int(next((a for a in sys.argv[1:] if a.isdigit()), "20"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc)
порог = (сейчас - timedelta(minutes=МИНУТ)).isoformat()

with store._lock:
    висят = store._conn.execute(
        "SELECT m.id, m.campaign_id, m.claimed_at, m.scheduled_at, "
        "       COALESCE(m.last_error,'') err "
        "FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id "
        "WHERE m.status='sending' AND cr.status IN ('approved','edited') "
        "AND COALESCE(m.claimed_at, m.updated_at) < ?", (порог,)).fetchall()
    просрочены = store._conn.execute(
        "SELECT substr(m.scheduled_at,1,10) d, COUNT(*) n "
        "FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id "
        "WHERE m.status='scheduled' AND cr.status IN ('approved','edited') "
        "AND m.scheduled_at < ? GROUP BY d ORDER BY d", (сейчас.isoformat(),)
    ).fetchall()

# СЛЕД ОТПРАВКИ. Письмо могло УЙТИ, а статус не дописаться — тогда его
# освобождение означает дубликат в чужом ящике. Смотрим три следа:
# запись в send_log по письму, запись по адресу и любое событие (доставка,
# отбивка, ответ). Плюс отдельно — писали ли мы этой компании вообще.
можно, нельзя = [], []
with store._lock:
    for r in висят:
        mid = int(r["id"])
        стр = store._conn.execute(
            "SELECT cr.email, r.inn FROM confirm_reviews cr "
            "LEFT JOIN recipients r ON r.id=cr.recipient_id "
            "WHERE cr.message_id=? LIMIT 1", (mid,)).fetchone()
        почта = str((стр or {})["email"] if стр else "" or "").strip().lower()
        инн = str((стр or {})["inn"] if стр else "" or "")
        в_логе = store._conn.execute(
            "SELECT COUNT(*) FROM send_log WHERE message_id=?", (mid,)
        ).fetchone()[0]
        по_адресу = store._conn.execute(
            "SELECT COUNT(*) FROM send_log WHERE lower(email)=?", (почта,)
        ).fetchone()[0] if почта else 0
        событий = store._conn.execute(
            "SELECT COUNT(*) FROM events WHERE message_id=?", (mid,)
        ).fetchone()[0]
        причина = ""
        if в_логе:
            причина = f"письмо уже в send_log ({в_логе})"
        elif событий:
            причина = f"по письму есть события ({событий})"
        elif по_адресу:
            причина = f"этому адресу уже писали ({по_адресу})"
        if причина:
            нельзя.append((mid, почта, причина))
        else:
            можно.append((mid, почта, инн))

print(f"висят в 'sending' дольше {МИНУТ} мин: {len(висят)}")
print(f"  из них НЕ трогаем: {len(нельзя)}")
for mid, почта, п in нельзя[:10]:
    print(f"    письмо {mid} {почта:<32} {п}")
print(f"  можно вернуть в очередь: {len(можно)}")
print("  по кампаниям:", dict(Counter(int(r["campaign_id"]) for r in висят)))
for r in висят[:8]:
    print(f"    письмо {r['id']} захвачено {str(r['claimed_at'])[:19]} "
          f"слот {str(r['scheduled_at'])[:16]} {str(r['err'])[:50]}")

print("\nпросроченные (слот в прошлом), по дню слота:")
для_всего = 0
for r in просрочены:
    print(f"  {r['d']}  {r['n']}")
    для_всего += int(r["n"])
print(f"  всего просроченных: {для_всего}")

if not КАТИТЬ:
    print("\nсухой прогон. Расклинить — --katit")
    raise SystemExit(0)

освобождено = 0
for mid, почта, инн in можно:
    try:
        store.release_message(int(mid))
        освобождено += 1
    except Exception as ex:                                      # noqa: BLE001
        print(f"  письмо {mid} не отпустилось: {str(ex)[:80]}")
print(f"\nвозвращено в очередь: {освобождено}")
