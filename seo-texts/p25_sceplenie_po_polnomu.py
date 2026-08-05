# -*- coding: utf-8 -*-
"""Сцепка предприятие↔новость по ПОЛНОМУ первоисточнику, а не по обрезке `what`.

Панель считает эту сцепку сама и пишет `signal_match: «НЕТ имени — проверь»` у 32 писем
из 50. Я уже показала на письме #61, что это МЕРА ОБРЕЗКИ: в полном тексте поста ВК имя
«ГК Содружество» названо прямо, вместе с директором по инвестициям. Значит нужно число,
посчитанное по источникам целиком.

ТРИ ЗАСЛОНА, каждый оплачен чьей-то ошибкой сегодня:

  * ВК простым запросом не читается — отдаёт «Your browser is out of date» на 245 знаков.
    Читаю через API с токеном сервера (иначе меряю снимок выдачи, а не первоисточник).
  * Полное имя против короткого: в базе «АКЦИОНЕРНОЕ ОБЩЕСТВО "ГОСУДАРСТВЕННОЕ
    НАУЧНО-ПРОИЗВОДСТВЕННОЕ ПРЕДПРИЯТИЕ "РЕГИОН"», на странице «ГНПП РЕГИОН». Сравнение
    целой строкой не сойдётся никогда — приём 2-й сессии, беру ядро названия и
    аббревиатуру.
  * Оболочка вместо статьи: страница, где шапка портала и НЕТ нашей машины, считается
    непрочитанной, а не «имя не найдено». Разные исходы, разные починки.

Только чтение. Провайдера не трогаю.
"""
import collections
import json
import os
import re
import sqlite3
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

SENDER = r'C:\sender\sender.db'
ENRICH = r'C:\sender\enrich.db'
SKOLKO = int(sys.argv[1]) if len(sys.argv) > 1 else 12

OPF = re.compile(r'\b(?:ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ|АКЦИОНЕРНОЕ ОБЩЕСТВО|'
                 r'ПУБЛИЧНОЕ|НЕПУБЛИЧНОЕ|ЗАКРЫТОЕ|ОТКРЫТОЕ|ООО|ОАО|ЗАО|АО|ПАО|НАО|ГУП|'
                 r'МУП|ФГУП|АНО|ФКУ|ФБУ|ГБУ|МБУ|ГРУППА КОМПАНИЙ|ГК|УПРАВЛЯЮЩАЯ КОМПАНИЯ|'
                 r'УК|ТОРГОВЫЙ ДОМ|ТД|НАУЧНО-ПРОИЗВОДСТВЕННОЕ ПРЕДПРИЯТИЕ|НПП|НПО)\b',
                 re.I)


def yadro(name):
    """Ядро названия: снять ОПФ и кавычки, взять самые длинные слова."""
    s = re.sub(r'[«»"\']', ' ', str(name or ''))
    s = OPF.sub(' ', s)
    slova = [w for w in re.split(r'[\s,\-]+', s) if len(w) >= 4]
    return sorted(slova, key=len, reverse=True)[:3]


def abbr(name):
    s = OPF.sub(' ', re.sub(r'[«»"\']', ' ', str(name or '')))
    b = [w[0] for w in re.split(r'[\s\-]+', s) if w and w[0].isalpha()]
    return ''.join(b).upper() if len(b) >= 2 else ''


def vk_tekst(url):
    m = re.search(r'wall(-?\d+_\d+)', url or '')
    tok = os.environ.get('VK_TOKEN', '')
    if not m or not tok:
        return ''
    D = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    u = ('https://api.vk.com/method/wall.getById?posts=%s&v=5.199'
         % urllib.parse.quote(m.group(1)))
    try:
        r = urllib.request.Request(u, headers={'Authorization': 'Bearer %s' % tok})
        d = json.loads(D.open(r, timeout=30).read().decode('utf-8', 'replace'))
        it = (d.get('response') or {})
        it = it.get('items') if isinstance(it, dict) else it
        return ' '.join(str(x.get('text') or '') for x in (it or []))
    except Exception:  # noqa: BLE001
        return ''


cs = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
kol = [r[1] for r in cs.execute('pragma table_info(confirm_reviews)')]
sel = ','.join('"%s"' % k for k in kol)
pend = [dict(zip(kol, r)) for r in cs.execute(
    'select %s from confirm_reviews where status="pending" order by id desc' % sel)]
