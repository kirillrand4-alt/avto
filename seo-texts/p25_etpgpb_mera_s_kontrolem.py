# -*- coding: utf-8 -*-
"""Мерка для ЭТП ГПБ, которая умеет сказать «нет». Прошлая не умела и потому ничего не стоила.

Прошлая проба искала обозначение машины ГДЕ УГОДНО на странице — и заведомо неверный адрес
`/etp/<номер>-x/` «доказал» 8 из 8 наравне с рабочим. Страницы по 400–500 КБ, обозначение
находится в боковых списках и «похожих закупках».

Новая мерка сравнивает НАЗВАНИЕ ЗАКУПКИ со страницы с названием из нашей строки. Если адрес
ведёт не туда, название не совпадёт — вот и весь смысл. Проверяю на трёх наборах:

    рабочий номер + рабочий адрес     ожидаю совпадение
    рабочий номер + сокращённый адрес ожидаю совпадение, если форма годная
    ЗАВЕДОМО НЕСУЩЕСТВУЮЩИЙ номер     ожидаю НЕсовпадение — это и есть контроль

Если контрольный набор снова «докажет», мерка опять негодная, и я это напечатаю первым, а
не спрячу за красивой долей.

Числа в КОНЦЕ.
"""
import io
import json
import re
import ssl
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
TITLE = re.compile(r'<title[^>]*>(.*?)</title>', re.S | re.I)
H1 = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S | re.I)
TEG = re.compile(r'<[^>]+>')
POTOK = r'C:\sender\_ops\park_ingest_3.jsonl'


def slova(s, n=6):
    return [w.lower() for w in re.findall(r'[А-Яа-яA-Za-z]{5,}', s or '')][:n]


def zagolovok(h):
    m = H1.search(h) or TITLE.search(h)
    return re.sub(r'\s+', ' ', TEG.sub(' ', m.group(1))).strip() if m else ''


pары = []
vid = set()
for s in io.open(POTOK, encoding='utf-8'):
    o = json.loads(s)
    for u in (o.get('istochniki') or '').split(' | '):
        m = re.search(r'etpgpb\.ru/procedure/tender/etp/(\d+)-([a-z0-9\-]+)/?', u)
        if m and m.group(1) not in vid:
            vid.add(m.group(1))
            pары.append((m.group(1), m.group(2), u))
    if len(pары) >= 6:
        break

NABORY = [
    ('рабочий адрес из базы', lambda n, hv: 'https://etpgpb.ru/procedure/tender/etp/%s-%s/' % (n, hv)),
    ('сокращённый без хвоста', lambda n, hv: 'https://etpgpb.ru/procedure/tender/etp/%s/' % n),
    ('КОНТРОЛЬ: несуществующий номер',
     lambda n, hv: 'https://etpgpb.ru/procedure/tender/etp/%s/' % (int(n) + 7654321)),
]
itog = {imya: {'sovpalo': 0, 'net': 0, 'zag': []} for imya, _ in NABORY}
print('########## ПО ОДНОЙ')
for n, hv, u in pары:
    # эталон — заголовок рабочей страницы
    try:
        et = zagolovok(op.open(urllib.request.Request(u, headers={'User-Agent': UA}),
                               timeout=45).read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        et = ''
    for imya, f in NABORY:
        adr = f(n, hv)
        try:
            h = op.open(urllib.request.Request(adr, headers={'User-Agent': UA}),
                        timeout=45).read().decode('utf-8', 'replace')
            z = zagolovok(h)
            a, b = set(slova(et)), set(slova(z))
            sovp = bool(a) and len(a & b) >= max(2, len(a) // 2)
            itog[imya]['sovpalo'] += 1 if sovp else 0
            itog[imya]['zag'].append(z[:60])
            print('  %-9s %-30s совпало %-5s | %s' % (n, imya[:30], sovp, z[:60]))
        except Exception as e:  # noqa: BLE001
            itog[imya]['net'] += 1
            print('  %-9s %-30s НЕ ОТКРЫЛАСЬ %s' % (n, imya[:30], str(e)[:36]))
print('\n########## ЧИСЛА')
for imya, _ in NABORY:
    z = itog[imya]
    print('  %-32s совпало %d из %d | не открылась %d | разных заголовков %d'
          % (imya, z['sovpalo'], len(pары), z['net'], len(set(z['zag']))))
kontrol = itog['КОНТРОЛЬ: несуществующий номер']['sovpalo']
print('  --- ВЕРДИКТ')
if kontrol > 0:
    print('  МЕРКА НЕГОДНАЯ: контрольный несуществующий номер «совпал» %d раз' % kontrol)
else:
    print('  мерка различает: контроль не совпал ни разу')
print('ИТОГ ' + json.dumps({imya: itog[imya]['sovpalo'] for imya, _ in NABORY},
                           ensure_ascii=False))
