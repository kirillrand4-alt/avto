# -*- coding: utf-8 -*-
"""Очередь писем: проверить СЦЕПЛЕНИЕ предприятие+новость+контакт по ПОЛНОМУ первоисточнику.

Владелец: «правдоподобное письмо на неверном адресате выглядит убедительно — ошибка видна
только по первоисточнику». Значит проверять надо не текст письма (он всегда гладкий), а
три сцепки, и каждую по своему доказательству:

    ПРЕДПРИЯТИЕ  названо ли НАШЕ юрлицо на странице первоисточника (не в снимке выдачи)
    НОВОСТЬ      то ли событие на странице, о котором письмо, и наша ли машина там
    КОНТАКТ      кому уходит: именной ящик, техническая роль, нетехническая, общий

1-я сессия прочитала три письма глазами и нашла письмо про замену компрессоров,
адресованное ГЛАВНОМУ БУХГАЛТЕРУ. Это анекдот, пока он один; я считаю то же самое по
всей очереди — сколько писем уходит на нетехнический адрес. Один случай — история,
число — мера.

Первоисточник качаю ЦЕЛИКОМ (`news_scan.fetch_article`), а не беру снимок выдачи. И сразу
отделяю оболочку: страница, где в первых двух тысячах знаков таблица стилей или рассказ
портала о себе, — не прочитана, и это пишется отдельным исходом, а не «не подтвердилось».

Только чтение. Провайдера не трогает.
"""
import collections
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
try:
    import news_scan as NS
except Exception:  # noqa: BLE001
    NS = None

SENDER = r'C:\sender\sender.db'
ENRICH = r'C:\sender\enrich.db'
SKOLKO_ISTOCHNIKOV = int(sys.argv[1]) if len(sys.argv) > 1 else 12

MASHINA = re.compile(
    r'компрессор\w*|турбокомпрессор\w*|газодувк\w+|воздуходувк\w+|нагнетател\w+|'
    r'воздухоразделен\w+|\bВРУ\b|сжат\w+\s+воздух\w*|пневмат\w+|\bазот\w*\b|'
    r'\bкислород\w*\b|\bчиллер\w*', re.I)
NETEH = re.compile(r'^(?:glavbuh|buh|buhg|account|finance|fin|hr|kadr|pr|market|sales|'
                   r'sale|shop|zakaz|order)\b', re.I)
TEH = re.compile(r'^(?:glaveng|glavniy|energ|energetik|mech|meh|oms|omts|otms|snab|'
                 r'zakup|tender|proekt|prom|tech|teh)\b', re.I)
OBSHCHIY = re.compile(r'^(?:info|office|mail|post|secretary|priemnaya|reception|kanc|'
                      r'general|company|admin|contact)\b', re.I)
IMENNOY = re.compile(r'^[a-z]{1,2}[._-][a-z]{3,}$|^[a-z]{3,}[._-][a-z]{1,2}$|'
                     r'^[a-z]{3,}\.[a-z]{3,}$', re.I)
OBOLOCHKA = re.compile(r'\{[a-z-]+:[^}]{2,80}\}|Официальный сайт Единой информационной|'
                       r'включите JavaScript|enable JavaScript', re.I)


def vid_adresa(em):
    lok = str(em or '').split('@')[0].lower()
    if NETEH.match(lok):
        return 'НЕТЕХНИЧЕСКИЙ (бухгалтерия/кадры/продажи)'
    if TEH.match(lok):
        return 'техническая роль'
    if OBSHCHIY.match(lok):
        return 'общий ящик'
    if IMENNOY.match(lok):
        return 'именной'
    return 'прочий'


if not os.path.exists(SENDER):
    print('ИТОГ ' + json.dumps({'нет базы': SENDER}, ensure_ascii=False))
    raise SystemExit

cs = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
kol = [r[1] for r in cs.execute('pragma table_info(messages)')]
print('=== messages: колонки %s' % kol)
sch_st = collections.Counter()
for st, n in cs.execute('select status, count(*) from messages group by status'):
    sch_st[str(st)] = n
print('=== СТАТУСЫ: %s' % dict(sch_st))

sel = ','.join('"%s"' % k for k in kol)
stroki = [dict(zip(kol, r)) for r in cs.execute(
    'select %s from messages where status in ("pending_review","sent") order by rowid desc'
    % sel)]
cs.close()

# --- сигналы по ИНН -------------------------------------------------------------------
sig = collections.defaultdict(list)
ver = {}
if os.path.exists(ENRICH):
    ce = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    for inn, what, url, ist in ce.execute(
            'select inn, what, source_url, source from signals'):
        if inn:
            sig[str(inn).strip()].append((what or '', url or '', ist or ''))
    for inn, v, nm in ce.execute('select inn, verified, name from companies'):
        if inn:
            ver[str(inn).strip()] = (str(v or ''), str(nm or ''))
    ce.close()

