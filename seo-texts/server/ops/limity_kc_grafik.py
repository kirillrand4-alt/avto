# -*- coding: utf-8 -*-
"""График лимитов ящиков КЦ (владелец 15.10): всем ящикам КЦ — 10 сегодня,
15 завтра, 25 в понедельник, 35 во вторник, 50 в среду, 66 в четверг.
В выходные держим пятничные 15.

Механика панели: дневной лимит = рамп-кривая провайдера, а ручной потолок
send_limits.per_mailbox умеет только ПРИЖАТЬ её. Поэтому:
  * рамп-день ящиков КЦ поднимаем до 11 (кривая yandex даёт 80) — база с запасом;
  * потолок per_mailbox = значение графика на сегодня.
Запускать каждый день (рутина в 00:05 МСК). Идемпотентно; без даты в графике
(после четверга) — потолок не трогает и пишет об этом.

    limity_kc_grafik.py [--primenit]
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402

ГРАФИК = {"2026-10-15": 10, "2026-10-16": 15, "2026-10-17": 15, "2026-10-18": 15,
          "2026-10-19": 25, "2026-10-20": 35, "2026-10-21": 50, "2026-10-22": 66}
сегодня = time.strftime("%Y-%m-%d")
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
кц = [mb.mailbox_id for mb in cfg.mailboxes() if mb.division == "kc"]
# После графика — постоянный потолок 40 (владелец 22.10, после паузы КЦ по
# спаму: «снизь до 40»). --limit=N — потолок прямо сейчас, мимо графика.
ПОСЛЕ_ГРАФИКА = 40
лимит = ГРАФИК.get(сегодня) or (ПОСЛЕ_ГРАФИКА if сегодня > max(ГРАФИК) else None)
лимит = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--limit=")), лимит)
print("сегодня %s, ящиков КЦ %d, лимит по графику: %s" % (сегодня, len(кц), лимит))
if лимит is None:
    print("=== ЛИМИТЫ КЦ: график кончился, не трогаю ===")
    sys.exit(0)
if "--primenit" not in sys.argv:
    print("=== ЛИМИТЫ КЦ: сухой прогон ===")
    sys.exit(0)
сл = st.get_setting("send_limits") or {}
if isinstance(сл, str):
    сл = json.loads(сл or "{}")
пер = dict(сл.get("per_mailbox") or {})
for м in кц:
    пер[м] = лимит
сл["per_mailbox"] = пер
st.set_setting("send_limits", сл)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
with c:
    н = c.execute("UPDATE mailbox_state SET ramp_day=11 WHERE ramp_day<11 AND mailbox_id IN (%s)"
                  % ",".join("?" * len(кц)), кц).rowcount
ключ_дня = (c.execute("SELECT day_key FROM mailbox_state ORDER BY updated_at DESC LIMIT 1").fetchone() or [сегодня])[0]
нет = [м for м in кц if not c.execute("SELECT 1 FROM mailbox_state WHERE mailbox_id=?", (м,)).fetchone()]
if нет:
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    with c:
        for м in нет:
            c.execute("INSERT INTO mailbox_state (mailbox_id, provider, day_key, ramp_day, daily_limit, updated_at) "
                      "VALUES (?,?,?,?,?,?)",
                      (м, next(mb.provider for mb in cfg.mailboxes() if mb.mailbox_id == м), ключ_дня, 11, лимит, т))
print("потолок %d на %d ящиков; рамп-день поднят у %d, заведено состояний %d" % (лимит, len(кц), н, len(нет)))
print("=== ЛИМИТЫ КЦ: ПРИМЕНЕНО ===")
