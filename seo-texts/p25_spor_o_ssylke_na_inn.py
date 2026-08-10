# -*- coding: utf-8 -*-
"""СПОР ДВУХ ПРИБОРОВ о моей же ссылке `organization/search?searchString=<ИНН>`.

1-я сессия прогнала мою форму С СЕРВЕРА и написала: признак «ИНН виден в теле страницы» —
эхо запроса, потому что выдуманный ИНН 9999999999 встретился в тексте ТРИ раза, а настоящий
один; вывод соседа — «сам ИНН на этой странице как реквизит не печатается, печатается только
название».

Мой замер (браузером, третьей попыткой) сказал иначе: 20 из 20 — «ИНН стоит СРАЗУ ПОСЛЕ слова
ИНН», и отрицательный контроль был ЧИСТ, потому что на выдуманный ИНН страница показала ДРУГУЮ
организацию с ДРУГИМ ИНН, и правило это увидело.

Спорят не выводы, а приборы: ЕИС рисует список скриптом, поэтому urllib видит только пустую
разметку и эхо в поле ввода, а браузер — отрисованную карточку. Правило «ЕИС мерить только
браузером» я вывела в этой же сессии, трижды обжёгшись. Но правило — не доказательство, и
доверять своей памяти против чужого замера нельзя. Поэтому меряю заново и ОБОИМИ приборами
сразу, на одних и тех же двух адресах:

    настоящий ИНН    7424024375  ПАО «Южуралзолото ГК»
    выдуманный ИНН   9999999999  такого нет

Печатаю по каждому прибору: сколько раз в тексте встречается «ИНН <цифры>», какие именно
цифры стоят после слова, найдены ли слова названия. И кладу СНИМОК обеих страниц — чтобы
глазами было видно, кто прав, а не по моему пересказу.

ИСХОД ЗАРАНЕЕ НАЗВАН, чтобы нельзя было подогнать:
    если браузер на настоящем ИНН печатает его ПОСЛЕ слова «ИНН», а на выдуманном — нет,
        прав мой прибор, и ссылка остаётся доказательством ИНН;
    если браузер печатает то же, что urllib (эхо и никакой карточки),
        прав сосед, и 9 141 строке нужен другой признак — слова названия.

Числа в КОНЦЕ.
"""
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
FORMA = 'https://zakupki.gov.ru/epz/organization/search/results.html?searchString=%s'
NASTOYASHCHIY = ('7424024375', ['ЮЖУРАЛЗОЛОТО', 'ЮГК'])
VYDUMANNYY = ('9999999999', ['ЮЖУРАЛЗОЛОТО', 'ЮГК'])
TEG = re.compile(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', re.S | re.I)
POSLE_SLOVA = re.compile(r'ИНН[^0-9A-Za-zА-Яа-я]{0,6}(\d{10}|\d{12})')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def pribor_urllib(inn):
    """Прибор соседа: сырой HTTP, без отрисовки."""
    try:
        rq = urllib.request.Request(FORMA % inn, headers={'User-Agent': UA,
                                                          'Accept-Language': 'ru'})
        syr = net.open(rq, timeout=45).read(600000).decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:60]
    return re.sub(r'\s+', ' ', TEG.sub(' ', syr)), ''


