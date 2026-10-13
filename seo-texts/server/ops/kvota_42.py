# -*- coding: utf-8 -*-
"""Кого из списка 500 по пробе сняла квота компании: что им уже ушло и когда."""
import io
import json
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.suppression import Suppression  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
print("потолок адресов на компанию: %s за %s дней" % (cs._potolok_kompanii(), cs._okno_dney()))
ид = json.load(io.open(r"C:\sender\_ops\partiya-500-proba.json", encoding="utf-8"))
мес, сколько, в_работе = Counter(), Counter(), 0
примеры = []
список = []
for rid in ид:
    rec = store.get_recipient(rid)
    inn = "".join(c for c in str(rec.inn or "") if c.isdigit())
    ушло = [r for r in store.send_log_history(inn=inn, limit=500)
            if str(r.get("outcome")) == "sent" and cs._v_okne(str(r.get("ts") or "")) is not False]
    адреса = {str(r.get("email")).lower() for r in ушло} - {str(rec.email or "").lower()}
    # снятые прежним потолком 2 (12.10) — считаем по факту отправок, а не
    # по текущей настройке: после подъёма потолка _guard их уже пропускает
    if len(адреса) < 2:
        continue
    список.append(rid)
    раб = cs._adresa_v_rabote(inn) - адреса
    в_работе += 1 if раб else 0
    сколько[len(адреса)] += 1
    for r in ушло:
        мес[str(r.get("ts"))[:7]] += 1
    if len(примеры) < 8:
        примеры.append("%s | ушло на %d адр.: %s | в очереди ещё %d" % (
            rec.company_name[:30], len(адреса),
            ", ".join(sorted({str(r.get('ts'))[:10] for r in ушло})[:3]), len(раб)))
print("снято квотой: %d" % sum(сколько.values()))
print("уже ушло писем на разные адреса: %s" % dict(сколько))
print("у скольких ещё письмо стоит в очереди: %d" % в_работе)
print("по месяцам отправки: %s" % dict(sorted(мес.items())))
for п in примеры:
    print("   " + п)
if "--spisok" in sys.argv:
    with io.open(r"C:\sender\_ops\partiya-kvota-42.json", "w", encoding="utf-8") as ф:
        json.dump(список, ф)
    print("список: _ops/partiya-kvota-42.json, %d" % len(список))
print("=== КВОТА 42 ===")
