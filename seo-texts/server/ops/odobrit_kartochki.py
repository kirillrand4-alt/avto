# -*- coding: utf-8 -*-
"""Одобрить карточки «Подтвердить отправку» по id — штатный approve (при
confirm.live_send письмо уходит сразу). Владелец 20.10 разрешил отправить
письма по переадресациям (Постак, АКОМ) без кнопки.

    odobrit_kartochki.py <id,id,...> [--katit]

Без --katit — только показать карточки. force — только с --force: без него если заслон
держит (стоп-лист, проба, 90 дней), письмо не уходит и печатается причина."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                     # noqa: E402
from sender.store import Store                       # noqa: E402
from sender.suppression import Suppression           # noqa: E402
from sender.wiring import build_deps                 # noqa: E402

ид = [int(x) for x in sys.argv[1].split(",")]
КАТИТЬ = "--katit" in sys.argv
# --force: двойное подтверждение оператора (обход в аудит). Только по прямой
# команде владельца на конкретные карточки (20.10: Постак — ответ «занимается тех
# служба» классифицирован как отказ, а это переадресация).
СИЛОЙ = "--force" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
for i in ид:
    r = store._conn.execute("SELECT id, email, subject, status FROM confirm_reviews WHERE id=?", (i,)).fetchone()
    print("#%s %s | %s | %s" % tuple(r) if r else "#%d нет такой карточки" % i)
if not КАТИТЬ:
    print("сухой прогон. Отправка — --katit")
    raise SystemExit(0)
deps = build_deps(cfg, store, dry_run=False)
cs = deps.confirm
print("живая отправка:", getattr(cs, "_sender", None) is not None)
for i in ид:
    try:
        ок = cs.approve(i, operator="Claude по команде владельца 20.10", force=СИЛОЙ)
        r = store._conn.execute("SELECT c.status, m.status, m.mailbox_id, m.last_error FROM confirm_reviews c "
                                "LEFT JOIN messages m ON m.id=c.message_id WHERE c.id=?", (i,)).fetchone()
        print("#%d approve=%s | карточка %s | письмо %s | ящик %s | %s" % ((i, ок) + tuple(r)))
    except Exception as ex:  # noqa: BLE001
        print("#%d НЕ УШЛО: %s" % (i, str(ex)[:300]))
