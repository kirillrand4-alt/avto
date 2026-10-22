# -*- coding: utf-8 -*-
"""Отправить РУЧНОЙ ответ оператора, застрявший из-за паузы ящика треда
(владелец 22.10: «отправь ты, разрешаю»): ответ «Котэс-Ит» встал, потому что
ящик КЦ igor.lyapin на паузе по спам-гейту направления. Снимаем паузу ТОЛЬКО с
ящика треда, штатный approve карточки (live_send), и ВСЕГДА (finally) ставим
паузу обратно с прежней причиной.
    otvet_cherez_pauzu.py <id карточки> <ящик>"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402

kid, ящик = int(sys.argv[1]), sys.argv[2]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
s = store.get_mailbox_state(ящик)
была = bool(getattr(s, "paused", False)) if s else False
причина = getattr(s, "pause_reason", None) if s else None
print("ящик %s: пауза=%s (%s)" % (ящик, была, причина))
deps = build_deps(cfg, store, dry_run=False)
# Дневной потолок: ящик мог уже выбрать сегодняшний лимит (22.10: ушло 55 при
# потолке 40) — на время одного ответа даём ему +1, потом возвращаем как было.
import json  # noqa: E402
сл = store.get_setting("send_limits") or {}
if isinstance(сл, str):
    сл = json.loads(сл or "{}")
пм = dict(сл.get("per_mailbox") or {})
был_потолок = пм.get(ящик, "нет")
ушло = int(getattr(s, "sent_today", 0) or 0) if s else 0
try:
    if была:
        store.set_mailbox_paused(ящик, False, None)
    if был_потолок != "нет" and int(был_потолок) <= ушло:
        store.set_setting("send_limits", dict(сл, per_mailbox=dict(пм, **{ящик: ушло + 1})))
        print("потолок на время ответа: %s -> %s" % (был_потолок, ушло + 1))
    # --force: снятой паузы мало — спам-гейт НАПРАВЛЕНИЯ (20 за сутки по КЦ)
    # тоже не даёт ящик; force — штатный обход оператора с записью в аудит.
    ок = deps.confirm.approve(kid, operator="kirill (через Claude, 22.10: «отправь ты, разрешаю»)",
                              force="--force" in sys.argv)
    r = store._conn.execute("SELECT status FROM confirm_reviews WHERE id=?", (kid,)).fetchone()
    print("approve=%s | карточка: %s" % (ок, r[0] if r else "?"))
except Exception as ex:  # noqa: BLE001
    print("НЕ УШЛО: %s" % str(ex)[:400])
finally:
    if был_потолок != "нет":
        тек = store.get_setting("send_limits") or {}
        if isinstance(тек, str):
            тек = json.loads(тек or "{}")
        тек_пм = dict(тек.get("per_mailbox") or {})
        тек_пм[ящик] = был_потолок
        store.set_setting("send_limits", dict(тек, per_mailbox=тек_пм))
        print("потолок возвращён:", был_потолок)
    if была:
        store.set_mailbox_paused(ящик, True, причина)
        print("пауза возвращена:", getattr(store.get_mailbox_state(ящик), "paused", None))
