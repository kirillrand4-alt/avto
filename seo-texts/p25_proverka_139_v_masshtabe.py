# -*- coding: utf-8 -*-
"""ПЕРЕПРОВЕРКА ЧУЖОГО ЧИСЛА В ПОЛНОМ МАСШТАБЕ (пункт 5).

1-я сессия (запись 139) взяла ВОСЕМЬ моих ссылок и намерила: машина названа 8 из 8, наш ИНН
0 из 8 — то есть «машина есть, чья не сказано». Восемь ссылок это проба; их вывод я приняла
и переписала мерку. Теперь проверяю то же утверждение НА ВСЁМ СВОЁМ ПАРКЕ, не открывая
страниц: по виду адреса видно, МОЖЕТ ЛИ страница в принципе назвать предприятие.

    КАРТОЧКА (закупки, процедуры, организации, заключения ЭПБ, Тендер.Про) — заказчик на ней
        назван по устройству страницы;
    СТРАНИЦА ПОИСКА — показывает выдачу по запросу; заказчик там может быть, а может не быть,
        и на восьми проверенных его не было ни разу.

Считаю по каждому факту: есть ли у него ХОТЬ ОДНА карточка. Если нет — факт держится только
на поиске, и по мерке 1-й сессии он «машина есть, чья не сказано».

Ноль в любой группе будет означать состояние парка, а не слепоту: обе группы считаются одним
и тем же разбором адреса, и печатаются обе.
"""
import collections, io, json, os, re, urllib.request
OPS = r'C:\sender\_ops'
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
KARTOCHKA = re.compile(r'/epz/order/(notice|orderplan)|/epz/organization/|/procedure/|'
                       r'/procedures/\d|/tender/\d|tender\.pro/api/tender|/conclusion/|'
                       r'/poisk/id/|zakupki\.mos\.ru/newapi', re.I)
POISK = re.compile(r'/epz/order/extendedsearch|/procedures/?\?search=|/poisk/search|'
                   r'[?&]query_field=|/procedures\?name=|[?&]keywords=', re.I)


def stroki(imya):
    p = os.path.join(OPS, imya)
    if os.path.exists(p):
        return io.open(p, encoding='utf-8', errors='replace').read().splitlines()
    try:
        return op.open(urllib.request.Request('%s/%s' % (drop, imya), headers=tok),
                       timeout=300).read().decode('utf-8', 'replace').splitlines()
    except Exception:  # noqa: BLE001
        return []


sch = collections.Counter()
inn_kart, inn_vse = set(), set()
for f in ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl',
          'park_ingest_3d.jsonl', 'PARK-PLOSHCHADKI-DLYA-PARKA-3S.jsonl',
          'PARK-RTS-PODTV-3S.jsonl']:
    for s in stroki(f):
        try: z = json.loads(s)
        except Exception: continue
        us = [u for u in str(z.get('istochniki') or '').split(' | ') if u.startswith('http')]
        if not us:
            sch['фактов без ссылок вовсе'] += 1
            continue
        i = str(z.get('inn') or '').strip()
        if i:
            inn_vse.add(i)
        if any(KARTOCHKA.search(u) for u in us):
            sch['есть КАРТОЧКА — предприятие может быть названо'] += 1
            if i:
                inn_kart.add(i)
        elif any(POISK.search(u) for u in us):
            sch['только СТРАНИЦА ПОИСКА — «машина есть, чья не сказано»'] += 1
        else:
            sch['прочий адрес (сайт предприятия и т. п.)'] += 1
vsego = sum(sch.values())
print('########## ФАКТЫ ПАРКА ПО ТОМУ, МОЖЕТ ЛИ ССЫЛКА НАЗВАТЬ ПРЕДПРИЯТИЕ')
for k, v in sch.most_common():
    print('  %-56s %6d  (%.1f%%)' % (k[:56], v, 100.0 * v / max(1, vsego)))
print('  ВСЕГО фактов %d' % vsego)
print('\n########## ПО ПРЕДПРИЯТИЯМ')
print('  ИНН в парке                                        %5d' % len(inn_vse))
print('  из них ХОТЬ ОДИН факт держится на карточке         %5d' % len(inn_kart))
print('  ТОЛЬКО поиск — по мерке 1-й сессии не доказаны     %5d' % len(inn_vse - inn_kart))
print('ИТОГ ' + json.dumps({'фактов': vsego, 'ИНН': len(inn_vse),
                            'ИНН с карточкой': len(inn_kart),
                            'ИНН только поиск': len(inn_vse - inn_kart)}, ensure_ascii=False))
