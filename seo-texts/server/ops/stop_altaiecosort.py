# -*- coding: utf-8 -*-
"""«Алтай Эко Сорт» — в стоп-лист (владелец 21.10: «проверить алтайэкосорт в
отправках холодных писем, посмотри и убери, если он где-то встречается»).
ИНН 2222857382, адрес osort@mail.ru, домен сайта altaiecosort.com. Штатный
Suppression (add_inn/add_email/add_domain) — заслон очереди и отправки."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
s = Suppression(Store(cfg.get("service.db_path", r"C:\sender\sender.db")))
П = "владелец 21.10: Алтай Эко Сорт — холодные не писать"
print("ИНН 2222857382:", s.add_inn("2222857382", П, source="owner"))
print("osort@mail.ru:", s.add_email("osort@mail.ru", П, source="owner"))
print("altaiecosort.com:", s.add_domain("altaiecosort.com", П, source="owner"))
