# -*- coding: utf-8 -*-
r"""Проба новой карточки лида БЕЗ рестарта: собираем страницу прямо здесь.

Панель подхватит модули только при старте, а проверить надо сейчас: правильно
ли склеились телефоны, встали ли источники, не осталось ли нашей подписи в
ответе, процитированном без знаков «>».
"""
import importlib
import json
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
LS = importlib.import_module('lid_ssylka')
LST = importlib.import_module('lid_stranica')
importlib.reload(LS)
importlib.reload(LST)

ИНН = '7719414324'
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
s.row_factory = sqlite3.Row
лид = dict(s.execute('select * from leads where inn=? order by id desc limit 1',
                     (ИНН,)).fetchone())
s.close()
л = {'company_name': лид.get('company_name'), 'inn': лид.get('inn'),
     'email': лид.get('email'), 'phone': лид.get('phone')}

ответ = (
    'Добрый день! Спасибо за предложение, сейчас не актуально.\n'
    'Если появится потребность — напишу.\n\n'
    'С уважением,\n'
    'Анна Волкова, руководитель производства\n'
    '+7 985 991 29 58\n\n'
    'Добрый день!\n'
    'Смотрел производство — фабрика-кухня, готовые блюда.\n'
    'Если вопрос не к вам, буду благодарен за контакт коллеги.\n\n'
    'С уважением,\n'
    'Менеджер по продажам,\n'
    'Юрий Кузьмин\n'
    '«Руспром Мейер»\n'
    'ООО «Руспром», ИНН 2221239841\n')
нить = [
    {'direction': 'out', 'kind': 'sent', 'ts': '2026-08-20T06:04:00',
     'subject': 'Вопрос по контролю качества', 'body':
     'Добрый день!\nСмотрел производство…\n\nС уважением,\nМенеджер по продажам,\n'
     'Юрий Кузьмин\n«Руспром Мейер»\nООО «Руспром», ИНН 2221239841'},
    {'direction': 'in', 'kind': 'reply', 'ts': '2026-08-20T06:30:00',
     'subject': 'Re: Вопрос по контролю качества', 'body': ответ},
]
карта = LS.karta_kompanii(ИНН, л)
стр = LST.sobrat(л, нить, {'karta': карта},
                 (LS.bez_podpisi, LS.bez_adresov, LS.bez_citaty,
                  LS.bez_nashey_podpisi))

текст = re.sub(r'<[^>]+>', ' ', стр)
итог = {
    'знаков': len(стр),
    'НАШ_менеджер_на_странице': [x for x in ('Кузьмин', 'Цейзер', 'Ляпин')
                                 if x in стр],
    'наш_ИНН_на_странице': '2221239841' in стр,
    'подпись_клиента_цела': 'Анна Волкова' in стр,
    'телефонов_строк': стр.count('<td class="n">Телефон</td>'),
    'источники_видны': стр.count('class="src"'),
    'реквизитов': len(карта.get('rekvizity') or []),
    'полей_паспорта': len((карта.get('pasport') or {}).get('polya') or []),
    'телефоны': карта.get('telefony'),
    'почты': карта.get('pochty'),
}
print(json.dumps({'реквизиты': карта.get('rekvizity')},
                 ensure_ascii=False, indent=1)[:1800])
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2600])
