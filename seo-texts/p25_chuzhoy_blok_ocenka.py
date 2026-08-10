# -*- coding: utf-8 -*-
"""Сколько у меня таких ошибок: контакт из блока ИСПОЛНИТЕЛЯ приписан ЗАКАЗЧИКУ.

Владелец подчеркнул строку в панели: Зайнуллин, 8-950-940-37-30, «главный инженер»
у ЛУКОЙЛ-Западная Сибирь. Снимок доказательства показал обратное: в документе два блока —

    Сведения о заказчике:   ООО «ЛУКОЙЛ-ЗАПАДНАЯ СИБИРЬ», ИНН 8608048498,
                            pokachizs@lukoil.com, телефон +7 (34669) 3-70-31
    Сведения об исполнителе: ООО ПЦ УГНТУ «НЕФТЕГАЗИНЖИНИРИНГ», ИНН 0277928462,
                            info@ngiugntu.ru, 8(347)216-39-35, 8 (950) 940-37-31

Номер принадлежит ПРОЕКТНОМУ ИНСТИТУТУ, а не заказчику. Заслон «номер у нескольких ИНН»
этого не ловит: номер встречается один раз. Заслон «ссылка открывается» — тоже: страница
живая и цитата честная.

Здесь я оцениваю МАСШТАБ, двумя слоями, и оба называю числом:

  СЛОЙ А, дёшево и по всей базе — признаки подозрения:
     1. домен почты контакта не совпадает с доменом предприятия и не бесплатный;
     2. ссылка-доказательство лежит на домене, который не принадлежит предприятию
        (не его сайт и не общая площадка) — то есть номер взят со страницы третьего лица.
  СЛОЙ Б, дорого и по выборке — открываю страницу и смотрю, стоит ли номер в блоке
     ИСПОЛНИТЕЛЯ/ПОДРЯДЧИКА, а не заказчика. Ищу подписи «Сведения об исполнителе»,
     «Исполнитель:», «Подрядчик:», «Проектная организация» и меряю расстояние от них до
     номера, сравнивая с расстоянием до подписи «заказчик».

Слой А даёт ВЕРХНЮЮ границу подозрения, слой Б — долю подтверждённых на выборке. Умножать
одно на другое я не буду: скажу оба числа и размер выборки.

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

OPS = r'C:\sender\_ops'
BAZA = os.path.join(OPS, 'PARK-BAZA-EDINAYA-3S.csv')
VYBORKA = 40
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', re.S | re.I)
OBSHCHIE = re.compile(r'zakupki\.gov|zakupki\.mos|etpgpb|tender\.pro|roseltorg|rts-tender|'
                      r'tektorg|fabrikant|sberbank-ast|b2b-center|monitor-pb|gosnadzor|'
                      r'checko|list-org|rusprofile|egrul\.nalog|sbis|audit-it|seldon|'
                      r'kontur|google|yandex|hh\.ru|vk\.com', re.I)
BESPLATNYE = re.compile(r'^(mail|gmail|yandex|ya|bk|inbox|list|rambler|outlook|icloud)\.', re.I)
ISPOLNITEL = re.compile(r'сведения об исполнител|исполнитель\s*[:—-]|подрядчик\s*[:—-]|'
                        r'проектная организация|разработчик проекта', re.I)
ZAKAZCHIK = re.compile(r'сведения о заказчик|заказчик\s*[:—-]|застройщик\s*[:—-]', re.I)


def chitat(put):
    out, sh = [], None
    for s in io.open(put, encoding='utf-8-sig'):
        p = s.rstrip('\n').split(';')
        if sh is None:
            sh = p
            continue
        if len(p) == len(sh):
            out.append(dict(zip(sh, p)))
    return out


def host(u):
    return re.sub(r'^https?://(?:www\.)?([^/]+).*', r'\1', u).lower()


stroki = chitat(BAZA)
# домен предприятия: беру из его же почты, если она с непубличного домена, и из ссылок
svoy_domen = collections.defaultdict(set)
for r in stroki:
    p = (r.get('pochta') or '').strip().lower()
    if '@' in p:
        d = p.split('@')[-1]
        if d and not BESPLATNYE.match(d) and not OBSHCHIE.search(d):
            svoy_domen[r['inn']].add(d)

sloy_a = collections.Counter()
podozr = []
for r in stroki:
    inn = r['inn']
    p = (r.get('pochta') or '').strip().lower()
    us = [u for u in (r.get('istochniki') or '').split(' | ') if u.startswith('http')]
    priznaki = []
    if '@' in p:
        d = p.split('@')[-1]
        if d and not BESPLATNYE.match(d) and svoy_domen.get(inn) and d not in svoy_domen[inn]:
            priznaki.append('домен почты не совпадает с доменом предприятия')
    chuzhie = [u for u in us if not OBSHCHIE.search(host(u))
               and svoy_domen.get(inn) and not any(d in host(u) for d in svoy_domen[inn])]
    if chuzhie and not [u for u in us if svoy_domen.get(inn)
                        and any(d in host(u) for d in svoy_domen[inn])]:
        priznaki.append('все ссылки — на домене третьего лица')
    if priznaki:
        sloy_a[' + '.join(priznaki)] += 1
        if r.get('nomer'):
            podozr.append((r, chuzhie or us))
    else:
        sloy_a['признаков нет'] += 1

# СЛОЙ Б: выборка подозрительных строк с номером — открываю и смотрю, чей блок
random.seed(909)
obr = random.sample(podozr, min(VYBORKA, len(podozr))) if podozr else []
sloy_b = collections.Counter()
primery = []
for r, us in obr:
    nom = re.sub(r'\D', '', r.get('nomer') or '')[-10:]
    naydeno = False
    for u in us[:2]:
        try:
            with net.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                             'Accept-Language': 'ru'}),
                          timeout=40) as rs:
                t = re.sub(r'\s+', ' ', TEG.sub(' ', rs.read(500000).decode('utf-8', 'replace')))
        except Exception:  # noqa: BLE001
            continue
        cif = re.sub(r'\D', '', t)
        if nom and nom in cif:
            naydeno = True
            # где стоит номер: ближе к подписи исполнителя или заказчика
            i = None
            for m in re.finditer(re.escape(nom[:3]), re.sub(r'\D', '', t)):
                i = m.start()
                break
            # грубая, но честная мера: сравниваю ближайшие подписи в ПЛОСКОМ тексте
            poz = t.find(nom[:3])
            bl_isp = max([m.start() for m in ISPOLNITEL.finditer(t) if m.start() < poz] or [-1])
            bl_zak = max([m.start() for m in ZAKAZCHIK.finditer(t) if m.start() < poz] or [-1])
            if bl_isp > bl_zak and bl_isp >= 0:
                sloy_b['номер стоит ПОСЛЕ подписи «исполнитель» — приписан не тому'] += 1
                if len(primery) < 8:
                    primery.append((r['inn'], (r.get('chelovek') or '')[:22], r.get('nomer'),
                                    u[:70]))
            elif bl_zak >= 0:
                sloy_b['номер стоит после подписи «заказчик» — привязка верна'] += 1
            else:
                sloy_b['подписей «заказчик/исполнитель» на странице нет'] += 1
            break
    if not naydeno:
        sloy_b['номера на странице не нашлось (страница сменилась или не открылась)'] += 1

print('\n\n########## СЛОЙ Б: ПРИМЕРЫ, ГДЕ НОМЕР ИЗ БЛОКА ИСПОЛНИТЕЛЯ')
for p in primery:
    print('  %-12s %-22s %-14s %s' % p)
print('\n########## ЧИСЛА')
print('  строк в базе                       %6d  (файл %s)' % (len(stroki),
                                                               os.path.basename(BAZA)))
print('  --- СЛОЙ А: признаки подозрения по всей базе')
for k, v in sloy_a.most_common():
    print('     %-56s %6d' % (k[:56], v))
print('  подозрительных СТРОК С НОМЕРОМ     %6d' % len(podozr))
print('  --- СЛОЙ Б: выборка %d из них, открыто с сервера' % len(obr))
for k, v in sloy_b.most_common():
    print('     %-56s %6d' % (k[:56], v))
n_isp = sloy_b['номер стоит ПОСЛЕ подписи «исполнитель» — приписан не тому']
n_pro = sum(v for k, v in sloy_b.items() if 'не нашлось' not in k)
print('  доля «чужой блок» среди проверенных %6s'
      % ('%.0f%%' % (100.0 * n_isp / n_pro) if n_pro else '—'))
print('ИТОГ ' + json.dumps({'строк': len(stroki), 'подозрительных с номером': len(podozr),
                            'выборка': len(obr), 'чужой блок': n_isp,
                            'проверено по существу': n_pro}, ensure_ascii=False))