pole_inn = 'inn' if 'inn' in kol else None
pole_em = ([k for k in kol if k.lower() in ('to_email', 'email', 'to', 'recipient')] or [None])[0]
pole_te = ([k for k in kol if k.lower() in ('body', 'text', 'html', 'content')] or [None])[0]
pole_su = ([k for k in kol if k.lower() in ('subject', 'title', 'tema')] or [None])[0]
print('=== поля: ИНН=%s адрес=%s тело=%s тема=%s' % (pole_inn, pole_em, pole_te, pole_su))

# --- сцепка по первоисточнику ----------------------------------------------------------
ochered = [d for d in stroki if str(d.get('status')) == 'pending_review']
print('\n=== В ОЧЕРЕДИ ПОДТВЕРЖДЕНИЯ: %d писем' % len(ochered))

ishod = collections.Counter()
vidy = collections.Counter()
razbor = []
for d in ochered:
    em = str(d.get(pole_em) or '') if pole_em else ''
    vidy[vid_adresa(em)] += 1

proverem = ochered[:SKOLKO_ISTOCHNIKOV]
for d in proverem:
    inn = str(d.get(pole_inn) or '').strip() if pole_inn else ''
    em = str(d.get(pole_em) or '') if pole_em else ''
    telo = str(d.get(pole_te) or '') if pole_te else ''
    v, nm = ver.get(inn, ('', ''))
    ss = sig.get(inn) or []
    what, url, ist = (ss[0] if ss else ('', '', ''))
    zapis = {'rowid': d.get('rowid') or d.get('id'), 'inn': inn, 'email': em,
             'vid': vid_adresa(em), 'verified': v, 'company': nm,
             'what': what[:200], 'url': url, 'source': ist}
    if not url:
        zapis['ИСХОД'] = 'ссылки на первоисточник нет'
        ishod['ссылки нет'] += 1
    elif NS is None:
        zapis['ИСХОД'] = 'модуль докачки недоступен'
        ishod['докачки нет'] += 1
    else:
        try:
            it = NS.fetch_article({'link': url, 'title': ''})
            ft = str(it.get('full_text') or '')
        except Exception as e:  # noqa: BLE001
            ft = ''
            zapis['ошибка'] = str(e)[:80]
        if not ft:
            zapis['ИСХОД'] = 'страница не отдалась'
            ishod['страница не отдалась'] += 1
        elif OBOLOCHKA.search(ft[:2000]):
            zapis['ИСХОД'] = 'ОБОЛОЧКА, не текст (проверять нечем)'
            ishod['оболочка'] += 1
        else:
            korotkoe = re.sub(r'^(ООО|АО|ПАО|ЗАО|ОАО|НАО)\s+', '', nm or '')
            korotkoe = re.sub(r'[«»"]', '', korotkoe).strip()
            nazvano = bool(korotkoe) and korotkoe.lower()[:18] in ft.lower()
            mash = bool(MASHINA.search(ft))
            zapis.update({'знаков': len(ft), 'ПРЕДПРИЯТИЕ НАЗВАНО': nazvano,
                          'МАШИНА НА СТРАНИЦЕ': mash,
                          'ИСХОД': ('сцепка подтверждена' if nazvano else
                                    'ПРЕДПРИЯТИЕ НА СТРАНИЦЕ НЕ НАЗВАНО')})
            ishod[zapis['ИСХОД']] += 1
    razbor.append(zapis)

print('\n\n########## ТРИ ПИСЬМА ЦЕЛИКОМ (глазами)')
for d in ochered[:3]:
    print('\n\n-------- письмо rowid %s --------' % (d.get('rowid') or d.get('id')))
    for k in kol:
        v = d.get(k)
        if v in (None, ''):
            continue
        s = str(v)
        if k == pole_te and len(s) > 100:
            print('  %s:\n%s' % (k, s[:1800]))
        else:
            print('  %-16s %s' % (k, s[:160]))

print('\n\n########## СЦЕПКА ПО ПЕРВОИСТОЧНИКУ, письмо за письмом')
for z in razbor:
    print('\n  письмо %-6s ИНН %-12s -> %s  [%s]'
          % (z.get('rowid'), z.get('inn'), z.get('email'), z.get('vid')))
    print('     компания: %s   verified=%s' % (str(z.get('company'))[:44], z.get('verified')))
    print('     повод:    %s' % str(z.get('what'))[:140])
    print('     источник: %s' % str(z.get('url'))[:110])
    print('     ИСХОД:    %s%s' % (z.get('ИСХОД'),
                                   '' if 'знаков' not in z else
                                   '   (страница %d знаков, машина на ней: %s)'
                                   % (z['знаков'], z['МАШИНА НА СТРАНИЦЕ'])))

print('\n\n########## ЧИСЛА')
print('  статусы очереди: %s' % dict(sch_st))
print('  в очереди подтверждения: %d' % len(ochered))
print('  --- КУДА уходят письма очереди (вид адреса)')
for k, n in vidy.most_common():
    print('    %-46s %4d' % (k, n))
print('  --- исход проверки сцепки по первоисточнику (проверено %d)' % len(razbor))
for k, n in ishod.most_common():
    print('    %-46s %4d' % (k, n))
print('ИТОГ ' + json.dumps({'в очереди': len(ochered), 'виды адресов': dict(vidy),
                            'исходы': dict(ishod)}, ensure_ascii=False))
