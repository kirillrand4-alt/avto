# -*- coding: utf-8 -*-
"""Разбирается ли шаблон карточки после правки. Сломанный шаблон роняет всю страницу.

Правка в чужом рабочем файле проверяется не тем, что она записалась, а тем, что панель
после неё жива. Ошибка в фигурных скобках Jinja не молчит и не портит один значок — она
роняет карточку целиком, и продавец видит пятисотую вместо предприятия.

Прибор делает три вещи: разбирает шаблон разборщиком Jinja, отрисовывает блок людей на
подставных данных и проверяет, что в выводе появились и должность, и пометка привязки.
Подставных людей трое: с подтверждённой привязкой, со спорной и обычный — иначе проверка
мерила бы непустоту, а не различение.
"""
import io
import json
import re
import sys

SHABLON = r'C:\seostat\app\templates\centro_card.html'
t = io.open(SHABLON, encoding='utf-8').read()

itog = {}
try:
    import jinja2
except Exception as e:  # noqa: BLE001
    print('REC jinja2 не поставлена, разбор не сделан: %s\t1' % str(e)[:40])
    print('ИТОГ ' + json.dumps({'разобран': None}, ensure_ascii=False))
    sys.exit()

sreda = jinja2.Environment(autoescape=True)
try:
    sreda.parse(t)
    itog['шаблон разбирается'] = True
except Exception as e:  # noqa: BLE001
    itog['шаблон разбирается'] = False
    itog['ошибка'] = str(e)[:200]
    print('REC ШАБЛОН СЛОМАН\t1')
    print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
    sys.exit()

# Вырезаем ЦИКЛ по людям и рисуем его отдельно — он самодостаточен.
# Первая попытка резала от «{% if persons %}» до первого «{% endif %}» — а внутри
# блока своих «endif» полдюжины, и кусок обрывался на середине цикла. Проба падала не
# на шаблоне, а на себе самой.
m = re.search(r'\{%\s*for p in persons\s*%\}.*?\{%\s*endfor\s*%\}', t, re.S)
if not m:
    print('REC блок людей не найден\t1')
    print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
    sys.exit()

LYUDI = [
    {'person': 'Анисимов Сергей Александрович', 'position': 'главный инженер',
     'is_tech': 1, 'phone': '', 'email': '', 'tel_href': '', 'mail_href': '',
     'privyazka_somnitelna': None,
     'privyazka_proverena': 'ПОДТВЕРЖДЕНО: наше предприятие названо в строке человека'},
    {'person': 'Ахмадишин Фаиз Фаикович', 'position': 'директор',
     'is_tech': 0, 'phone': '', 'email': '', 'tel_href': '', 'mail_href': '',
     'privyazka_somnitelna': 'перепроверка: в строке источника назван Дом народного '
                             'творчества', 'privyazka_proverena': 'ОТВЯЗАТЬ'},
    {'person': 'Обычный Иван Иванович', 'position': 'снабжение',
     'is_tech': 0, 'phone': '79001234567', 'email': '', 'tel_href': 'tel:79001234567',
     'mail_href': '', 'privyazka_somnitelna': None, 'privyazka_proverena': None},
]
try:
    vyvod = sreda.from_string(m.group(0)).render(persons=LYUDI)
    itog['блок рисуется'] = True
except Exception as e:  # noqa: BLE001
    itog['блок рисуется'] = False
    itog['ошибка отрисовки'] = str(e)[:200]
    print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
    sys.exit()

itog['должность видна'] = 'главный инженер' in vyvod
itog['спорная привязка названа'] = 'Дом народного творчества' in vyvod
itog['подтверждённая помечена'] = 'привязка проверена по строке источника' in vyvod
itog['у обычного лишнего не дорисовано'] = (
    vyvod.count('привязка проверена по строке источника') == 1
    and vyvod.count('не подтверждена') == 1)

print('--- как это увидит продавец')
for s in re.sub(r'\n\s*\n', '\n', re.sub(r'<[^>]+>', ' ', vyvod)).split('\n'):
    if s.strip():
        print('   %s' % re.sub(r'\s+', ' ', s).strip()[:130])

for k, v in itog.items():
    print('REC %s\t%d' % (k, 1 if v else 0))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