sent = [dict(zip(kol, r)) for r in cs.execute(
    'select %s from confirm_reviews where status="sent" order by id desc limit 2' % sel)]
cs.close()

ce = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
imena = {str(i): str(n or '') for i, n in ce.execute('select inn, name from companies')}
sig = collections.defaultdict(list)
for inn, what, url in ce.execute('select inn, what, source_url from signals'):
    if inn:
        sig[str(inn)].append((what or '', url or ''))
ce.close()

print('=== ОЧЕРЕДЬ: pending %d, беру на проверку %d' % (len(pend), SKOLKO))
ishody = collections.Counter()
razbor = []
for d in pend[:SKOLKO]:
    inn = str(d.get('inn') or '')
    nm = imena.get(inn, '')
    ss = sig.get(inn) or []
    what, url = (ss[0] if ss else ('', ''))
    z = {'id': d.get('id'), 'inn': inn, 'email': d.get('email'), 'company': nm,
         'url': url}
    tekst = ''
    if not url:
        z['ИСХОД'] = 'ссылки на первоисточник нет'
    else:
        if 'vk.com' in url:
            tekst = vk_tekst(url)
            z['как читала'] = 'API ВК'
        if not tekst:
            try:
                it = NS.fetch_article({'link': url, 'title': ''})
                tekst = str(it.get('full_text') or '')
                z['как читала'] = z.get('как читала', '') + ' + GET'
                if it.get('obolochka'):
                    z['ИСХОД'] = 'ОБОЛОЧКА — страница не прочитана'
            except Exception as e:  # noqa: BLE001
                z['ИСХОД'] = 'докачка упала: %s' % str(e)[:60]
        if tekst and 'ИСХОД' not in z:
            ya = yadro(nm)
            ab = abbr(nm)
            nash = [w for w in ya if w.lower() in tekst.lower()]
            po_ab = bool(ab) and len(ab) >= 3 and ab in tekst.upper()
            z['знаков'] = len(tekst)
            z['ядро'] = ya
            z['совпало'] = nash or (['аббревиатура %s' % ab] if po_ab else [])
            z['ИСХОД'] = ('ИМЯ НАЙДЕНО в полном тексте' if (nash or po_ab)
                          else 'имени нет и в полном тексте')
        elif 'ИСХОД' not in z:
            z['ИСХОД'] = 'страница не отдалась'
    ishody[z['ИСХОД']] += 1
    razbor.append(z)

print('\n\n########## ДВА ОТПРАВЛЕННЫХ ПИСЬМА ЦЕЛИКОМ (планка)')
for d in sent:
    print('\n----- отправленное #%s -> %s' % (d.get('id'), d.get('email')))
    print('ТЕМА: %s' % str(d.get('subject') or '')[:140])
    print(str(d.get('body') or '')[:1300])

print('\n\n########## ТРИ ПИСЬМА ОЧЕРЕДИ ЦЕЛИКОМ')
for d in pend[:3]:
    print('\n----- очередь #%s -> %s  (ИНН %s, %s)'
          % (d.get('id'), d.get('email'), d.get('inn'),
             imena.get(str(d.get('inn') or ''), '')[:40]))
    print('ТЕМА: %s' % str(d.get('subject') or '')[:140])
    print(str(d.get('body') or '')[:1300])

print('\n\n########## СЦЕПКА ПО ПОЛНОМУ ИСТОЧНИКУ, письмо за письмом')
for z in razbor:
    print('\n  #%-5s ИНН %-12s %s' % (z['id'], z['inn'], str(z['company'])[:44]))
    print('     -> %-34s  %s' % (str(z['email'])[:34], z.get('как читала', '')))
    print('     источник: %s' % str(z['url'])[:104])
    print('     ИСХОД: %s%s' % (z['ИСХОД'],
                                ('   (совпало: %s, знаков %d)'
                                 % (z.get('совпало'), z.get('знаков', 0)))
                                if 'совпало' in z else ''))

print('\n\n########## ЧИСЛА')
for k, v in ishody.most_common():
    print('  %-44s %3d' % (k, v))
print('ИТОГ ' + json.dumps({'проверено': len(razbor), 'исходы': dict(ishody)},
                           ensure_ascii=False))
