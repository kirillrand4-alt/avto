# -*- coding: utf-8 -*-
"""Настоящий потолок ящиков: кривая разогрева и день каждого ящика.

Владелец держит цель 600 писем КЦ в сутки. Замер 24.08 показал, что все
четырнадцать КЦ-ящиков стоят ровно на 10-11 письмах, тогда как
мейеровские разогнаны до 18-44. Это не разброс, а упор в потолок.

Прошлый мой вызов рампы дал нули — я звал daily_send_limit(provider,
ramp_day, mailbox), а сигнатура daily_send_limit(config, provider,
ramp_day). Судить по тем нулям было нельзя, здесь считаем правильно.

Печатаем кривую целиком по каждому провайдеру, день разогрева каждого
ящика и положенный ему потолок — и сразу видно, сколько КЦ может дать
сегодня, сколько через неделю и чего не хватает до шестисот.
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.config import Config                               # noqa: E402
from sender.ramp import daily_send_limit                       # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== КРИВЫЕ РАЗОГРЕВА ===")
for пров in ("yandex", "mailru", "other", ""):
    try:
        кривая = cfg.ramp_curve(пров) or []
    except Exception as e:                                     # noqa: BLE001
        print("  %-8s кривой нет (%s)" % (пров or "(пусто)", str(e)[:50]))
        continue
    print("  %-8s %s" % (пров or "(пусто)", str(кривая)[:150]))

print("\n=== ЯЩИКИ: ДЕНЬ, ПОТОЛОК, ФАКТ ===")
print("%-42s %-8s %-5s %-7s %-6s %s"
      % ("ящик", "провайд", "день", "потолок", "ушло", "пауза"))
итог = {}
for р in c.execute(
        "SELECT mailbox_id, provider, ramp_day, sent_today, paused, "
        "       pause_reason FROM mailbox_state ORDER BY mailbox_id"):
    try:
        потолок = daily_send_limit(cfg, р["provider"], р["ramp_day"])
    except Exception as e:                                     # noqa: BLE001
        потолок = "сбой: %s" % str(e)[:30]
    напр = "meyer" if any(с in str(р["mailbox_id"]) for с in
                          ("sort", "optic", "zerno")) else "kc"
    if isinstance(потолок, int):
        итог.setdefault(напр, [0, 0])
        итог[напр][0] += потолок
        итог[напр][1] += int(р["sent_today"] or 0)
    print("%-42s %-8s %-5s %-7s %-6s %s"
          % (str(р["mailbox_id"])[:42], str(р["provider"] or "?")[:8],
             р["ramp_day"], потолок, р["sent_today"],
             ("ПАУЗА " + str(р["pause_reason"] or "")[:30]) if р["paused"]
             else "—"))

print("\n=== СВОДКА ПО НАПРАВЛЕНИЯМ ===")
for напр, (потолок, ушло) in sorted(итог.items()):
    print("  %-6s суммарный потолок сегодня %-5s | фактически ушло %s"
          % (напр, потолок, ушло))

print("\n=== ЧТО БУДЕТ ЧЕРЕЗ НЕДЕЛЮ И ЧЕРЕЗ ДВЕ ===")
for сдвиг in (7, 14):
    свод = {}
    for р in c.execute("SELECT mailbox_id, provider, ramp_day "
                       "  FROM mailbox_state"):
        напр = "meyer" if any(с in str(р["mailbox_id"]) for с in
                              ("sort", "optic", "zerno")) else "kc"
        try:
            свод[напр] = свод.get(напр, 0) + daily_send_limit(
                cfg, р["provider"], (р["ramp_day"] or 0) + сдвиг)
        except Exception:                                      # noqa: BLE001
            pass
    print("  через %2d дней: %s" % (сдвиг, свод))
