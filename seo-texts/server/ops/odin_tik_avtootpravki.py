# -*- coding: utf-8 -*-
"""Один тик автоотправки вне панели: работает ли сама машинка.

После перезапуска панели письма всё равно не уходят, хотя 24 письма проходят
все проверки. Логи цикла пусты. Значит надо спросить не логи, а саму машинку:
собираем ТОТ ЖЕ AutoSendLoop и делаем РОВНО ОДИН тик с batch=1.

Письмо, которое он возьмёт, одобрено оператором и созрело по окну — это не
новая отправка, а ровно та, которую цикл и должен был сделать. Двойной
отправки быть не может: claim_approved_due переводит письмо в 'sending'
атомарно, панель ту же строку уже не возьмёт.

Пароли ящиков лежат в C:\\sender\\panel.env (панель получает их через nssm).
Читаем файл в окружение процесса; ЗНАЧЕНИЯ НЕ ПЕЧАТАЕМ - только «есть/нет».

    python zapusk_svoego_skripta.py ops/odin_tik_avtootpravki.py            # разбор без отправки
    python zapusk_svoego_skripta.py ops/odin_tik_avtootpravki.py --послать  # один тик
"""
import io
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")

ПОСЛАТЬ = "--послать" in sys.argv

# 1. окружение с паролями ящиков
путь_env = r"C:\sender\panel.env"
взято = 0
if os.path.exists(путь_env):
    for строка in io.open(путь_env, encoding="utf-8-sig", errors="replace"):
        строка = строка.strip()
        if not строка or строка.startswith("#") or "=" not in строка:
            continue
        к, _, з = строка.partition("=")
        к, з = к.strip(), з.split(" #")[0].strip()
        if к and з and к not in os.environ:
            os.environ[к] = з
            взято += 1
print(f"переменных из panel.env подхвачено: {взято}")

from sender.auto_send import AutoSendLoop                         # noqa: E402
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
живой = getattr(deps, "live_sender", None)
print(f"confirm.live_send: {cfg.get('confirm.live_send', False)}")
print(f"боевой sender собран: {живой is not None}, "
      f"dry_run={getattr(живой, 'dry_run', '?')}")

цикл = AutoSendLoop(store=store, config=cfg, live_sender=живой, batch=1)
print(f"цикл.enabled(): {цикл.enabled()}")

# пароли: только факт наличия
нет_пароля = []
for mb in cfg.mailboxes():
    имя = getattr(mb, "password_env", "") or ""
    if имя and not (os.environ.get(имя) or "").strip():
        нет_пароля.append(mb.mailbox_id)
print(f"ящиков без пароля в окружении: {len(нет_пароля)}"
      + (f" -> {нет_пароля[:5]}" if нет_пароля else ""))

if not ПОСЛАТЬ:
    print("\nразбор без отправки. Сделать один тик — аргумент --послать")
    raise SystemExit(0)
if живой is None or нет_пароля:
    print("\nтик НЕ делаю: нет боевого сендера или нет паролей")
    raise SystemExit(2)

до = store._conn.execute(
    "SELECT COUNT(*) FROM messages WHERE status='scheduled'").fetchone()[0]
итог = цикл.tick()
после = store._conn.execute(
    "SELECT COUNT(*) FROM messages WHERE status='scheduled'").fetchone()[0]
print(f"\nрезультат тика: {итог}")
print(f"очередь scheduled: было {до}, стало {после}")
with store._lock:
    посл = store._conn.execute(
        "SELECT event_ts, mailbox_id FROM events WHERE event_type='sent' "
        "ORDER BY event_ts DESC LIMIT 3").fetchall()
print("последние отправки:")
for ts, mb in посл:
    print(f"  {str(ts)[:19]}  {mb}")
