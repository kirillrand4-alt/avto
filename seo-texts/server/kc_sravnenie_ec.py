# -*- coding: utf-8 -*-
r"""Сравнение «наш обход против серверного обогатителя» на НОВЫХ сайтах (владелец 09.10: «делай так, чтобы почт,
телефонов, ролей, ФИО у нас было не меньше; потом сравнение — разница 0 либо у нас больше; тестирование — на новых
сайтах»).

Компании: из полного списка набора (<набор>-spisok-polnyy.json), не из рабочей выборки, с сайтом, и без файла в кэше
страниц ни по ИНН, ни по домену — сайт не обходили ни Зенка, ни прежний обогатитель. Случайная выборка (seed) по
сегментам.

На каждой компании по очереди:
  A) серверный обогатитель как есть: enrich_contacts.enrich_one — с теми же ограничениями, что внутри обхода (без
     браузера, решателей капч и прокси, без ЕИС/hh/ОПО/VK/SMTP, без поисковой сверки сайта и реквизитов); кэш — в
     отдельной папке A;
  B) наш обход kc_kontakty.обход (свой обход + серверный обогатитель внутри + извлекатели), кэш — в папке B.
Сначала фаза A по всем компаниям, затем B (папку кэша EC берёт из окружения процесса). Итог каждой компании и фазы —
строка в <набор>-sravnenie-ec.jsonl (fsync; резюм по (ИНН, фаза)). Сводка: python kc_sravnenie_ec.py itog

    KC_NABOR=meyer7t KC_SRAV_N=30 python kc_sravnenie_ec.py
"""
import collections
import io
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
НАБОР = os.environ.get('KC_NABOR', 'meyer7t')
ПАПКА = os.path.join(r'C:\seostat\drop', 'pagecache-sravnenie-' + НАБОР)
os.environ['PAGECACHE_DIR'] = os.path.join(ПАПКА, 'B')  # до импорта kc_kontakty: КЭШ_СТРАНИЦ читается при импорте
import kc_kontakty as KK  # noqa: E402
import enrich_contacts as EC  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

ВЫХОД = os.path.join(DIR, НАБОР + '-sravnenie-ec.jsonl')
ОСНОВНОЙ_КЭШ = r'C:\seostat\drop\pagecache'
КАТАЛОГИ = re.compile(r'rusprofile|checko|list-org|zoon|2gis|yandex|google|vk\.com|ok\.ru|avito|hh\.ru|spark-|'
                      r'audit-it|sbis|zachestnyibiznes|kontur|b2b\.house|tiu\.ru|pulscen|\.clients\.site|tochka\.com|'
                      r'sberbank|tinkoff|tbank|alfabank|vtb\.ru|gosuslugi|nalog|\.gov\.ru|gov\d*\.ru|wikipedia|youtube|'
                      r'tilda\.ws|wixsite|ucoz|narod\.ru|blizko|orgpage|spravker|kartaslov|rbc\.ru', re.I)
_лок = threading.Lock()


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def ц(x):
    return re.sub(r'\D', '', x or '')[-10:]


def фио_н(x):
    """ФИО для сравнения: фамилия + инициалы, без регистра и ё."""
    сл = re.findall(r'[А-ЯЁA-Z][а-яёa-z\-]+|[А-ЯЁA-Z]\.', (x or '').replace('ё', 'е'))
    if not сл:
        return ''
    фам = max((w for w in сл if len(w) > 2), key=len, default='')
    return фам.lower()


ОБЩИЕ_EC = ('', 'общий', 'приёмная', 'юрзначимый (ЕГРЮЛ)')
ОБЩИЕ_НАШИ = ('', 'Прочее', 'Общий номер / приёмная')


