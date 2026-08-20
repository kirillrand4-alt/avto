# -*- coding: utf-8 -*-
"""Проверка на боевом: фразы знакомства согласуются, письмо Анастасии чинится."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import ZNAKOMSTVO                          # noqa: E402
from sender.gender_agree import _FEM, agree                      # noqa: E402

без = [z for z in ZNAKOMSTVO if z.split()[0].lower().strip(",") not in _FEM]
print("фразы знакомства без женской формы:", без or "нет")
проба = ("Меня зовут Анастасия, представляю компанию «Руспром Meyer». "
         "Разбирался, чем занимается «Эйва-Про». Прошёлся по вашему сайту. "
         "Знакомился с профилем. Буду благодарен за контакт коллеги.")
print("\nбыло: ", проба)
print("стало:", agree(проба, "f"))
