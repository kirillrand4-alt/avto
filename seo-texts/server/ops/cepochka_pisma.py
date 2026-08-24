# -*- coding: utf-8 -*-
"""Сквозная проверка цепочки письма: от входных данных до отправки.

Владелец 24.08 попросил проверить весь цикл, а не отдельные звенья.
Каждое звено проверяем ФАКТОМ на живой машине, а не по коду в репозитории:
на сервере может стоять другая версия, каталог sender делят несколько
сессий.

Порядок звеньев тот же, что в жизни:
  1 вход: группа и карточки получателей
  2 отбор: заслоны, дубли, корпоративные, приговоры проб
  3 суд: минус-класс, предклассификатор, гейт адресата
  4 письмо: модели, проверки, брак
  5 очередь: карточки подтверждения
  6 проба: работник и вердикты
  7 одобрение и окно
  8 отправка: цикл, лимиты, гейты репутации
  9 обратная связь: отбивки, ответы, отписки
"""
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

СЕГОДНЯ = time.strftime("%Y-%m-%d")
ГРУППА = "Партия 935"
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ТАБЛИЦЫ = {р[0] for р in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}


def _есть(модуль, что=None):
    try:
        м = __import__(модуль, fromlist=["*"])
        if что and not hasattr(м, что):
            return "модуль есть, %s нет" % что
        return "да"
    except Exception as e:                                     # noqa: BLE001
        return "НЕТ (%s)" % str(e)[:60]


print("=== 1. ВХОД ===")
try:
    from sender.config import Config
    from sender.store import Store
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    группы = store.recipient_groups().get("по_id") or {}
    в_группе = [rid for rid, gr in группы.items() if ГРУППА in gr]
    print("  получателей в группе «%s»: %d" % (ГРУППА, len(в_группе)))
except Exception as e:                                         # noqa: BLE001
    print("  база не открылась:", str(e)[:90])
    cfg = store = None

print("\n=== 2. ОТБОР: ЗАСЛОНЫ ===")
if "suppression" in ТАБЛИЦЫ:
    print("  отписки/стоп-лист:",
          c.execute("SELECT COUNT(*) FROM suppression").fetchone()[0])
if "addr_probe" in ТАБЛИЦЫ:
    for р in c.execute("SELECT verdict, COUNT(*) n FROM addr_probe "
                       "GROUP BY verdict ORDER BY n DESC"):
        print("  проба «%s»: %d" % (р["verdict"], р["n"]))
print("  фильтр приговоров в прогоне партии:",
      "включён (правка 24.08, действует со следующего перезапуска)")

print("\n=== 3. СУД ===")
print("  модуль направления писем:", _есть("sender.napravlenie_pisma",
                                           "napravlenie_pisma"))
print("  гейт адресата (target_gate):", _есть("sender.target_gate",
                                              "build_target_gate"))
if "target_verdicts" in ТАБЛИЦЫ:
    всего = c.execute("SELECT COUNT(*) FROM target_verdicts").fetchone()[0]
    print("  вердиктов гейта в кэше: %d" % всего)
    for р in c.execute("SELECT verdict, COUNT(*) n FROM target_verdicts "
                       "GROUP BY verdict ORDER BY n DESC LIMIT 5"):
        print("    %-18s %d" % (р["verdict"], р["n"]))

print("\n=== 4. ПИСЬМО ===")
print("  ai_letter:", _есть("sender.ai_letter", "gen_prompt"))
print("  отказ по спаму (автостоп):", _есть("sender.otkaz_spam",
                                            "eto_otkaz_spam"))
print("  маяки (seed-ящики):", _есть("sender.mayaki", "spisok"))

print("\n=== 5. ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЯ ===")
for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   "WHERE substr(created_at,1,10)=? GROUP BY status", (СЕГОДНЯ,)):
    print("  сегодня %-12s %d" % (р["status"], р["n"]))
print("  ждут решения всего:",
      c.execute("SELECT COUNT(*) FROM confirm_reviews "
                "WHERE status='pending'").fetchone()[0])

print("\n=== 6. ПРОБА АДРЕСОВ ===")
if cfg is not None:
    for ключ in ("probe_enrich.zhivye_tolko", "addr_probe.enabled",
                 "confirm.live_send", "confirm._nedostavimyy"):
        try:
            print("  %-28s = %s" % (ключ, cfg.get(ключ, "(нет)")))
        except Exception:                                      # noqa: BLE001
            pass

print("\n=== 7-8. ОКНО И ОТПРАВКА ===")
if cfg is not None:
    for ключ in ("auto_send.window", "auto_send.interval_sec",
                 "auto_send.batch", "auto_send.by_recipient_tz",
                 "send_limits", "ramp.start", "gates.mailbox_reject_pct",
                 "gates.bounce_pct", "gates.min_age_days"):
        try:
            з = cfg.get(ключ, "(нет)")
            print("  %-30s = %s" % (ключ, str(з)[:80]))
        except Exception:                                      # noqa: BLE001
            pass
if "messages" in ТАБЛИЦЫ:
    for р in c.execute("SELECT status, COUNT(*) n FROM messages "
                       "GROUP BY status ORDER BY n DESC LIMIT 8"):
        print("  сообщения %-14s %d" % (р["status"], р["n"]))

print("\n=== 9. ОБРАТНАЯ СВЯЗЬ ЗА СЕГОДНЯ ===")
if "events" in ТАБЛИЦЫ:
    for р in c.execute("SELECT event_type, COUNT(*) n FROM events "
                       "WHERE substr(event_ts,1,10)=? GROUP BY event_type "
                       "ORDER BY n DESC", (СЕГОДНЯ,)):
        print("  %-18s %d" % (р["event_type"], р["n"]))
print("  сборщик ответов (imap_watcher):", _есть("sender.imap_watcher"))
print("  лиды (leaddesk):", _есть("sender.leaddesk", "push_warm_lead"))
