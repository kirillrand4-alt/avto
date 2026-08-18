# -*- coding: utf-8 -*-
"""Подтвердить письма в очереди — то же, что нажать «Отправить» в панели.

Владелец 18.08: «подтверждай». При confirm.live_send подтверждение уходит
НЕМЕДЛЕННО, окно отправки на ручную отправку не распространяется.

Идём тем же путём, что и панель: ConfirmSend.approve. Никаких прямых правок
статуса — иначе письмо просто ляжет в автоотправку и будет ждать окна.

    python zapusk_svoego_skripta.py ops/podtverdit_pisma_rukami.py 2602 2603 2604
    python zapusk_svoego_skripta.py ops/podtverdit_pisma_rukami.py 2602 --слать
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.wiring import build_deps                             # noqa: E402

СЛАТЬ = "--слать" in sys.argv
# Заслон «контакт был меньше 90 дней назад» здесь срабатывает не по делу:
# компания САМА назвала другой адрес («пишите вот сюда», «я на больничном,
# обращайтесь к»). Заслон видит только «этой фирме недавно писали». Обход
# рассчитан ровно на такой случай - второе подтверждение оператора, оно же
# force (решение владельца 26.07), и оно пишется в аудит.
ЧЕРЕЗ_ЗАСЛОН = "--через-заслон" in sys.argv
ids = [int(a) for a in sys.argv[1:] if a.isdigit()]
if not ids:
    print("укажи id писем")
    raise SystemExit(2)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
confirm = deps.confirm
print(f"confirm.live_send: {cfg.get('confirm.live_send', False)}")
print(f"боевой sender у подтверждения: "
      f"{getattr(confirm, '_sender', None) is not None}")

for cid in ids:
    row = store.confirm_get(cid) or {}
    print(f"\n#{cid} {row.get('email')} [{row.get('status')}] "
          f"{str(row.get('subject'))[:60]}")
    if row.get("status") != "pending":
        print("  не pending — пропускаю")
        continue
    if not СЛАТЬ:
        continue
    try:
        итог = confirm.approve(cid, operator="владелец (через сессию)",
                               force=ЧЕРЕЗ_ЗАСЛОН)
        print(f"  итог: {итог}")
    except Exception as ex:                                      # noqa: BLE001
        print(f"  СБОЙ: {type(ex).__name__} {str(ex)[:200]}")

if not СЛАТЬ:
    print("\nсухой прогон: ничего не отправлено. Слать — аргумент --слать")
