# -*- coding: utf-8 -*-
"""Чистка мусора из phone_contacts (владелец: «прям не очень качество»):
регэксп цеплял ОГРН/ИНН/счета и заглушки. Валидатор:
- нормализация к 10 цифрам после кода страны; ровно 10, код не 000/0xx;
- сырой текст должен быть ОТФОРМАТИРОВАН как телефон (+7 / скобки / дефисы),
  голые длинные цифрострoки - мусор;
- заглушки (000-00-00, 999-99-99, все цифры одинаковые/подряд) - мусор.
Удаляем невалидные, показываем счёт до/после."""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

e = EDB.EnrichDB().cx


def валиден(сырой):
    s = str(сырой or '').strip()
    ц = re.sub(r'\D', '', s)
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    if len(ц) != 10:
        return False
    if ц[0] == '0' or ц[:3] == '000':
        return False
    if len(set(ц)) <= 2:                       # 0000000000, 9999999999, 7777...
        return False
    if ц[3:] in ('0000000', '9999999') or ц[3:5] == ц[5:7] == ц[7:9] == '00':
        return False
    хвост = ц[3:]
    if len(set(хвост)) == 1:
        return False
    # форматирование: телефон на странице пишут с +7/8 и разделителями
    if not re.match(r'^\+?[78][\s(\-]', s):
        return False
    if not re.search(r'[\s()\-]', s[2:]):
        return False
    return True


до = e.execute('SELECT COUNT(*) FROM phone_contacts').fetchone()[0]
удалить = []
for rowid, phone in e.execute('SELECT rowid, phone FROM phone_contacts'):
    if not валиден(phone):
        удалить.append(rowid)
for rid in удалить:
    e.execute('DELETE FROM phone_contacts WHERE rowid=?', (rid,))
e.commit()
после = e.execute('SELECT COUNT(*) FROM phone_contacts').fetchone()[0]
print(json.dumps({'до': до, 'удалено': len(удалить), 'после': после},
                 ensure_ascii=False))
