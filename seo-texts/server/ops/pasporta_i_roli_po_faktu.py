# -*- coding: utf-8 -*-
"""Толщина паспорта против брака, и как ролевые адреса ведут себя у нас.

Паспорт есть у 99.7% кандидатов, но у трети он на два поля из шести.
Вопрос не «есть ли», а «хватает ли»: проверяем по сегодняшнему журналу,
чаще ли уходит в брак письмо к компании с тонким паспортом.

Про ролевые адреса (info@, sales@, office@) отвечаем не теорией, а нашей
же историей: сколько им отправлено, сколько отбилось, сколько ответили.
"""
import io
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.validation import _BASE_ROLE_PREFIXES as РОЛИ     # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
ПОЛЯ = ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб",
        "мощности")

print("настройка validation.role_based_risky = %s"
      % cfg.get("validation.role_based_risky", "(нет в конфиге)"))
print("настройка validation.detect_role      = %s"
      % cfg.get("validation.detect_role", "(нет в конфиге)"))

# --- паспорт против брака ------------------------------------------------ #
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
записи = []
for с in io.open(ЖУРНАЛ, encoding="utf-8"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if з.get("inn") and з.get("ок") is not None:
        записи.append(з)
записи = записи[-1200:]
print("\n=== ТОЛЩИНА ПАСПОРТА ПРОТИВ БРАКА (последние %d попыток) ===" % len(записи))
кэш = {}
свод = defaultdict(lambda: [0, 0])       # полей -> [всего, брак]
for з in записи:
    inn = str(з.get("inn"))
    if inn not in кэш:
        try:
            d = q._site_facts(inn) or {}
        except Exception:  # noqa: BLE001
            d = {}
        кэш[inn] = sum(1 for к in ПОЛЯ if d.get(к))
    полей = кэш[inn]
    свод[полей][0] += 1
    if not з.get("ок"):
        свод[полей][1] += 1
print("  %-8s %8s %8s %8s" % ("полей", "попыток", "брак", "доля брака"))
for полей in sorted(свод, reverse=True):
    всего, брак = свод[полей]
    print("  %-8d %8d %8d %7.1f%%  %s"
          % (полей, всего, брак, 100.0 * брак / всего if всего else 0,
             "#" * int(20.0 * брак / всего) if всего else ""))

# --- ролевые адреса по нашей истории ------------------------------------- #
print("\n=== РОЛЕВЫЕ АДРЕСА: ЧТО БЫЛО У НАС ===")
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
итог = {"ролевой": Counter(), "именной": Counter()}
for р in c.execute(
        "SELECT r.email, m.id mid FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status='sent'"):
    вид = ("ролевой" if str(р["email"]).split("@")[0].strip().lower() in РОЛИ
           else "именной")
    итог[вид]["отправлено"] += 1
    итог[вид]["_ид"] = итог[вид].get("_ид", 0)
# события по видам
ид_вид = {}
for р in c.execute("SELECT id, email FROM recipients"):
    ид_вид[р["id"]] = ("ролевой"
                       if str(р["email"]).split("@")[0].strip().lower() in РОЛИ
                       else "именной")
for р in c.execute(
        "SELECT recipient_id, event_type, COUNT(*) n FROM events "
        " WHERE event_type IN ('bounce','reply') GROUP BY recipient_id, event_type"):
    вид = ид_вид.get(р["recipient_id"])
    if вид:
        итог[вид][р["event_type"]] += р["n"]
print("  %-10s %10s %8s %8s %8s %8s"
      % ("вид", "отправлено", "отбивок", "%", "ответов", "%"))
for вид in ("ролевой", "именной"):
    о = итог[вид]["отправлено"]
    б = итог[вид]["bounce"]
    от = итог[вид]["reply"]
    print("  %-10s %10d %8d %7.1f%% %8d %7.1f%%"
          % (вид, о, б, 100.0 * б / о if о else 0, от,
             100.0 * от / о if о else 0))

print("\n=== КАКИЕ ИМЕННО РОЛИ В КАНДИДАТАХ ===")
роли = Counter()
for р in c.execute("SELECT email FROM recipients"):
    л = str(р["email"]).split("@")[0].strip().lower()
    if л in РОЛИ:
        роли[л] += 1
for к, н in роли.most_common(12):
    print("  %-14s %5d" % (к + "@", н))
