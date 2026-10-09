# -*- coding: utf-8 -*-
r"""Контроль полного прогона Meyer (набор meyer7) для проверок каждые 20 минут (владелец 09.10: «каждые 20 минут
проверяй ход работ и высказывай теории, что может пойти не так»). Только чтение, -> ===ИТОГ=== JSON:
поиск (строки, ошибки за последние 500, доменов), волна и шаги конвейера, трассировки в логах шагов за последний час,
обход (компаний, сайт открылся, с номером, с почтой, роли у номеров, контакты обогателя, исключённые скрытые почты,
брошенные сторожем), список (компаний, с сайтом, ждут ОКВЭД), агенты, баланс xmlriver."""
import collections
import glob
import io
import json
import os
import re
import time
import urllib.request

DIR = r'C:\sender\server'
Н = os.environ.get('KC_NABOR', 'meyer7')
o = {'время': time.strftime('%Y-%m-%d %H:%M:%S')}


def jl(х, хвост=None):
    п = os.path.join(DIR, Н + х)
    if not os.path.exists(п):
        return []
    строки = io.open(п, encoding='utf-8', errors='replace').readlines()
    if хвост:
        строки = строки[-хвост:]
    out = []
    for s in строки:
        try:
            out.append(json.loads(s))
        except ValueError:
            pass
    return out


serp = jl('-serp.jsonl')
посл = serp[-500:]
o['поиск'] = {'строк': len(serp), 'ошибок_в_последних_500': sum(1 for z in посл if z.get('итог') == 'ошибка'),
              'виды_ошибок': dict(collections.Counter((z.get('ошибка') or '')[:30] for z in посл if z.get('итог') == 'ошибка').most_common(3)),
              'пустых_в_последних_500': sum(1 for z in посл if not z.get('доки'))}
лл = sorted(glob.glob(os.path.join(DIR, Н + '_poisk_*.log')), key=os.path.getmtime)
if лл:
    o['поиск']['лог'] = io.open(лл[-1], encoding='utf-8', errors='replace').read()[-260:]
п = os.path.join(DIR, Н + '-konveyer.json')
if os.path.exists(п):
    к = json.load(io.open(п, encoding='utf-8'))
    o['конвейер'] = {'волна': к.get('волна'), 'фон': к.get('фон'), 'следующая': к.get('следующая_волна'), 'стоп': к.get('стоп', ''),
                     'шаги': {ш: '%s→%s код %s%s' % (v.get('старт', '')[-5:], v.get('конец', '')[-5:], v.get('код', ''),
                                                     ' пропуск' if v.get('пропуск') else '') for ш, v in к.get('шаги', {}).items()}}
трасс = {}
for л in glob.glob(os.path.join(DIR, 'konveyer_%s_*.log' % Н)):
    if time.time() - os.path.getmtime(л) < 3600:
        т = io.open(л, encoding='utf-8', errors='replace').read()
        n = т.count('Traceback')
        if n:
            трасс[os.path.basename(л)] = {'трассировок': n, 'последняя': т[т.rfind('Traceback'):][:400]}
o['трассировки_за_час'] = трасс
сп = {}
пс = os.path.join(DIR, Н + '-spisok.json')
if os.path.exists(пс):
    try:
        сп = json.load(io.open(пс, encoding='utf-8')).get('компании', {})
    except ValueError:
        сп = {}
o['список'] = {'компаний': len(сп), 'с сайтом': sum(1 for к in сп.values() if к.get('сайт')),
               'по сегментам': dict(collections.Counter((к.get('сегм') or '?')[:25] for к in сп.values()).most_common(6))}
конт = {}
for з in jl('-kontakty.jsonl'):
    if з.get('inn'):
        конт[з['inn']] = з
ok = [з for з in конт.values() if з.get('итог') == 'ok']
с_сайтом = [з for з in ok if з.get('сайт')]
номера = [н for з in ok for н in з.get('номера', []) if н.get('номер')]
почты = [н for з in ok for н in з.get('номера', []) if н.get('почта')]
o['обход'] = {'компаний': len(конт), 'ok': len(ok), 'сбоев': len(конт) - len(ok),
              'сайт открылся, %': round(100 * sum(1 for з in с_сайтом if any(с == 'ok' for _, с in з.get('страницы', []))) / max(1, len(с_сайтом)), 1),
              'с номером, %': round(100 * sum(1 for з in ok if any(н.get('номер') for н in з.get('номера', []))) / max(1, len(ok)), 1),
              'с почтой, %': round(100 * sum(1 for з in ok if any(н.get('почта') for н in з.get('номера', []))) / max(1, len(ok)), 1),
              'номеров': len(номера), 'почт': len(почты),
              'роль есть у номеров, %': round(100 * sum(1 for н in номера if н.get('роль') or н.get('класс')) / max(1, len(номера)), 1),
              'ЛПР да': sum(1 for з in ok for н in з.get('номера', []) if н.get('лпр') == 'да'),
              'ФИО': sum(1 for з in ok for н in з.get('номера', []) if н.get('фио')),
              'контактов от обогатителя': sum(1 for з in ok for н in з.get('номера', []) if 'enrich' in str(н.get('откуда') or '')),
              'обогатитель: сбой/ошибка': dict(collections.Counter(((з.get('ec') or {}).get('ошибка') or (з.get('ec') or {}).get('сбой') or 'ok')[:25] for з in ok if з.get('ec')).most_common(4)),
              'почт исключено как скрытые': sum(len(з.get('почты_исключены') or []) for з in ok),
              'видимость «скрыта»': sum(1 for з in ok for н in з.get('номера', []) if н.get('видимость'))}
лк = sorted(glob.glob(os.path.join(DIR, 'konveyer_%s_kc_kontakty_*.log' % Н)), key=os.path.getmtime)
if лк:
    т = io.open(лк[-1], encoding='utf-8', errors='replace').read()
    o['обход']['лог'] = т[-300:]
    o['обход']['брошено сторожем'] = т.count('брошены')
o['агенты'] = {'записей': len(jl('-glubokiy.jsonl')), 'перепроверка': len(jl('-glubokiy2.jsonl'))}
try:
    оп = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    o['xmlriver'] = float(оп.open('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (
        os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')), timeout=30).read(100))
except Exception as e:  # noqa: BLE001
    o['xmlriver'] = repr(e)[:80]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:7000])
