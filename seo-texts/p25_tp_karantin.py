# -*- coding: utf-8 -*-
"""Убрать в карантин 1 599 карточек, приписанных не тем предприятиям. Не удалить.

ЧТО СЛУЧИЛОСЬ. Прогон по компаниям ставил в форму `company_id`, а он у площадки не
фильтрует ничего. Все восемь предприятий получили ОДНУ И ТУ ЖЕ общую выдачу — по
2 820 «своих» тендеров у каждого, — и 1 599 скачанных карточек легли в поток как
карточки РТ-Инжиниринга, Апатита, Карабашмеди и остальных пяти.

Карточки настоящие. Неверна ПРИНАДЛЕЖНОСТЬ, и ровно ей мы бы потом закрывали
предприятия. Это та же подмена, что «номер рядом с фамилией — значит его»: данные
подлинные, а связь придумана прибором.

ПОЭТОМУ КАРАНТИН, А НЕ УДАЛЕНИЕ. Поток переименовывается в `-bred`, чтобы очередь
считала восемь предприятий непройденными и спросила их заново уже рабочим фильтром.
Сами тексты карточек остаются на диске: они добыты, и когда номера тендеров будут
сшиты с ИНН по-честному, их можно будет разобрать без повторного скачивания.
"""
import json
import os
import shutil

POTOK = r'C:\sender\_ops\p25-tp-po-kompaniyam.jsonl'
KARANTIN = r'C:\sender\_ops\p25-tp-po-kompaniyam-bred.jsonl'

if not os.path.exists(POTOK):
    print('ИТОГ ' + json.dumps({'поток': 'нет — карантинить нечего'}, ensure_ascii=False))
    raise SystemExit

strok = kart = 0
predpr = []
for ln in open(POTOK, encoding='utf-8'):
    try:
        z = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    strok += 1
    kart += z.get('kartochek', 0)
    predpr.append(z.get('tp_name') or z.get('predpriyatie', ''))

# Если карантин уже есть — дописываем, а не затираем: чужую работу не теряем.
if os.path.exists(KARANTIN):
    with open(KARANTIN, 'a', encoding='utf-8') as f:
        f.write(open(POTOK, encoding='utf-8').read())
    os.remove(POTOK)
else:
    shutil.move(POTOK, KARANTIN)

print('ИТОГ ' + json.dumps({
    'строк в карантин': strok, 'карточек в карантине': kart,
    'предприятий вернулось в очередь': predpr,
    'поток очищен': not os.path.exists(POTOK),
    'карантин': os.path.basename(KARANTIN)}, ensure_ascii=False))
