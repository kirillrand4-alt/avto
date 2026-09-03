#!/usr/bin/env python3
# coding: utf-8
"""Вариант статей без тега script: обработчик кнопки переезжает в атрибут
onclick. Нужен, если редактор Битрикса вырезает script при сохранении
(на ac-kompressor.ru он уже ломал блок inline/230/1f147p до «<sc ript»).

Запуск: python3 bez_skripta.py   - берёт всё из statyi/, кладёт в statyi-bez-skripta/
"""

import io
import os
import re
import glob

ONCLICK = ("var b=document.querySelector('.footer-btn');"
           "var s=b?b.previousElementSibling:null;"
           "if(s?s.hasAttribute('data-b24-loaded'):0){b.click();return false}")

korn = os.path.dirname(os.path.abspath(__file__))
cel = os.path.join(korn, "statyi-bez-skripta")
os.makedirs(cel, exist_ok=True)
for put in sorted(glob.glob(os.path.join(korn, "statyi", "*.html"))):
    s = io.open(put, encoding="utf-8", newline="").read()
    s = re.sub(r'\s*<!--[^>]*?-->\s*<script>.*?</script>\s*$', '\r\n', s, flags=re.S)
    n = s.count('class="ac-kp-trigger"')
    s = s.replace('class="ac-kp-trigger"', f'class="ac-kp-trigger" onclick="{ONCLICK}"')
    assert '<script' not in s and s.count('onclick=') == n, put
    io.open(os.path.join(cel, os.path.basename(put)), "w", encoding="utf-8", newline="").write(s)
    print(f'{os.path.basename(put):40} кнопок: {n}')
