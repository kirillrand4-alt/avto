# -*- coding: utf-8 -*-
"""362 предприятия парка без названия. Беру имена в реестре организаций ЕИС по ИНН.

Это последняя дыра очереди: без названия предприятия запрос «"ФИО" "<компания>"»
вырождается в поиск однофамильцев по стране, и поиск ЛПР по таким ИНН делать бессмысленно.
Замер прошлой смены: полное имя даёт 10 доказуемых из 12, аббревиатура — 3 из 12.

Где брать. В базах их нет (проверено: 12 567 названий, эти 362 не покрыты), в моих потоках
тоже (443 добраны, остальные пусты). Зато у ЕИС есть реестр организаций с поиском по ИНН:

    zakupki.gov.ru/epz/organization/search/results.html?searchString=<ИНН>

Страница открывается с сервера обычным запросом — тем же путём, каким берётся выдача
закупок, и её адрес сам по себе служит ссылкой-доказательством названия.

ЗАСЛОН: имя засчитывается, только если на странице ЕСТЬ сам ИНН. Иначе это выдача «ничего
не найдено» с чужой организацией в подсказках, и я припишу предприятию чужое имя — ошибка
того же рода, что «номер одного человека у имени другого».

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import ssl
import time
import urllib.request

POTOKI = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
          r'C:\sender\_ops\park_ingest_3c.jsonl']
S_IMENAMI = r'C:\sender\_ops\CELI-PARK-S-IMENAMI-3S.csv'
VYHOD = r'C:\sender\_ops\PARK-IMENA-IZ-EIS-3S.csv'
SKOLKO = 200
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
IMYA = re.compile(r'registry-entry__body-href[^>]*>\s*<a[^>]*>\s*([^<]{6,200})</a>', re.S)
IMYA2 = re.compile(r'registry-entry__body-value[^>]*>\s*([^<]{6,200})<', re.S)

park = set()
for p in POTOKI:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            i = json.loads(s).get('inn')
        except Exception:  # noqa: BLE001
            continue
        if i:
            park.add(i)
est = set()
if os.path.exists(S_IMENAMI):
    for s in io.open(S_IMENAMI, encoding='utf-8-sig').read().splitlines()[1:]:
        p_ = s.split(';')
        if p_ and p_[0].strip().isdigit():
            est.add(p_[0].strip())
# в очереди с именами лежат только те, у кого имя нашлось; остальные — цель
bez = sorted(park - est)[:SKOLKO]

nashli, ishody = [], collections.Counter()
for inn in bez:
    u = ('https://zakupki.gov.ru/epz/organization/search/results.html?searchString=%s'
         '&morphology=on&sortBy=UPDATE_DATE' % inn)
    try:
        h = op.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                       'Accept-Language': 'ru'}),
                    timeout=60).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        ishody['ошибка сети: %s' % str(e)[:34]] += 1
        continue
    t = re.sub(r'\s+', ' ', TEG.sub(' ', h))
    if inn not in t:
        ishody['ИНН на странице нет — организация не найдена'] += 1
        continue
    m = IMYA.search(h) or IMYA2.search(h)
    nm = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
    if not nm or len(nm) < 6:
        ishody['ИНН есть, а название не разобралось'] += 1
        continue
    nashli.append({'inn': inn, 'predpriyatie': nm, 'istochnik': u})
    ishody['название найдено'] += 1
    time.sleep(0.35)

with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write('inn;predpriyatie;istochnik\n')
    for o in nashli:
        f.write(';'.join(str(o[k]).replace(';', ',') for k in
                         ('inn', 'predpriyatie', 'istochnik')) + '\n')
try:
    o2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = o2.open(rq, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ НАЙДЕННЫХ')
for o in nashli[:10]:
    print('  %-12s %s' % (o['inn'], o['predpriyatie'][:70]))
print('\n########## ЧИСЛА')
print('  ИНН в парке              %5d' % len(park))
print('  из них с именем уже      %5d' % len(est & park))
print('  спрошено в реестре ЕИС   %5d' % len(bez))
for k, v in ishody.most_common():
    print('     %-52s %5d' % (k[:52], v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'спрошено': len(bez), 'найдено': len(nashli)}, ensure_ascii=False))
