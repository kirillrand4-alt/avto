# -*- coding: utf-8 -*-
"""Живой вызов pick_mailbox по карточкам партии: какой ящик реально выберется.

Читать код мало: маршрут зависит от mx_provider получателя, гейта
направлений и дневных лимитов. Спрашиваем сам подборщик, как при ручном
подтверждении (manual=True - окно и пейсинг не учитываются).

Ничего не отправляет и ничего не пишет.
"""
import random
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.gates import Gates                                  # noqa: E402
from sender.sender import Sender                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ТЕМА = "для качества: вопрос по сортировке зерна"
СКОЛЬКО = 300
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
карты = None
try:
    from sender.company_cards import CompanyCards
    карты = CompanyCards(r"C:\sender\obzvon-index.db")
except Exception as ex:                                         # noqa: BLE001
    print("карточки обзвона не поднялись (%s) - гейт направлений будет мягче"
          % str(ex)[:70])
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=True,
             cards=карты)

with store._lock:
    строки = store._conn.execute(
        """SELECT c.recipient_id, c.campaign_id, c.email, m.id AS mid
             FROM confirm_reviews c JOIN messages m ON c.message_id = m.id
            WHERE c.subject=? AND c.status='pending'""", (ТЕМА,)).fetchall()
выбор = random.sample(list(строки), min(СКОЛЬКО, len(строки)))

камп = {}
итог = Counter()
по_домену = {}
for р in выбор:
    cid = int(р["campaign_id"] or 0)
    if cid not in камп:
        камп[cid] = store.get_campaign(cid)
    rec = store.get_recipient(int(р["recipient_id"]))
    msg = store.get_message(int(р["mid"])) if hasattr(store, "get_message") else None
    try:
        mid = snd.pick_mailbox(rec, камп[cid], manual=True, message=msg)
    except Exception as ex:                                     # noqa: BLE001
        mid = "ОШИБКА: " + str(ex)[:60]
    ключ = str(mid or "НЕКОМУ СЛАТЬ (None)")
    итог[ключ] += 1
    дом = str(getattr(rec, "domain", "") or "?").lower()
    по_домену.setdefault(дом, Counter())[ключ] += 1

print("--- по доменам получателя (топ-6) ---")
for дом, c in sorted(по_домену.items(), key=lambda x: -sum(x[1].values()))[:6]:
    вид = ", ".join("%s:%d" % (k.split("@")[0][:16], v)
                    for k, v in c.most_common(4))
    print("   %-18s всего %4d | %s" % (дом, sum(c.values()), вид))
print("")
print("=" * 74)
print("=== КАКОЙ ЯЩИК ВЫБЕРЕТСЯ (проба на %d карточках) ===" % len(выбор))
for к, в in итог.most_common(25):
    print("   %-40s %5d" % (к[:40], в))
print("разных ящиков: %d; писем без ящика: %d"
      % (len([k for k in итог if "@" in k]), итог.get("НЕКОМУ СЛАТЬ (None)", 0)))
