# -*- coding: utf-8 -*-
"""Снять из очереди тех, кому уже писали когда-либо.

Владелец 19.08, глядя на очередь: «ну кому писали естественно скип».

Штатный заслон confirm._guard режет только контакт СВЕЖЕЕ 90 ДНЕЙ
(recent_contact<90d). Панель же метит красным «писали» по другому признаку —
send_log.ever, то есть любое касание в прошлом, хоть год назад. Из-за этого
письма к давним адресатам проходили заслон и попадали в очередь.

Решение владельца: снимать при ЛЮБОМ прошлом касании, а не только свежем.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КАТИТЬ = "--katit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    # И ОДОБРЕННЫЕ, И НЕРЕШЁННЫЕ. Красные пометки «писали» на экране
    # владельца стояли у НЕРЕШЁННЫХ карточек — до отправки они не доходят,
    # но занимают очередь и глаза оператора. Снимаем и тех, и других.
    строки = store._conn.execute(
        "SELECT c.id, c.campaign_id, c.email, c.status, r.inn, r.company_name "
        "FROM confirm_reviews c "
        "LEFT JOIN recipients r ON r.id=c.recipient_id "
        "WHERE c.campaign_id IN (10,11) "
        "AND c.status IN ('approved','edited','pending') "
        # ТОЛЬКО ТЕ, ЧЬЁ ПИСЬМО ЕЩЁ НЕ УШЛО. Без этого условия выборка
        # набрала 1167 карточек, у которых письмо отправлено 17-18 августа
        # нашей же кампанией: «писали» там стоит по нашему же следу, и
        # снимать отправленное бессмысленно.
        "AND (c.message_id IS NULL OR EXISTS (SELECT 1 FROM messages m "
        "     WHERE m.id=c.message_id AND m.status NOT IN "
        "           ('sent','failed','skipped')))").fetchall()

инн = [r["inn"] for r in строки if r["inn"]]
почты = [r["email"] for r in строки if r["email"]]
флаги = store.sent_flags(inns=инн, emails=почты)

счёт = Counter()
на_снятие = []
for r in строки:
    ц = "".join(c for c in str(r["inn"] or "") if c.isdigit())
    e = str(r["email"] or "").strip().lower()
    f = флаги.get(ц) or флаги.get(e) or {}
    if f.get("ever"):
        когда = str(f.get("last_ts") or "")[:10]
        свежо = " (свежее 90 дней)" if f.get("within_90d") else ""
        отв = " (ОТВЕТИЛИ)" if f.get("replied") else ""
        на_снятие.append((int(r["id"]), когда, свежо + отв,
                          r["company_name"], e))
        счёт[f"писали ранее{свежо}{отв}"] += 1
    else:
        счёт["не писали — оставляем"] += 1

from collections import Counter as _C
print("карточек в работе:", dict(_C(str(r["status"]) for r in строки)))
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")
print("\n== примеры на снятие ==")
for i, когда, п, ф, e in на_снятие[:10]:
    print(f"  #{i} {когда} {e} — {str(ф)[:34]}{п}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить — --katit")
    raise SystemExit(0)

снято = 0
for i, когда, п, ф, e in на_снятие:
    try:
        ок = store.confirm_decide(
            i, status="skipped",
            reason=f"этому адресу/ИНН уже писали ({когда}){п}",
            decided_by="разбор очереди 19.08 (решение владельца)")
        снято += 1 if ок is not False else 0
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{i}: {str(ex)[:90]}")
print(f"\nснято: {снято}")
