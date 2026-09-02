# -*- coding: utf-8 -*-
"""Только чтение: готова ли партия к отправке. Прогон всех 175 писем."""
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.store import Store                # noqa: E402
from sender.suppression import Suppression    # noqa: E402
from sender.company_card import CompanyCards  # noqa: E402
import sender.sender as S                     # noqa: E402
import sender.gates as G                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
карт = CompanyCards(index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store), cards=карт)
камп = store.get_campaign(12)
мейер = {m["mailbox_id"] for m in cfg.get("mailboxes", [])
         if str(m.get("division")) == "meyer"}

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
ряды = list(c.execute("SELECT id, recipient_id, mailbox_id, subject, body_rendered b,"
                      " status, scheduled_at FROM messages WHERE campaign_id=12"))

# --- 1. текст ---
беды = []
for р in ряды:
    т = р["b"] or ""
    сл = len(re.findall(r"[A-Za-zА-Яа-яЁё0-9_]+", т))
    if not (45 <= сл <= 200):
        беды.append("объём %d" % сл)
    if т.count("?") > 2:
        беды.append("вопросов %d" % т.count("?"))
    if "—" in т or "–" in т:
        беды.append("длинное тире")
    if not р["subject"] or len(р["subject"].split()) > 12:
        беды.append("тема")
    if "Готова " in т:
        беды.append("женский род в исходнике")
тел = len({р["b"] for р in ряды})
print("=== 1. ТЕКСТ ===")
print("  писем %d, уникальных тел %d, замечаний гейта %d" % (len(ряды), тел, len(беды)))
if беды:
    print("  " + str(Counter(беды).most_common(5)))

# --- 2. закрепление ---
Я = "i.kuznetsova@sort-systems.ru"
пин = sum(1 for р in ряды if р["mailbox_id"] == Я)
имя = sum(1 for р in ряды if "Ирина Кузнецова" in (р["b"] or ""))
разлад = sum(1 for р in ряды
             if ("Ирина Кузнецова" in (р["b"] or "")) != (р["mailbox_id"] == Я))
print("\n=== 2. ЗАКРЕПЛЕНИЕ ===")
print("  закреплено за Ириной %d, писем с её именем %d, расхождений %d"
      % (пин, имя, разлад))

# --- 3. подбор ящика ---
как_сейчас, как_надо = Counter(), Counter()
for р in ряды:
    rec = store.get_recipient(р["recipient_id"])
    msg = store.get_message(р["id"])
    a = snd.pick_mailbox(rec, камп) or "НЕ НАЙДЕН"
    b = snd.pick_mailbox(rec, камп, message=msg) or "НЕ НАЙДЕН"
    как_сейчас[a] += 1
    как_надо[b] += 1
чужие = sum(n for m, n in как_сейчас.items() if m not in мейер and m != "НЕ НАЙДЕН")
print("\n=== 3. ПОДБОР ЯЩИКА ===")
print("  как зовёт оркестратор сейчас (без message):")
for m, n in как_сейчас.most_common():
    print("     %-38s %3d %s" % (m, n, "<-- НЕ MEYER, письмо умрёт в skipped"
                                 if m not in мейер and m != "НЕ НАЙДЕН" else ""))
print("  сгорит впустую: %d из %d (%.0f%%)" % (чужие, len(ряды), 100.0 * чужие / len(ряды)))
print("  если передать message:")
for m, n in как_надо.most_common():
    print("     %-38s %3d" % (m, n))

# --- 4. прочее ---
print("\n=== 4. ПРОЧЕЕ ===")
for x in c.execute("SELECT status, COUNT(*) n FROM messages WHERE campaign_id=12"
                   " GROUP BY status"):
    print("  статус %s: %d" % (x["status"], x["n"]))
print("  срок отправки: %s" % ряды[0]["scheduled_at"])
for р in c.execute("SELECT mailbox_id, paused FROM mailbox_state"
                   " WHERE mailbox_id LIKE '%food-sort%'"):
    print("  %s: пауза=%s" % (р["mailbox_id"], р["paused"]))
