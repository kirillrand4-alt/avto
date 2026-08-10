# -*- coding: utf-8 -*-
"""25 случайных строк ЕДИНОЙ БАЗЫ, открытых глазами: «это всё откуда реально было достать?»

Владелец поставил проверку словами: открыть хотя бы 25 случайных ссылок-доказательств и
ответить, действительно ли оттуда добывались факты и контакты, а если не всё — доделать.
Проверяю не поток и не витрину, а саму базу, и по каждой строке спрашиваю ТРИ вещи:

    1. открывается ли ссылка вообще (и если нет — что именно отвечает сервер);
    2. стоит ли на странице ИМЕННО ЭТОТ номер (сравниваю по цифрам, разделители не в счёт);
    3. стоит ли на странице ЭТОТ человек (фамилия) — там, где человек в строке назван.

Отдельно считаю строки, у которых ссылок НЕСКОЛЬКО: по правилу владельца провенанс
накапливается, и если хоть одна из ссылок доказывает — строка доказана. Печатаю, сколько
строк спасла именно вторая ссылка: это прямая цена накопления источников.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ. К выборке добавляю 5 заведомо ЛОЖНЫХ пар: настоящая ссылка из базы
и чужой номер, взятый из другой строки. Мерка обязана уметь сказать «нет»: если контроль
«докажет» хоть одну ложную пару — доверять её «да» нельзя, и я об этом скажу первой.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import random
import re
import ssl
import urllib.request

BAZA = r'C:\sender\_ops\PARK-BAZA-EDINAYA-3S.csv'
SKOLKO = 25
LOZHNYH = 5
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', re.S | re.I)
pamyat = {}


def tyanut(u):
    if u in pamyat:
        return pamyat[u]
    rq = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept-Language': 'ru'})
    with net.open(rq, timeout=40) as rs:
        t = re.sub(r'\s+', ' ', TEG.sub(' ', rs.read(500000).decode('utf-8', 'replace')))
    pamyat[u] = t
    return t


stroki = []
shapka = None
for s in io.open(BAZA, encoding='utf-8-sig'):
    p = s.rstrip('\n').split(';')
    if shapka is None:
        shapka = p
        continue
    if len(p) != len(shapka):
        continue
    stroki.append(dict(zip(shapka, p)))

random.seed(2626)
vybor = random.sample(stroki, min(SKOLKO, len(stroki)))
lozhnye = []
for o in random.sample(stroki, min(LOZHNYH, len(stroki))):
    chuzhoy = random.choice([x for x in stroki if x.get('nomer') and x is not o])
    z = dict(o)
    z['nomer'] = chuzhoy['nomer']
    z['chelovek'] = chuzhoy.get('chelovek', '')
    z['_lozhnaya'] = True
    lozhnye.append(z)

ishody = collections.Counter()
spasla_vtoraya = 0
kontrol_proboy = 0
print('########## ПО ОДНОЙ СТРОКЕ')
for o in vybor + lozhnye:
    us = [u for u in (o.get('istochniki') or '').split(' | ') if u.startswith('http')]
    nomer = re.sub(r'\D', '', o.get('nomer') or '')[-10:]
    fam = (o.get('chelovek') or '').split(' ')[0]
    nashli_nomer, nashli_cheloveka, otkrylos, kakaya = False, False, 0, 0
    oshibka = ''
    for nom_ssylki, u in enumerate(us[:4], 1):
        try:
            t = tyanut(u)
        except Exception as e:  # noqa: BLE001
            oshibka = str(e)[:40]
            continue
        otkrylos += 1
        est_n = bool(nomer) and nomer in re.sub(r'\D', '', t)
        est_ch = bool(fam) and len(fam) > 3 and fam.lower() in t.lower()
        if est_n and not nashli_nomer:
            kakaya = nom_ssylki
        nashli_nomer = nashli_nomer or est_n
        nashli_cheloveka = nashli_cheloveka or est_ch
    if o.get('_lozhnaya'):
        if nashli_nomer:
            kontrol_proboy += 1
            print('  КОНТРОЛЬ ПРОБИТ: чужой номер %s «нашёлся» по %s' % (o['nomer'], us[:1]))
        else:
            print('  контроль: чужой номер %s не подтвердился — мерка умеет говорить «нет»'
                  % o['nomer'])
        continue
    if nashli_nomer and kakaya > 1:
        spasla_vtoraya += 1
    if nashli_nomer and (nashli_cheloveka or not fam):
        v = 'ДОКАЗАНО: номер стоит на странице'
    elif nashli_nomer:
        v = 'номер стоит, человек на странице не назван'
    elif nashli_cheloveka:
        v = 'человек назван, номера на странице нет'
    elif otkrylos:
        v = 'страница открылась, но искомого на ней нет'
    else:
        v = 'НЕ ОТКРЫЛАСЬ НИ ОДНА ССЫЛКА'
    ishody[v.split(':')[0]] += 1
    print('  %-12s %-22s %-14s ссылок %d, открылось %d — %s'
          % (o.get('inn', ''), (o.get('chelovek') or '—')[:22], o.get('nomer', ''),
             len(us), otkrylos, v))
    print('        %s' % (us[0][:110] if us else 'ссылок нет'))
    if oshibka:
        print('        ошибка: %s' % oshibka)

print('\n########## ЧИСЛА')
print('  строк в базе                       %5d' % len(stroki))
print('  проверено                          %5d' % len(vybor))
for k, v in ishody.most_common():
    print('     %-52s %5d' % (k[:52], v))
print('  строк, спасённых ВТОРОЙ ссылкой    %5d  (цена накопления источников)'
      % spasla_vtoraya)
print('  отрицательный контроль: ложных пар %5d, пробито %d %s'
      % (len(lozhnye), kontrol_proboy,
         '— мерке верить нельзя' if kontrol_proboy else '— мерка умеет говорить «нет»'))
print('ИТОГ ' + json.dumps({'проверено': len(vybor), 'исходы': dict(ishody),
                            'контроль пробит': kontrol_proboy}, ensure_ascii=False))
