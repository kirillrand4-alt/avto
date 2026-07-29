# -*- coding: utf-8 -*-
"""Перепроверка ролей провайдером ВНЕ сервера + выборочная сверка вручную.

Раннер один и занят агентами, а этот разбор к серверу не привязан: текст
должности уже выгружен, фетчить нечего. Работа идёт локально и параллельно.

Владелец: «только с выборочной перепроверкой» — поэтому вердикты модели НЕ
применяются вслепую. Скрипт печатает случайную выборку её решений вместе с
исходной должностью, чтобы можно было сверить глазами до записи в базу.
"""
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

КАНОН = ('гл.инженер', 'гл.энергетик', 'гл.механик', 'гл.технолог',
         'гл.конструктор', 'техдиректор', 'нач.производства', 'нач.цеха',
         'АСУ/КИПиА', 'снабжение/закупки', 'продажи', 'директор',
         'бухгалтерия', 'кадры', 'приёмная', 'общий')
ТЕХ = КАНОН[:9]
ПАЧКА = 25
ПОТОКОВ = 6


def провайдер(промпт, максимум=3000):
    key = os.environ.get('PROVIDER_API_KEY', '')
    base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    тело = json.dumps({'model': 'claude-fable-5', 'max_tokens': максимум,
                       'stream': True,
                       'messages': [{'role': 'user', 'content': промпт}]},
                      ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        base + '/v1/messages', data=тело, method='POST',
        headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                 'content-type': 'application/json',
                 'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0'})
    куски = []
    with urllib.request.urlopen(req, timeout=300) as r:
        for сырая in r:
            стр = сырая.decode('utf-8', 'replace').strip()
            if not стр.startswith('data:'):
                continue
            try:
                ev = json.loads(стр[5:].strip())
            except Exception:  # noqa: BLE001
                continue
            if ev.get('type') == 'content_block_delta':
                куски.append((ev.get('delta') or {}).get('text', ''))
    return ''.join(куски)


def разобрать(пачка):
    строки = '\n'.join(
        f'{i}. должность: «{x["post"]}» | сейчас размечена как: {x["role"]}'
        for i, x in enumerate(пачка))
    промпт = (
        'Ниже должности сотрудников промышленных предприятий и роль, которой '
        'их разметил наш код. Проверь КАЖДУЮ и верни правильную роль строго из '
        'списка: ' + ', '.join(КАНОН) + '.\n\n'
        'ПРАВИЛА, они важнее интуиции:\n'
        '— «заместитель главного инженера» это НЕ «гл.инженер»: заместитель '
        'решения не принимает, ему роль «общий»;\n'
        '— «инженер по снабжению», «инженер отдела МТС» — это снабжение, а не '
        'инженер;\n'
        '— «инженер технического отдела», «ведущий инженер» без слова «главный» '
        '— рядовой специалист, роль «общий»;\n'
        '— «начальник отдела сбыта» это продажи, даже если в названии есть '
        'слово «производство»;\n'
        '— «главный конструктор» — это гл.конструктор;\n'
        '— если должность обрезана и смысл не восстановить, ставь «общий».\n\n'
        'Верни СТРОГО JSON без markdown: {"r":[{"i":номер,"role":"роль",'
        '"why":"коротко почему, если роль меняется"}]}\n\n' + строки)
    try:
        ответ = провайдер(промпт)
    except Exception as ex:  # noqa: BLE001
        return []
    m = re.search(r'\{.*\}', ответ or '', re.S)
    if not m:
        return []
    try:
        return (json.loads(m.group(0)).get('r') or [])
    except Exception:  # noqa: BLE001
        return []


def main():
    d = json.load(open('roles_dump.json', encoding='utf-8'))
    люди = d['люди']
    пачки = [люди[i:i + ПАЧКА] for i in range(0, len(люди), ПАЧКА)]
    итог = []
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        for пачка, ответ in zip(пачки, пул.map(разобрать, пачки)):
            для = {int(x.get('i', -1)): x for x in ответ if isinstance(x, dict)}
            for i, ч in enumerate(пачка):
                r = для.get(i)
                if not r:
                    continue
                нов = (r.get('role') or '').strip()
                if нов in КАНОН and нов != ч['role']:
                    итог.append({**ч, 'новая': нов, 'почему': r.get('why', '')})
    json.dump(итог, open('roles_verdicts.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    было_тех = sum(1 for x in люди if x['role'] in ТЕХ)
    стало_тех = было_тех - sum(1 for x in итог if x['role'] in ТЕХ
                               and x['новая'] not in ТЕХ) \
        + sum(1 for x in итог if x['role'] not in ТЕХ and x['новая'] in ТЕХ)
    print(f'людей: {len(люди)}, модель предлагает изменить: {len(итог)}')
    print(f'технических было {было_тех}, станет {стало_тех}')
    print('\n--- ВЫБОРОЧНАЯ ПЕРЕПРОВЕРКА: каждое 3-е решение, сверять глазами ---')
    for x in итог[::3][:18]:
        print(f'  «{x["post"][:58]}»\n      {x["role"]} -> {x["новая"]}   {x.get("почему","")[:70]}')


if __name__ == '__main__':
    main()
