# -*- coding: utf-8 -*-
"""Посмотреть по IMAP, в какой папке легло письмо-маяк, и записать вердикт.

Это единственный способ узнать папку: по SMTP она не сообщается никогда.
Ищем по теме - почтовики переписывают Message-ID при пересылке, а тема
остаётся. Смотрим «Входящие» и найденную папку спама.

Вердикт кладём событием mayak в журнал: домен отправителя, провайдер маяка,
папка. Дальше по этим событиям видно, у кого мы в спаме и с какого дня.

Запуск: mayaki_proverit.py [--tema "..."]
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.dtos import EventIn                                     # noqa: E402
from sender.mayaki import СОБЫТИЕ, gde_pismo, spisok                # noqa: E402
from sender.store import Store                                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

тема = None
if "--tema" in sys.argv:
    тема = sys.argv[sys.argv.index("--tema") + 1]
тема = тема or store.get_setting("mayaki_poslednyaya_tema", None)
когда_слали = store.get_setting("mayaki_poslednyaya_otpravka", None)
if not тема:
    print("не знаю, что искать: маякам ещё не слали (mayaki_otpravit.py)")
    raise SystemExit(0)
print(f"ищем письмо: {тема}")
print(f"отправлено:  {когда_слали}")

маяки = spisok(cfg)
if not маяки:
    print("список маяков пуст")
    raise SystemExit(0)

сейчас = datetime.now(timezone.utc)
итог = {}
for м in маяки:
    ответ = gde_pismo(м, тема)
    итог[м.email] = ответ["папка"]
    print(f"\n{м.email} ({м.provayder}): {ответ['папка'].upper()}")
    if ответ.get("папка_имя"):
        print(f"   папка: {ответ['папка_имя']}")
    if ответ.get("искали"):
        print(f"   смотрели: {', '.join(ответ['искали'])}")
    if ответ.get("почему"):
        print(f"   {ответ['почему']}")
    if ответ["папка"] in ("входящие", "спам"):
        try:
            store.append_event(EventIn(
                dedup_key=f"mayak|{м.email}|{тема[:60]}",
                event_type=СОБЫТИЕ,
                message_id=None, recipient_id=None,
                campaign_id=int(store.get_setting("mayaki_kampaniya", 0) or 0) or None,
                mailbox_id=None, provider=м.provayder,
                event_ts=сейчас,
                detail={"папка": ответ["папка"], "тема": тема,
                        "маяк": м.email, "провайдер": м.provayder},
            ))
        except Exception as ex:                                    # noqa: BLE001
            print(f"   событие не записалось: {str(ex)[:80]}")

print("\nитог:", json.dumps(итог, ensure_ascii=False))
в_спаме = [а for а, п in итог.items() if п == "спам"]
if в_спаме:
    print(f"В СПАМЕ: {', '.join(в_спаме)}")
