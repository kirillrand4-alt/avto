# -*- coding: utf-8 -*-
"""Что значит «сработал гейт репутации» на конкретном ящике - числами.

Гейт репутации по ящику: доля жёстких отбивок среди отправленного за окно
(gates.window_days) выше порога gates.mailbox_bounce_pct, и отправлено уже
достаточно, чтобы доля что-то значила (gates.min_volume). Смысл простой:
почтовые провайдеры считают отбивки признаком рассылки по мусорной базе, и
при 3-5% начинают резать домен целиком. Гейт останавливает ЯЩИК раньше, чем
это сделает Mail.ru или Яндекс - и остановленный ящик автоотправка не берёт.

Отбивка отбивке рознь, и с 18.08 гейт это различает: в долю идут только
МЁРТВЫЕ адреса, а отказ по политике («blocked due to security reason» —
ящик живой, письмо завернул фильтр) показан отдельной колонкой и порога не
трогает. До этой правки два ящика из четырёх были заперты именно policy.

Печатаем по каждому ящику: отправлено, мёртвых, policy, доля, вердикт; а по
сработавшим - поимённо письма, которые дали отбивки.

    python zapusk_svoego_skripta.py ops/gejt_reputacii_pochemu.py
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.wiring import build_deps                             # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
g = deps.gates
c = cfg.gates()

print(f"пороги: отбивок на ящик {c.mailbox_bounce_pct}% | "
      f"минимальный объём {c.min_volume} писем | окно {c.window_days} дней")
print(f"        отбивок на домен {c.domain_bounce_pct}% | "
      f"жалоб глобально {c.global_complaint_pct}% | "
      f"отбивок на провайдера {c.provider_bounce_pct}%\n")

сработавшие = []
print(f"{'ящик':<38} {'отпр':>5} {'мёртв':>6} {'policy':>7} {'доля':>7}  "
      "вердикт")
для_окна = g._since()
for mb in cfg.mailboxes():
    d = g.check_mailbox(mb.mailbox_id)
    отпр = g._count("sent", mailbox_id=mb.mailbox_id, since=для_окна)
    все_отб = g._count("bounce", mailbox_id=mb.mailbox_id, since=для_окна)
    мёртв = g._count("bounce", mailbox_id=mb.mailbox_id, since=для_окна,
                     exclude_policy=True)
    метка = "СРАБОТАЛ" if d.tripped else ("ок" if отпр else "нет отправок")
    if d.tripped:
        сработавшие.append(mb.mailbox_id)
    print(f"  {mb.mailbox_id:<36} {отпр:>5} {мёртв:>6} "
          f"{все_отб - мёртв:>7} {d.value:>6.1f}%  {метка} "
          f"(порог {d.threshold}%)")

for mid in сработавшие:
    print(f"\n=== {mid}: письма, давшие отбивки за окно")
    with store._lock:
        ряд = store._conn.execute(
            "SELECT e.event_ts, r.email, r.company_name, e.detail_json "
            "FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
            "WHERE e.event_type='bounce' AND e.mailbox_id=? "
            "ORDER BY e.event_ts DESC LIMIT 40", (mid,)).fetchall()
    for ts, email, фирма, dj in ряд:
        текст = ""
        try:
            import json as _j
            d = (_j.loads(dj or "{}").get("dsn") or {})
            текст = f"{d.get('verdict') or '?'}: {str(d.get('diagnostic') or '')[:70]}"
        except Exception:                                        # noqa: BLE001
            текст = str(dj or "")[:70]
        print(f"  {str(ts)[:19]}  {str(email or '-'):<32} {текст}")

print("\n=== что гейт делает с ящиком")
for mid in сработавшие or [m.mailbox_id for m in cfg.mailboxes()][:1]:
    r = deps.sender.mailbox_readiness(mid)
    print(f"  {mid}: готов={r.ready} причины={list(r.reasons)} "
          f"пауза={r.paused} лимит={r.daily_limit} сегодня={r.sent_today}")
