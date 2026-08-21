# -*- coding: utf-8 -*-
"""Досчитать panel_json карточкам вебинара 28.08.

Панель оператора показывает НЕ живые данные, а СНИМОК: столбец
confirm_reviews.panel_json, который штатный confirm.submit собирает в
момент постановки. Карточки вебинара заводились прямым INSERT (заслон
submit резал бы повторные контакты, а владелец их разрешил), и снимок
остался пустым - отсюда «нет данных компании в карточке» при том, что в
enrich.db все 54 ИНН на месте.

Собираем тем же infopanel.build_panel и теми же источниками, что
ai_quota: строка companies + emails + signals из enrich.db плюс карточка
базы обзвона (в ней выручка и директор). Своей копии логики не заводим.
Без аргумента - сухой прогон.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.infopanel import build_panel, load_enrich_lead    # noqa: E402
from sender.store import Store                                # noqa: E402

писать = len(sys.argv) > 1 and sys.argv[1] == "primenit"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
енрич = getattr(q, "_enrich_db", None) or r"C:\sender\enrich.db"

with store._lock:
    карточки = store._conn.execute(
        "SELECT id, inn, email, subject, body, status, "
        "       panel_json IS NOT NULL AS есть "
        "  FROM confirm_reviews WHERE dedup_key LIKE 'vebinar28:%' "
        " ORDER BY id").fetchall()
пусто = [к for к in карточки if not к[6] and к[5] == "pending"]
print(f"карточек вебинара: {len(карточки)}, без снимка панели: {len(пусто)}")
if not писать:
    print("сухой прогон: ничего не менял (primenit — записать)")
    raise SystemExit(0)

готово, сбои = 0, 0
for кид, инн, почта, тема, тело, _ст, _е in пусто:
    try:
        ctx = load_enrich_lead(str(инн or ""), db_path=енрич, email=почта)
        карта = q._card_for(инн) if инн else None
        снимок = build_panel(
            inn=str(инн) if инн else None, email=почта,
            letter_subject=тема, letter_body=тело,
            company=ctx.get("company") or {},
            emails=ctx.get("emails") or [],
            signals=ctx.get("signals") or [], store=store,
            card=карта, signature=q._signature_preview("meyer"))
        store.confirm_set_panel(int(кид), снимок)
        готово += 1
    except Exception as ex:                                   # noqa: BLE001
        сбои += 1
        print(f"  №{кид}: {type(ex).__name__} {str(ex)[:100]}")
print(f"\nснимок собран: {готово}, сбоев: {сбои}")
