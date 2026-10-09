# -*- coding: utf-8 -*-
r"""Паспорт сайта: GPT-5.6 Luna против GPT-6 Luna на одних и тех же 20 компаниях пилота (владелец 09.10: «переведи
паспорт на луну 6, проверь на 20 компаниях»). Карточки собираются site_facts._razobrat_odnu — БЕЗ записи в enrich.db
(собранные паспорта не трогаем). Каждая строка каждого поля сверяется с текстом страниц (pasport_sverka): подтверждена
или нет. Новости (второй проход, Claude Haiku) — только в прогоне GPT-6 Luna, чтобы посчитать их вызовы и токены.
Выход (fsync): pilot-pasport-ab.jsonl -> дроп. Итог — JSON после ===ИТОГ===.
"""
import gzip
import io
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import gen_provider as GP  # noqa: E402
import pasport_sverka as PS  # noqa: E402
import site_facts as SF  # noqa: E402

ВЫХОД = os.path.join(DIR, 'pilot-pasport-ab.jsonl')
МОДЕЛИ = ('gpt-5.6-luna', 'gpt-6-luna')
haiku = {'вызовов': 0, 'вход': 0, 'выход': 0, 'кэш': 0}
_исх_call = GP.call


def _call(klient, msgs, model=None, **kw):
    msg = _исх_call(klient, msgs, model=model, **kw)
    if model and model.startswith('claude'):
        u = getattr(msg, 'usage', None)
        haiku['вызовов'] += 1
        haiku['вход'] += getattr(u, 'input_tokens', 0) or 0
        haiku['выход'] += getattr(u, 'output_tokens', 0) or 0
        haiku['кэш'] += (getattr(u, 'cache_read_input_tokens', 0) or 0) + (getattr(u, 'cache_creation_input_tokens', 0) or 0)
    return msg


GP.call = _call
подмены = []  # тихий уход на запасную модель внутри GP.call (молчащая Luna -> Haiku)
_исх_подм = GP._zapisat_podmenu


def _подм(bylo, stalo, prichina):
    подмены.append((bylo, stalo, prichina))
    _исх_подм(bylo, stalo, prichina)


GP._zapisat_podmenu = _подм


def выборка():
    сп = json.load(io.open(os.path.join(DIR, 'pilot-spisok.json'), encoding='utf-8'))['компании']
    конт = []
    for s in io.open(os.path.join(DIR, 'pilot-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        з = json.loads(s)
        if з.get('итог') == 'ok' and з['inn'] in сп and з['inn'].isdigit() and sum(1 for _, ст in з.get('страницы', []) if ст == 'ok') >= 3 \
                and os.path.exists(os.path.join(SF.KESH, з['inn'] + '.json.gz')):
            конт.append({'inn': з['inn'], 'name': сп[з['inn']]['имя'], 'site': з['сайт'], 'сегм': сп[з['inn']]['сегм']})
    # разные сегменты: по одной компании на сегмент по кругу
    по_сегм = {}
    for к in конт:
        по_сегм.setdefault(к['сегм'], []).append(к)
    выбор, i = [], 0
    while len(выбор) < 20 and any(по_сегм.values()):
        for с in sorted(по_сегм):
            if по_сегм[с] and len(выбор) < 20:
                выбор.append(по_сегм[с].pop(i % len(по_сегм[с])))
        i += 7
    return выбор


def сверка(inn, fakty):
    текст = PS._tekst(inn)
    рез = {}
    for ключ in PS.КЛЮЧИ:
        стр = [x for x in SF._stroki_polya(fakty, ключ) if str(x).strip()]
        рез[ключ] = (len(стр), sum(1 for x in стр if PS._podtverzhdena(str(x), текст)))
    return рез


def main():
    выбор = выборка()
    klient = GP.make_client()
    сделано = {}
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8'):
            з = json.loads(s)
            сделано[(з['модель'], з['inn'])] = з
    исх_новости = SF._dobrat_novosti
    for м in МОДЕЛИ:
        SF.MODEL = м
        SF._dobrat_novosti = исх_новости if м == 'gpt-6-luna' else (lambda *a, **kw: None)

        def одна(к):
            if (м, к['inn']) in сделано:
                return
            t0 = time.time()
            о = SF._razobrat_odnu(klient, к)
            з = {'модель': м, 'inn': к['inn'], 'имя': к['name'], 'сегм': к['сегм'], 'сек': round(time.time() - t0),
                 'note': о.get('note'), 'fakty': о.get('fakty'),
                 'сверка': сверка(к['inn'], о['fakty']) if о.get('fakty') else {}}
            with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
                f.write(json.dumps(з, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            сделано[(м, к['inn'])] = з
        with ThreadPoolExecutor(10) as ex:
            list(ex.map(одна, выбор))
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    итог = {}
    for м in МОДЕЛИ:
        зз = [сделано[(м, к['inn'])] for к in выбор if (м, к['inn']) in сделано]
        ок = [з for з in зз if з.get('fakty')]
        по_ключу = {}
        for ключ in PS.КЛЮЧИ:
            заполн = sum(1 for з in ок if з['сверка'].get(ключ, (0, 0))[0])
            строк = sum(з['сверка'].get(ключ, (0, 0))[0] for з in ок)
            подтв = sum(з['сверка'].get(ключ, (0, 0))[1] for з in ок)
            по_ключу[ключ] = '%d комп., строк %d, подтв. %d%%' % (заполн, строк, round(100 * подтв / строк) if строк else 0)
        строк = sum(sum(v[0] for v in з['сверка'].values()) for з in ок)
        подтв = sum(sum(v[1] for v in з['сверка'].values()) for з in ок)
        итог[м] = {'карточек': len(ок), 'сбоев': [з.get('note') for з in зз if not з.get('fakty')],
                   'строк всего': строк, 'подтверждено, %': round(100 * подтв / строк) if строк else 0,
                   'сек ср': round(sum(з['сек'] for з in зз) / max(1, len(зз))), 'по полям': по_ключу}
    примеры = []
    for к in выбор[:4]:
        а, б = сделано.get(('gpt-5.6-luna', к['inn'])), сделано.get(('gpt-6-luna', к['inn']))
        if а and б and а.get('fakty') and б.get('fakty'):
            примеры.append({'компания': к['name'][:40], 'сегм': к['сегм'][:30],
                            '5.6 продукция': str(а['fakty'].get('продукция'))[:250], '6 продукция': str(б['fakty'].get('продукция'))[:250],
                            '5.6 мощности': str(а['fakty'].get('мощности'))[:150], '6 мощности': str(б['fakty'].get('мощности'))[:150]})
    print('===ИТОГ===')
    print(json.dumps({'компаний': len(выбор), 'сегменты': sorted({к['сегм'][:25] for к in выбор}), 'итог': итог,
                      'новости (Haiku, только прогон GPT-6 Luna)': haiku, 'подмены модели': подмены[:20], 'подмен всего': len(подмены), 'примеры': примеры}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