def свод_ec(r):
    почты = {(e.get('email') or '').lower(): (e.get('role') or '') for e in r.get('emails') or [] if isinstance(e, dict) and e.get('email')}
    тел = {}
    for x in r.get('phone_roles') or []:
        if isinstance(x, dict) and ц(x.get('phone')):
            тел[ц(x['phone'])] = x.get('role') or x.get('dept') or ''
    for x in r.get('phones') or []:
        if isinstance(x, str) and ц(x):
            тел.setdefault(ц(x), '')
    for x in r.get('people') or []:
        if isinstance(x, dict) and ц(x.get('phone')):
            тел.setdefault(ц(x['phone']), x.get('post') or '')
    фио = {фио_н(e.get('person')) for e in r.get('emails') or [] if isinstance(e, dict)}
    фио |= {фио_н(x.get('person')) for x in (r.get('phone_roles') or []) + (r.get('people') or []) if isinstance(x, dict)}
    фио.discard('')
    return {'почты': почты, 'тел': {k: v for k, v in тел.items() if len(k) == 10}, 'фио': фио}


def свод_наш(з):
    почты, тел, фио = {}, {}, set()
    for н in з.get('номера') or []:
        if н.get('почта'):
            почты[н['почта'].lower()] = н.get('роль') or ''
        if н.get('номер') and len(ц(н['номер'])) == 10:
            тел[ц(н['номер'])] = н.get('роль') or ''
        if н.get('фио'):
            фио.add(фио_н(н['фио']))
    for ч in з.get('люди') or []:
        фио.add(фио_н(ч.get('фио')))
    фио.discard('')
    return {'почты': почты, 'тел': тел, 'фио': фио}


def выборка(n):
    сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
    полный = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok-polnyy.json'), encoding='utf-8'))['компании']
    кандидаты = collections.defaultdict(list)
    # домен у нескольких компаний — каталог, банк или сайт группы, а не сайт компании (проба 09.10: check.tochka.com)
    частота = collections.Counter(MN.домен(к.get('сайт') or '') for к in полный.values() if к.get('сайт'))
    for i, к in полный.items():
        сайт = к.get('сайт') or ''
        if i in сп or not сайт or not i.isdigit() or КАТАЛОГИ.search(сайт) or частота[MN.домен(сайт)] > 1:
            continue
        дом = MN.домен(сайт)
        if any(os.path.exists(os.path.join(ОСНОВНОЙ_КЭШ, '%s.json.gz' % к_)) for к_ in (i, re.sub(r'[^a-z0-9.-]', '_', дом)[:60])):
            continue  # сайт уже обходили (Зенка, прежний обогатитель, наш обход)
        кандидаты[(к.get('сегм') or '?')[:40]].append(dict(к, inn=i))
    сл = random.Random(int(os.environ.get('KC_SRAV_SEED', '910')))
    for v in кандидаты.values():
        сл.shuffle(v)
    out, сегм = [], sorted(кандидаты, key=lambda s: -len(кандидаты[s]))
    while len(out) < n and any(кандидаты.values()):
        for s in сегм:
            if кандидаты[s] and len(out) < n:
                out.append(кандидаты[s].pop())
    return out


def сайт_к(к):
    return к['сайт'] if к['сайт'].startswith('http') else 'https://' + к['сайт']


def фаза_A(к):
    t = time.time()
    try:
        ra = EC.enrich_one(KK.ec_компания(к, сайт_к(к)), KK.EC_ТЕМП)
    except Exception as e:  # noqa: BLE001
        ra = {'error': 'сбой: ' + repr(e)[:100]}
    записать({'inn': к['inn'], 'фаза': 'A', 'имя': к.get('имя'), 'сайт': сайт_к(к), 'сегм': к.get('сегм'),
              'сек': round(time.time() - t),
              'r': {k: ra.get(k) for k in ('emails', 'phones', 'phone_roles', 'people', 'error', 'method', 'phones_source',
                                           'staff_search', 'timings')}})


def фаза_B(к):
    t = time.time()
    try:
        rb = KK.обход(к, сайт_к(к))
    except Exception as e:  # noqa: BLE001
        rb = {'сбой': repr(e)[:120]}
    записать({'inn': к['inn'], 'фаза': 'B', 'сайт': сайт_к(к), 'сек': round(time.time() - t), 'r': rb})


