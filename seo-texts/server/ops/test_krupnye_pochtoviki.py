# -*- coding: utf-8 -*-
"""Как крупные почтовики сейчас отвечают нашей пробе на ЗАВЕДОМО несуществующий адрес (если «есть» — значит
почтовик перестал говорить нам правду: принимает всё от нашего IP). По одному разговору на домен. В базы НЕ пишет."""
import random, string, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proba_tochnaya as P
for дом in ("mail.ru", "bk.ru", "yandex.ru", "rambler.ru", "gmail.com"):
    а = "zz" + "".join(random.choice(string.ascii_lowercase) for _ in range(16)) + "@" + дом
    try: print(дом, P._разговор(P.mx_doh(дом)[0], а, P.ОТ))
    except Exception as ex: print(дом, "сбой", str(ex)[:120])
