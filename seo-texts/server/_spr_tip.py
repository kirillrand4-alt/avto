# -*- coding: utf-8 -*-
"""Тип источника: саморегистрация или собранная база. Ищем формы добавления,
кабинет, «это моя компания», модерацию, дату карточки."""
import io
import json
import os
import re
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')


def get(url, cookie='', tmo=35):
    hd = {'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
          'Accept': 'text/html,application/xhtml+xml,*/*'}
    if cookie:
        hd['Cookie'] = cookie
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hd), timeout=tmo) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace')
        except Exception:
            return e.code, ''
    except Exception as e:
        return -1, str(e)[:80]


def plain(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&quot;', '"'), ('&mdash;', '—'), ('&amp;', '&'),
                 ('&laquo;', '"'), ('&raquo;', '"'), ('&ndash;', '-')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


МАРК = ['добавить компан', 'добавить производител', 'добавить завод', 'зарегистрировать',
        'личный кабинет', 'это моя компания', 'это ваша компания', 'модерац',
        'проходят проверку', 'разместить', 'подтвердить право', 'владелец карточки',
        'бесплатно разместить', 'стать участником', 'тариф', 'подписк',
        'данные взяты из', 'открытых источников', 'егрюл', 'росстат']
R = {}
CK = 'beget=begetok'
цели = [
    ('ozav_главная', 'https://o-zavodah.ru/', CK),
    ('ozav_add', 'https://o-zavodah.ru/add-factory/', CK),
    ('ozav_zavody', 'https://o-zavodah.ru/zavody/', CK),
    ('agro_главная', 'https://www.agrobase.ru/', ''),
    ('agro_orgs', 'https://www.agrobase.ru/organizations', ''),
    ('agro_about', 'https://www.agrobase.ru/about', ''),
    ('agro_manuf_list', 'https://www.agrobase.ru/organizations/manufacturers', ''),
]
for имя, u, ck in цели:
    st, h = get(u, cookie=ck)
    t = plain(h).lower()
    R[имя] = {'st': st, 'len': len(h),
              'маркеры': [m for m in МАРК if m in t],
              'ссылки_add': sorted({x for x in re.findall(r'href="([^"]*(?:add|dobav|register|cabinet|account|lk)[^"]*)"', h)})[:10]}
    time.sleep(1.4)
# карточка производителя agrobase: ищем маркеры и «обновлено»
st, h = get('https://www.agrobase.ru/organizations/manufacturer/'
            'pdmanufacturer_97505953-cdd2-489a-b9f7-94fbb43f501e')
t = plain(h)
R['agro_карточка'] = {
    'st': st, 'маркеры': [m for m in МАРК if m in t.lower()],
    'обновлено': re.findall(r'(?:Обновлено|обновлен[оа]|Дата обновления)[^.]{0,60}', t)[:3],
    'фрагмент_шапки': t[:700]}
time.sleep(1.4)
st, h = get('https://o-zavodah.ru/zavody/ooo-bobrovskii-syrzavod/', cookie=CK)
t = plain(h)
R['ozav_карточка'] = {'st': st, 'маркеры': [m for m in МАРК if m in t.lower()],
                      'фрагмент_низа': t[-900:]}
try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['tip'] = R
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(R, ensure_ascii=False)[:5700])
