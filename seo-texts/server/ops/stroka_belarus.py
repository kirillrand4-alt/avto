# -*- coding: utf-8 -*-
"""Белорусским получателям — «работаю с такими предприятиями в Беларуси».

Владелец 12.10: «добавь в шаблон для белоруси что по таким предприятиям в
белоруси работаю». Шаблона у Meyer-писем нет — их пишет генератор по
карточке, поэтому строка идёт в карточку получателя (_recipient_block):
получатель из группы «Белорусь 1000» (или со страной Беларусь) получает
указание сказать это во второй строке представления. Гейт строку «Работаю
с…» дословно не проверяет — брака от вставки не будет.
"""
import importlib.util as _iu
import io
import os
import py_compile
import shutil
import sys
import time

sys.path.insert(0, r"C:\sender")
ПУТЬ = r"C:\sender\sender\ai_letter.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "ПОЛУЧАТЕЛЬ ИЗ БЕЛАРУСИ" in т:
    print("строка уже стоит")
    print("=== БЕЛАРУСЬ: УЖЕ БЫЛО ===")
    sys.exit(0)
ЯКОРЬ = """    _кратко = короткое_имя(rec.get('company_name'))
    ex = rec.get('extra') or {}
"""
ВСТАВКА = ЯКОРЬ + """    # ПОЛУЧАТЕЛЬ ИЗ БЕЛАРУСИ (владелец 12.10: «добавь, что по таким
    # предприятиям в Беларуси работаю»). Опознаём по группе партии
    # («Белорусь 1000») или по стране из книги паспортов.
    _гр = ex.get('gruppy') or []
    if (any('елорус' in str(г) or 'еларус' in str(г) for г in _гр)
            or 'еларус' in str(ex.get('strana') or '')):
        lines.append("ПОЛУЧАТЕЛЬ ИЗ БЕЛАРУСИ. Во второй строке представления "
                     "скажи, что работаешь с такими предприятиями в Беларуси: "
                     "«Работаю с <отраслью получателя> в Беларуси по вопросам "
                     "<тема>». Страну назови один раз, в этой строке.")
"""
if т.count(ЯКОРЬ) != 1:
    print("якорь не найден (%d)" % т.count(ЯКОРЬ))
    print("=== БЕЛАРУСЬ: НЕ ПРИМЕНЕНО ===")
    sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8").write(т.replace(ЯКОРЬ, ВСТАВКА))
try:
    py_compile.compile(ПУТЬ, doraise=True)
    сп = _iu.spec_from_file_location("al_by", ПУТЬ)
    м = _iu.module_from_spec(сп)
    sys.modules["al_by"] = м
    сп.loader.exec_module(м)
    база = {"company_name": "ОАО «Тест»", "okved": "10.61", "activity": "мука",
            "mode": "generic", "email": "a@b.by"}
    by = dict(база, extra={"gruppy": ["Белорусь 1000"]})
    ru = dict(база, extra={"gruppy": ["Россия 9000"]})
    п_by = м._recipient_block(0, by, "meyer")
    п_ru = м._recipient_block(0, ru, "meyer")
    print("проверка: белорус -> строка есть: %s" % ("ИЗ БЕЛАРУСИ" in п_by))
    print("проверка: россия  -> строки нет: %s" % ("ИЗ БЕЛАРУСИ" not in п_ru))
    assert "ИЗ БЕЛАРУСИ" in п_by and "ИЗ БЕЛАРУСИ" not in п_ru
    print("ПРИМЕНЕНО, бэкап %s" % os.path.basename(бэкап))
    print("=== БЕЛАРУСЬ: ПРИМЕНЕНО ===")
except Exception as e:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("ОТКАТ: %s" % e)
    print("=== БЕЛАРУСЬ: ОТКАТ ===")
