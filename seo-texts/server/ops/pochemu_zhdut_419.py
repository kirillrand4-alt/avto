# -*- coding: utf-8 -*-
"""Почему письма стоят и не уходят: статусы, окно, лимиты, гейты."""
import sys, time
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.gates import Gates                                  # noqa: E402
from sender.sender import Sender                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
теперь = datetime.now(timezone.utc)
print("сейчас UTC: %s | местное: %s"
      % (теперь.strftime("%Y-%m-%d %H:%M"), time.strftime("%Y-%m-%d %H:%M")))
print("окно отправки в конфиге: %s - %s, tz=%s"
      % (cfg.get("sending.window_start", "?"), cfg.get("sending.window_end", "?"),
         cfg.get("sending.timezone", "?")))
print("рассылка на паузе: %s" % cfg.get("sending.paused", "?"))
print("режим подтверждения confirm.mode: %s" % cfg.get("confirm.mode", "?"))
print("реальная отправка confirm.live_send: %s" % cfg.get("confirm.live_send", "?"))

статусы = Counter()
with store._lock:
    for р in store._conn.execute("SELECT status, COUNT(*) c FROM messages "
                                 " GROUP BY status"):
        статусы[str(р["status"])] = int(р["c"])
print("")
print("--- письма по статусам (вся база) ---")
for к, в in статусы.most_common():
    print("   %-18s %6d" % (к, в))

# кто именно ждёт
ЖДУТ = ("scheduled", "queued", "pending", "ready")
есть = [s for s in ЖДУТ if статусы.get(s)]
for s in есть:
    with store._lock:
        стр = store._conn.execute(
            """SELECT m.id, m.campaign_id, m.mailbox_id, m.scheduled_at,
                      m.attempt_count, m.last_error, r.mx_provider, r.email
                 FROM messages m LEFT JOIN recipients r ON m.recipient_id = r.id
                WHERE m.status=? LIMIT 2000""", (s,)).fetchall()
    по_кампании = Counter(str(р["campaign_id"]) for р in стр)
    по_ящику = Counter(str(р["mailbox_id"] or "НЕ ЗАДАН") for р in стр)
    по_пров = Counter(str(р["mx_provider"] or "?") for р in стр)
    ошибки = Counter(str(р["last_error"] or "нет")[:60] for р in стр)
    print("")
    print("--- статус %s: %d ---" % (s, len(стр)))
    print("   по кампании: %s" % dict(по_кампании.most_common(5)))
    print("   по ящику:    %s" % dict(по_ящику.most_common(5)))
    print("   провайдер:   %s" % dict(по_пров.most_common(5)))
    for к, в in ошибки.most_common(4):
        print("   ошибка: %-60s %5d" % (к, в))

# что скажет сам сендер про ящики прямо сейчас
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=True)
готовы = Counter()
примеры = []
for mb in cfg.mailboxes():
    mid = str(getattr(mb, "mailbox_id", ""))
    если_можно = snd.can_send_now(mid, now=теперь, manual=False)
    вручную = snd.can_send_now(mid, now=теперь, manual=True)
    готовы["авто: %s / вручную: %s" % (если_можно, вручную)] += 1
    if not если_можно and len(примеры) < 6:
        примеры.append((mid, str(getattr(mb, "division", "?"))))
print("")
print("=" * 74)
print("=== МОЖНО ЛИ СЛАТЬ ПРЯМО СЕЙЧАС ===")
for к, в in готовы.most_common():
    print("   %-34s ящиков %d" % (к, в))
for mid, d in примеры:
    print("   закрыт сейчас: %-40s напр=%s" % (mid[:40], d))
