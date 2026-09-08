# -*- coding: utf-8 -*-
"""Честный вызов pick_mailbox: с живым индексом обзвона и с письмом.

Прошлая проба врала дважды. Индекс обзвона не поднялся (модуль зовётся
company_card, не company_ields), и гейт направлений был выключен - поэтому
mail.ru-письма «выбрали» компрессорный ящик. И message не передавался, так
что правило «ящик обязан совпадать с направлением ПИСЬМА» не работало.

Ротацию эта проба всё равно не покажет: указатель круга двигает реальная
отправка (_last_sent_mailbox), а мы не шлём. Она отвечает на другое, более
важное: НАЙДЁТСЯ ли вообще пригодный ящик и какого он направления.
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
СКОЛЬКО = 250
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

карты = None
try:
    from sender.company_card import CompanyCards
    карты = CompanyCards(
        index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
        enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
    print("индекс обзвона: активен=%s" % getattr(карты, "active", "?"))
except Exception as ex:                                         # noqa: BLE001
    print("ИНДЕКС ОБЗВОНА НЕ ПОДНЯЛСЯ: %s" % str(ex)[:110])

print("перелив между пулами (provider_split.overflow): %s"
      % cfg.get("provider_split.overflow", False))

snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=True,
             cards=карты)


class _Письмо(object):
    """Ровно то, что нужно гейту: id, по нему он найдёт карточку и направление."""

    def __init__(self, i):
        self.id = i


with store._lock:
    строки = store._conn.execute(
        """SELECT c.recipient_id, c.campaign_id, c.inn, m.id AS mid
             FROM confirm_reviews c JOIN messages m ON c.message_id = m.id
            WHERE c.subject=? AND c.status='pending'""", (ТЕМА,)).fetchall()
выбор = random.sample(list(строки), min(СКОЛЬКО, len(строки)))

# сколько наших ИНН вообще известны базе обзвона: гейт блокирует компанию,
# которой в ней нет, СО ВСЕХ ящиков
в_obzvone = Counter()
if карты is not None and getattr(карты, "active", False):
    получ = getattr(карты, "divisions", None)
    for р in выбор:
        try:
            d = получ(str(р["inn"] or "")) if callable(получ) else None
        except Exception:                                       # noqa: BLE001
            d = None
        в_obzvone["есть в базе обзвона" if d else "НЕТ в базе обзвона"] += 1

камп = {}
итог = Counter()
напр = Counter()
ящик_напр = {}
for м in (cfg.get("mailboxes", None) or []):
    ящик_напр[str((м or {}).get("id") or "")] = str((м or {}).get("division") or "?")
for р in выбор:
    cid = int(р["campaign_id"] or 0)
    if cid not in камп:
        камп[cid] = store.get_campaign(cid)
    rec = store.get_recipient(int(р["recipient_id"]))
    try:
        mid = snd.pick_mailbox(rec, камп[cid], manual=True,
                               message=_Письмо(int(р["mid"])))
    except Exception as ex:                                     # noqa: BLE001
        mid = "ОШИБКА: " + str(ex)[:60]
    ключ = str(mid or "НЕКОМУ СЛАТЬ (None)")
    итог[ключ] += 1
    напр[ящик_напр.get(str(mid), "нет ящика")] += 1

print("")
print("=" * 74)
print("=== ЧЕСТНЫЙ ПОДБОР ЯЩИКА (%d карточек) ===" % len(выбор))
for к, в in в_obzvone.most_common():
    print("   %-30s %5d" % (к, в))
print("")
for к, в in итог.most_common(12):
    print("   %-42s %5d" % (к[:42], в))
print("")
print("направление выбранного ящика:")
for к, в in напр.most_common():
    print("   %-16s %5d" % (к, в))
print("писем без ящика: %d" % итог.get("НЕКОМУ СЛАТЬ (None)", 0))