def сравнить(з):
    a, b = свод_ec(з['A'].get('r') or {}), свод_наш(з['B'].get('r') or {})
    нет_п = sorted(set(a['почты']) - set(b['почты']))
    нет_т = sorted(set(a['тел']) - set(b['тел']))
    нет_ф = sorted(a['фио'] - b['фио'])
    # роль: контакт, у которого у EC роль конкретная, а у нас — пусто/общий/прочее
    нет_р = [k for k, v in list(a['почты'].items()) + list(a['тел'].items())
             if v not in ОБЩИЕ_EC and (b['почты'].get(k) if '@' in k else b['тел'].get(k)) in ОБЩИЕ_НАШИ + (None,)
             and k not in нет_п and k not in нет_т]
    return {'A': {'почт': len(a['почты']), 'тел': len(a['тел']), 'фио': len(a['фио']),
                  'ролей': sum(1 for v in list(a['почты'].values()) + list(a['тел'].values()) if v not in ОБЩИЕ_EC)},
            'B': {'почт': len(b['почты']), 'тел': len(b['тел']), 'фио': len(b['фио']),
                  'ролей': sum(1 for v in list(b['почты'].values()) + list(b['тел'].values()) if v not in ОБЩИЕ_НАШИ)},
            'нет_у_нас': {'почты': нет_п, 'тел': нет_т, 'фио': нет_ф, 'роли': нет_р}}


def итог():
    рез = collections.defaultdict(dict)
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        рез[з['inn']][з['фаза']] = з
    рез = {i: з for i, з in рез.items() if 'A' in з and 'B' in з}
    сум = collections.Counter()
    разн = []
    for i, з in рез.items():
        с = сравнить(з)
        for сторона in ('A', 'B'):
            for k, v in с[сторона].items():
                сум[сторона + ' ' + k] += v
        for k, v in с['нет_у_нас'].items():
            сум['нет у нас: ' + k] += len(v)
        сум['A сек'] += з['A'].get('сек') or 0
        сум['B сек'] += з['B'].get('сек') or 0
        if any(с['нет_у_нас'].values()):
            разн.append({'inn': i, 'сайт': з['A']['сайт'], **с['нет_у_нас']})
    return {'компаний': len(рез), 'сумма': dict(сум), 'где у нас меньше': разн}


def main():
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                сделано.add((з['inn'], з['фаза']))
            except (ValueError, KeyError):
                pass
    KK.ec_настроить()  # A — с теми же ограничениями, что у обогатителя внутри обхода
    компании = выборка(int(os.environ.get('KC_SRAV_N', '30')))
    потоков = int(os.environ.get('KC_SRAV_POTOKOV', '10'))
    # фазы по очереди: папку кэша EC берёт из окружения процесса при вызове — A и B одновременно идти не должны
    for фаза, f, папка in (('A', фаза_A, 'A'), ('B', фаза_B, 'B')):
        os.environ['PAGECACHE_DIR'] = os.path.join(ПАПКА, папка)
        очередь = [к for к in компании if (к['inn'], фаза) not in сделано]
        print('фаза', фаза, 'компаний', len(очередь), flush=True)
        n = [0]

        def один(к):
            f(к)
            n[0] += 1
            print('фаза %s готово %d/%d' % (фаза, n[0], len(очередь)), flush=True)

        with ThreadPoolExecutor(потоков) as ex:
            list(ex.map(один, очередь))
    with io.open(os.path.join(DIR, НАБОР + '-sravnenie-ec-itog.json'), 'w', encoding='utf-8') as f:
        json.dump(итог(), f, ensure_ascii=False, indent=1)
    print('готово', flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'itog':
        print('===ИТОГ===')
        print(json.dumps(итог(), ensure_ascii=False, indent=1)[:9000])
    else:
        main()
