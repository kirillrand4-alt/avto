# -*- coding: utf-8 -*-
"""Проверка просьбы о контакте коллеги в каноне августа: без имени — ставится,
с именем — нет, повторно — не дублируется."""
import importlib.util
import sys
sys.path.insert(0, r"C:\sender")
import sender  # noqa: E402
сп = importlib.util.spec_from_file_location("sender.ai_letter", r"C:\sender\server\ops\ai_letter_avgust.py")
A = importlib.util.module_from_spec(сп)
sys.modules["sender.ai_letter"] = A
сп.loader.exec_module(A)
без = "Добрый день!\n\nСмотрел профиль «Икс».\n\nПодскажите, актуален ли вопрос?\n\nС уважением,"
с = "Добрый день, Ирина!\n\nСмотрел профиль «Икс».\n\nПодскажите, актуален ли вопрос?\n\nС уважением,"
r1 = A.zashit_kontsovku(без, "kc")
print(r1)
print("--- без имени: просьба", A.PROSBA_KONTAKTA in r1)
r2 = A.zashit_kontsovku(с, "kc")
print("--- с именем: просьба", A.PROSBA_KONTAKTA in r2)
print("--- повтор не дублирует:", A.zashit_kontsovku(r1, "kc").count(A.PROSBA_KONTAKTA) == 1)
print("--- Meyer не трогаем:", A.PROSBA_KONTAKTA not in A.zashit_kontsovku(без, "meyer"))
