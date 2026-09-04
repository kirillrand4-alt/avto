# -*- coding: utf-8 -*-
"""Только чтение: как это письмо будет выглядеть у адресата."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.store import Store                # noqa: E402
from sender.suppression import Suppression    # noqa: E402
from sender.company_card import CompanyCards  # noqa: E402
import sender.sender as S                     # noqa: E402
import sender.gates as G                      # noqa: E402
import sender.gender_agree as GA              # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
карт = CompanyCards(index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store), cards=карт)
камп = store.get_campaign(13)
RM = S.RenderedMessage
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

р = c.execute("SELECT email, subject, body FROM confirm_reviews WHERE campaign_id=13"
              " AND body LIKE '%Милл фауз%'").fetchone()
if not р:
    р = c.execute("SELECT email, subject, body FROM confirm_reviews"
                  " WHERE campaign_id=13 AND body LIKE '%благодарен%'"
                  " LIMIT 1").fetchone()
print("письмо: %s | %s" % (р["email"], р["subject"]))

for ящик, кто in (("a.tyunin@sort-systems.ru", "МУЖСКОЙ ящик"),
                  ("i.kuznetsova@sort-systems.ru", "ЖЕНСКИЙ ящик")):
    итог = snd._apply_signature(RM(subject=р["subject"], body=р["body"]), ящик, камп)
    т = итог.body
    print("\n========== %s: %s ==========" % (кто, ящик))
    print(т)
    print("  ---- проверки ----")
    print("  метка осталась: %s" % ("ДА, ПЛОХО" if "ИМЯ_ОТПРАВИТЕЛЯ" in т else "нет"))
    for сл in ("благодарен", "благодарна", "Готов ", "Готова "):
        if сл.strip() in т:
            print("  найдено слово: «%s»" % сл.strip())

print("\n=== ПРОВЕРКА СЛОВ НА РОД ПО ВСЕЙ ПАРТИИ 13 ===")
слова = ("благодарен", "признателен", "готов", "рад", "уверен", "должен",
         "смог", "хотел", "решил", "написал", "связался", "был")
for сл in слова:
    k = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13"
                  " AND LOWER(body) LIKE ?", ("%" + сл + "%",)).fetchone()[0]
    if k:
        пробa = GA.agree("Я " + сл + ".", "f")
        print("  «%-12s» в %3d письмах | женский род движка: «%s»"
              % (сл, k, пробa.strip()))
