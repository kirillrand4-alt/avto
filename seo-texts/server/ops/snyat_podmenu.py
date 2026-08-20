# -*- coding: utf-8 -*-
"""Снять письма, построенные на фактах чужой компании.

Отбор двухступенчатый: бесплатный фильтр по имени (chey_sayt_prikleen.py)
дал 43 кандидата, опус из них подтвердил три. Хайку на этой задаче врала —
называла подменой формальный ОКВЭД.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ПОДМЕНЫ = {
    3154: "карточка — чай и кофе, сайт и почта — молочно-мясная ферма "
          "с птицефабрикой: письмо построено на чужих фактах",
    3269: "карточка — какао и шоколад, сайт — производство "
          "металлообрабатывающих станков и роботов",
    3407: "карточка — обработка металлов, сайт — строительная компания, "
          "ремонт зданий и сооружений",
}
КАТИТЬ = "--katit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

for rid, причина in ПОДМЕНЫ.items():
    row = store.confirm_get(rid) or {}
    print(f"#{rid} {row.get('company_name')} | статус {row.get('status')}")
    if not КАТИТЬ:
        continue
    # РЕШЕНИЕ ПО КАРТОЧКЕ НЕИЗМЕННО. confirm_decide не перерешивает уже
    # одобренное (аудит-след) и молча возвращает False. Значит письмо надо
    # останавливать там, где его берёт автоотправка: в самом messages.
    # claim_approved_due выбирает только status='scheduled'.
    mid = row.get("message_id")
    if not mid:
        print("   письма нет — останавливать нечего")
        continue
    try:
        store.mark_skipped(int(mid), "подмена сайта: " + причина)
        стало = store.confirm_get(rid) or {}
        print(f"   письмо #{mid} снято с отправки; "
              f"состояние письма: {стало.get('message_status')}")
    except Exception as ex:                                      # noqa: BLE001
        print(f"   не снялось: {str(ex)[:110]}")
if not КАТИТЬ:
    print("\nсухой прогон. Катить — --katit")
