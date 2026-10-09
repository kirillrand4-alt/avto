# -*- coding: utf-8 -*-
r"""Чья разметка ролей точнее: серверный обогатитель (enrich_contacts.extract_roles) или наш обход (kc_kontakty)
(владелец 09.10: «точность данных тоже надо проверить: какой лучше подписывает роли»).

Вход — <набор>-sravnenie-ec.jsonl (kc_sravnenie_ec: на одних и тех же новых сайтах фаза A — серверный обогатитель,
фаза B — наш обход). Контакты, которые есть у обоих (почта или номер), роль EC переводится в нашу «Роль» (EC_РОЛЬ);
где роли разошлись — все такие контакты, где совпали — выборка (KC_SUDYA_SOVP, по умолчанию 15%) для контроля.
Судья — сильная модель (PROVIDER_MODEL, Sol) по фрагменту страницы вокруг контакта; варианты — вслепую («1»/«2» в
случайном порядке) и «ни один»; он же называет верную роль. Итог по контакту — строка в <набор>-sudya-roley.jsonl
(fsync, резюм по ключу); сводка — python kc_sudya_roley.py itog.
"""
import collections
import io
import json
import os
import random
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_kontakty as KK  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'meyer7t')
ВХОД = os.path.join(DIR, НАБОР + '-sravnenie-ec.jsonl')
НАША = os.environ.get('KC_SUDYA_FAZA', 'C')  # наша фаза сравнения (C — режим полного прогона)
ВЫХОД = os.path.join(DIR, НАБОР + '-sudya-roley.jsonl')
_лок = threading.Lock()
ПРОМПТ = (
    'Ты проверяешь разметку контактов с сайта компании «{имя}» (сайт {сайт}). Ниже фрагмент страницы вокруг контакта '
    '{контакт}. Две системы назначили контакту роль в компании. Реши по фрагменту, какая роль верна.\n'
    'Справочник ролей: {роли}.\n'
    'Роль «Общий номер / приёмная» — общий адрес/номер компании без конкретного отдела или человека. «Прочее» — '
    'отдел или человек вне остальных ролей. Если во фрагменте нет признаков роли — верна «Общий номер / приёмная».\n\n'
    'Фрагмент:\n«{фрагмент}»\n\nВариант 1: {в1}\nВариант 2: {в2}\n\n'
    'Ответь одним JSON: {{"верный": "1"|"2"|"оба"|"ни один", "роль": "<верная роль из справочника>", '
    '"почему": "<до 15 слов>"}}')


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def ц(x):
    return re.sub(r'\D', '', x or '')[-10:]


def пары():
    фазы = collections.defaultdict(dict)
    for s in io.open(ВХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
            фазы[з['inn']][з['фаза']] = з
        except (ValueError, KeyError):
            continue
    сл = random.Random(910)
    доля = float(os.environ.get('KC_SUDYA_SOVP', '0.15'))
    out = []
    for i, ф in фазы.items():
        if 'A' not in ф or НАША not in ф:
            continue
        a, b = ф['A']['r'] or {}, ф[НАША]['r'] or {}
        роли_a = {}
        for e in a.get('emails') or []:
            if isinstance(e, dict) and e.get('email'):
                роли_a['mail:' + e['email'].lower()] = e.get('role') or ''
        for x in a.get('phone_roles') or []:
            if isinstance(x, dict) and ц(x.get('phone')):
                роли_a[ц(x['phone'])] = x.get('role') or x.get('dept') or ''
        for н in b.get('номера') or []:
            кл = 'mail:' + н['почта'].lower() if н.get('почта') else ц(н.get('номер'))
            if кл not in роли_a:
                continue
            ra = KK.EC_РОЛЬ.get(роли_a[кл], ('Общий номер / приёмная' if роли_a[кл] in ('', 'общий') else 'Прочее', ''))[0]
            rb = н.get('роль') or 'Общий номер / приёмная'
            if ra == rb and сл.random() > доля:
                continue
            out.append({'ключ': i + '|' + кл, 'inn': i, 'имя': ф['A'].get('имя') or '', 'сайт': ф['A'].get('сайт') or '',
                        'контакт': кл.replace('mail:', ''), 'роль_EC_исх': роли_a[кл], 'A': ra, 'B': rb,
                        'B_фио': н.get('фио') or '', 'B_должность': н.get('должность') or '',
                        'фрагмент': (н.get('контекст') or '')[-900:], 'совпали': ra == rb})
    return out


def судить(x):
    сл = random.Random(x['ключ'])
    порядок = ['A', 'B'] if сл.random() < 0.5 else ['B', 'A']
    отв = KK.модель(ПРОМПТ.format(имя=x['имя'], сайт=x['сайт'], контакт=x['контакт'], роли=', '.join(KK.РОЛИ),
                                  фрагмент=x['фрагмент'], в1=x[порядок[0]], в2=x[порядок[1]]), False) or {}
    в = str(отв.get('верный') or '')
    x.update({'судья': в, 'судья_роль': отв.get('роль') or '', 'почему': (отв.get('почему') or '')[:120],
              'прав_A': в == 'оба' or (в in ('1', '2') and порядок[int(в) - 1] == 'A') or (отв.get('роль') == x['A']),
              'прав_B': в == 'оба' or (в in ('1', '2') and порядок[int(в) - 1] == 'B') or (отв.get('роль') == x['B']),
              'ответ_есть': bool(в)})
    записать(x)


def итог():
    рез = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
            рез[з['ключ']] = з
        except (ValueError, KeyError):
            continue
    с = collections.Counter()
    прим = []
    for з in рез.values():
        if not з.get('ответ_есть'):
            с['без ответа судьи'] += 1
            continue
        вид = 'совпали' if з['совпали'] else 'разошлись'
        с[вид] += 1
        с[вид + ': прав EC'] += з['прав_A']
        с[вид + ': прав наш'] += з['прав_B']
        if not з['совпали'] and len(прим) < 14:
            прим.append('%s | EC: %s (%s) | наш: %s | судья: %s — %s' % (з['контакт'], з['A'], з['роль_EC_исх'], з['B'],
                                                                       з['судья_роль'], з['почему']))
    return {'контактов': len(рез), 'счёт': dict(с), 'примеры расхождений': прим}


def main():
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                сделано.add(json.loads(s)['ключ'])
            except (ValueError, KeyError):
                pass
    очередь = [x for x in пары() if x['ключ'] not in сделано]
    print('контактов к суду', len(очередь), flush=True)
    with ThreadPoolExecutor(int(os.environ.get('KC_SUDYA_POTOKOV', '8'))) as ex:
        list(ex.map(судить, очередь))
    print('===ИТОГ===')
    print(json.dumps(итог(), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'itog':
        print('===ИТОГ===')
        print(json.dumps(итог(), ensure_ascii=False, indent=1))
    else:
        main()
