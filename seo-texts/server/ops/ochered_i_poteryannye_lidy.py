# -*- coding: utf-8 -*-
"""Почему в очереди видно 10 из 98 и куда делись два ответа.

Владелец 24.08: панель пишет «ждут подтверждения 98», а в списке он видит
десять. И отдельно: живых ответов сегодня четыре, а карточек лидов три,
причём одна из них — автоответ.

Догадка по очереди: карточку не показывают оператору, пока по её адресу
не пришёл вердикт пробы (confirm._zhdyot_verdikta). Тогда 88 писем ждут
работника на VPS, а показаны только готовые.

По лидам: два ответа пришли в 09:00:14 и 09:00:36 — «Сталь Технологии» и
«Агрокомбинат Тамбовкрахмал», — и лидов по ним нет. Разница 22 секунды,
значит причина общая, а не совпадение.
"""
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

СЕГОДНЯ = time.strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЯ: ЧТО В НЕЙ ===")
print("всего pending: %d"
      % c.execute("SELECT COUNT(*) FROM confirm_reviews "
                  "WHERE status='pending'").fetchone()[0])

try:
    from sender.config import Config
    from sender.store import Store
    from sender.suppression import Suppression
    from sender.confirm import ConfirmSend
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    cs = ConfirmSend(cfg, store, Suppression(store))
    строки = cs.pending(limit=100000)
    print("cs.pending() отдаёт: %d" % len(строки))
    ждут, готовы, причины = 0, 0, {}
    for r in строки:
        п = None
        try:
            п = cs._zhdyot_verdikta(r)
        except Exception as e:                                 # noqa: BLE001
            п = "проверка упала: %s" % str(e)[:60]
        if п:
            ждут += 1
            ключ = str(п).split(":")[0][:44]
            причины[ключ] = причины.get(ключ, 0) + 1
        else:
            готовы += 1
    print("  ждут вердикта пробы: %d" % ждут)
    print("  готовы к показу:     %d" % готовы)
    for к, н in sorted(причины.items(), key=lambda x: -x[1]):
        print("    %-46s %d" % (к, н))
except Exception as e:                                         # noqa: BLE001
    print("  панельные объекты не собрались: %s: %s"
          % (type(e).__name__, str(e)[:120]))

print("\n=== ДВА ПОТЕРЯННЫХ ОТВЕТА ===")
for пол in (2998, 7861):
    print("\n--- получатель %d ---" % пол)
    for р in c.execute(
            "SELECT id, event_type, event_ts, mailbox_id, detail_json "
            "  FROM events WHERE recipient_id=? "
            "   AND substr(event_ts,1,10)=? ORDER BY id", (пол, СЕГОДНЯ)):
        д = str(р["detail_json"] or "")
        # вытаскиваем только то, что говорит о РАЗБОРЕ, а не заголовки письма
        куски = []
        for ключ in ("kind", "class", "signal", "reply_kind", "snippet",
                     "reason", "lead", "from_addr", "thread_id"):
            и = д.find('"%s"' % ключ)
            if и >= 0:
                куски.append(д[и:и + 110].replace("\n", " "))
        print("  [%s] %s | %s" % (р["event_type"], str(р["event_ts"])[:19],
                                  str(р["mailbox_id"] or "?")[:30]))
        for к in куски:
            print("      %s" % к)
    ряд = c.execute("SELECT id, email, status FROM leads WHERE recipient_id=?",
                    (пол,)).fetchall()
    print("  лидов по этому получателю: %d" % len(ряд))
    for р in ряд:
        print("      #%s %s %s" % (р["id"], р["email"], р["status"]))

print("\n=== ЛИДЫ: ЕСТЬ ЛИ ОНИ ВООБЩЕ ПО ЭТИМ АДРЕСАМ ===")
for адрес in ("com@sttehnol.ru", "tambovkrahmal@mail.ru"):
    ряд = c.execute("SELECT id, status, created_at FROM leads WHERE email=?",
                    (адрес,)).fetchall()
    print("  %-26s лидов %d %s"
          % (адрес, len(ряд),
             " ".join("#%s/%s" % (р["id"], str(р["created_at"])[:10])
                      for р in ряд)))