def pribor_brauzer(inn, imya_snimka, popytok=3):
    """Мой прибор: страница отрисована, снимок кладётся на дроп.

    ДВЕ ПОЛОМКИ ПРИБОРА, найденные на первом же заходе, — обе мои:
    1) ответ раннера лежит под ключом `data`, а я читала `result` и получала пустоту;
    2) в `eval_js` поле `return` — это ВЫРАЖЕНИЕ строкой, а я передала питоновское True,
       и на странице выполнялось `() => (True)` — «True is not defined».
    Обе давали «текста нет», и вывод строился на пустоте. Плюс сама ЕИС может ответить
    ошибкой статуса, поэтому пробую несколько раз: доступность меряется частотой.
    """
    besedy = []
    for nomer in range(popytok):
        # МИМО МЁРТВОГО ПРОКСИ (407) И С НЕДОВЕРЕННЫМ СЕРТИФИКАТОМ ПРЯМОГО ПУТИ.
        # Без этих двух ключей браузер сервера не открывает даже example.com, и спор
        # приборов упирался не в ЕИС, а в путь до неё.
        zadanie = {'url': FORMA % inn, 'wait_ms': 9000, 'screenshot': nomer == 0,
                   'proxy': False, 'ignore_https_errors': True,
                   'screenshot_drop': nomer == 0, 'inn': imya_snimka,
                   'eval_js': {'return': 'document.body ? document.body.innerText : ""',
                               'after_ms': 2500}}
        p = subprocess.run([sys.executable, os.path.join(DIR, 'server', 'run_on_server.py'),
                            'browser_probe', json.dumps(zadanie, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=420)
        syr = p.stdout or ''
        i = syr.find('{')
        if i < 0:
            besedy.append((p.stderr or syr)[:60])
            continue
        try:
            o = (json.loads(syr[i:syr.rfind('}') + 1]).get('data')) or {}
        except Exception:  # noqa: BLE001
            besedy.append(syr[:60])
            continue
        t = re.sub(r'\s+', ' ', str(o.get('eval_js_value') or ''))
        besedy.append('попытка %d: длина %d %s' % (nomer + 1, len(t),
                                                   (o.get('error') or '')[:40]))
        if len(t) > 200:
            return t, ' | '.join(besedy)
    return None, ' | '.join(besedy)


def razbor(t, inn, slova):
    """Что именно видно на странице: цифры после слова ИНН и слова названия."""
    if t is None:
        return {'прибор не прочёл': True}
    posle = POSLE_SLOVA.findall(t)
    return {'длина текста': len(t),
            'сколько раз «ИНН <цифры>»': len(posle),
            'какие цифры после слова': ', '.join(sorted(set(posle))[:4]) or '—',
            'НАШ ИНН стоит после слова': inn in posle,
            'слова названия найдены': [s for s in slova if s in t.upper()]}


itog = {}
for kto, (inn, slova) in (('настоящий ИНН 7424024375', NASTOYASHCHIY),
                          ('ВЫДУМАННЫЙ ИНН 9999999999', VYDUMANNYY)):
    t1, e1 = pribor_urllib(inn)
    t2, e2 = pribor_brauzer(inn, 'SPOR-' + inn)
    itog[kto] = {'urllib (прибор соседа)': razbor(t1, inn, slova),
                 'браузер (мой прибор)': razbor(t2, inn, slova),
                 'отметки': {'urllib': e1, 'браузер': e2}}

print('\n\n########## ЧТО ВИДИТ КАЖДЫЙ ПРИБОР')
for kto, v in itog.items():
    print('\n  %s' % kto)
    for pribor in ('urllib (прибор соседа)', 'браузер (мой прибор)'):
        print('    %s' % pribor)
        for k, z in v[pribor].items():
            print('        %-30s %s' % (k, z))
    print('    отметки: %s' % v['отметки'])

n_br = itog['настоящий ИНН 7424024375']['браузер (мой прибор)']
v_br = itog['ВЫДУМАННЫЙ ИНН 9999999999']['браузер (мой прибор)']

# ЗАСЛОН ПЕРЕД ВЫВОДОМ. Первый заход напечатал «ПРАВ СОСЕД» на ДВУХ пустых страницах:
# ни один прибор ничего не прочёл, а вывод всё равно был выдан — ровно то, за что я
# цепляюсь у других. Вывод возможен только если браузер прочёл ОБЕ страницы.
prochel_obe = not n_br.get('прибор не прочёл') and not v_br.get('прибор не прочёл')
prav_ya = (prochel_obe and bool(n_br.get('НАШ ИНН стоит после слова'))
           and not v_br.get('НАШ ИНН стоит после слова'))

print('\n########## КТО ПРАВ')
if not prochel_obe:
    print('  ВЫВОДА НЕТ: браузер не прочёл страницу (настоящий ИНН — %s, выдуманный — %s).'
          % ('прочёл' if not n_br.get('прибор не прочёл') else 'НЕ прочёл',
             'прочёл' if not v_br.get('прибор не прочёл') else 'НЕ прочёл'))
    print('  Это состояние прибора, а не факт о ссылке. Спор остаётся открытым.')
else:
    print('  браузер на настоящем ИНН печатает его после слова «ИНН»: %s'
          % n_br.get('НАШ ИНН стоит после слова'))
    print('  браузер на выдуманном ИНН печатает его после слова «ИНН»: %s'
          % v_br.get('НАШ ИНН стоит после слова'))
    print('  ВЫВОД: %s' % ('прибор 3-й сессии прав — ссылка доказывает ИНН, признак умеет '
                           'говорить «нет»' if prav_ya else
                           'ПРАВ СОСЕД — признаку «ИНН после слова» верить нельзя, нужен '
                           'признак по словам названия'))
print('ИТОГ ' + json.dumps({'обе страницы прочтены': prochel_obe,
                            'прав прибор 3-й сессии': prav_ya if prochel_obe else None},
                           ensure_ascii=False))
