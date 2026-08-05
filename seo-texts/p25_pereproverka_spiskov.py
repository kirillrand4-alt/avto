# -*- coding: utf-8 -*-
"""Перепроверить 543 спорных привязки по САМИМ страницам: у кого какой работодатель.

ЗАЧЕМ. Люди взяты со страниц-списков, где у каждой строки свой работодатель, а разбор
приписал всех предприятию, которое я искала. Пометка это зафиксировала, но пометка не
чистит данные: продавцу нужно знать, кто ТАМ работает, а кто нет.

Страницы у нас есть — ссылка сохранена у каждого человека. Значит можно перечитать и
взять работодателя ИЗ СТРОКИ ЧЕЛОВЕКА, а не со страницы вообще. Это то же правило
«полосы человека», которым я утром починила карточки площадки: от его имени до
следующего имени — всё его, дальше чужое.

ТРИ ИСХОДА, И КАЖДЫЙ НАЗЫВАЕТСЯ СЛОВОМ:
  * ПОДТВЕРЖДЕНО — в строке человека названо наше предприятие;
  * ОТВЯЗАТЬ — в строке названо ДРУГОЕ место работы, и оно записывается: это не потеря,
    а находка, «Ахмадишин — директор Дома народного творчества» полезнее пустоты;
  * НЕ ОПРЕДЕЛЕНО — строку не нашли или работодатель в ней не назван. Тогда привязка
    остаётся спорной, и это честнее, чем решить наугад.

СРАВНЕНИЕ ПО ЯДРУ ИМЕНИ, а не по строке. «АО "НИЖНЕКАМСКТЕХУГЛЕРОД"» и
«ОАО «Нижнекамск-техуглерод»» — одно предприятие, названное иначе: правовая форма,
кавычки, дефисы и регистр к делу не относятся. Этот приём 2-я сессия уже применяла, и
в панели он подписан «привязка проверена по ядру имени» — беру его же, чтобы правило
не разошлось в двух местах.

Запуск: python3 p25_pereproverka_spiskov.py [--lim N] [--apply]
Без --apply в базу ничего не пишется.
"""
import collections
import csv
import html
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

PUT = r'C:\seostat\data\centrifugal.db'
VYHOD = r'C:\sender\_ops\P25-PEREPROVERKA-SPISKOV-3S.csv'
APPLY = '--apply' in sys.argv
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0 Safari/537.36')
TEG = re.compile(r'<[^>]+>')
PRAVOVAYA = re.compile(
    r'\b(?:ООО|ОАО|ЗАО|АО|ПАО|НАО|ГУП|МУП|ФГУП|АНО|НКО|ИП|ФКУ|ФБУ|ГБУ|МБУ|'
    r'общество\s+с\s+ограниченной\s+ответственностью|акционерное\s+общество|'
    r'публичное\s+акционерное\s+общество|открытое\s+акционерное\s+общество|'
    r'закрытое\s+акционерное\s+общество|группа\s+компаний|гк|управляющая\s+компания)\b',
    re.I)


def yadro(s):
    """Ядро имени: без правовой формы, кавычек, дефисов, пробелов и регистра."""
    t = PRAVOVAYA.sub(' ', str(s or ''))
    t = re.sub(r'[«»"\'`]', ' ', t)
    return re.sub(r'[^а-яёa-z0-9]', '', t.lower())


def vzyat(url, popytok=3):
    for p in range(popytok):
        try:
            rq = urllib.request.Request(url, headers={'User-Agent': UA,
                                                      'Accept-Language': 'ru,en;q=0.8'})
            with urllib.request.urlopen(rq, timeout=60) as r:
                syroy = r.read()
            for kod in ('utf-8', 'cp1251'):
                try:
                    return syroy.decode(kod)
                except Exception:  # noqa: BLE001
                    continue
            return syroy.decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return '__ОШИБКА__ %s' % type(e).__name__
            time.sleep(1.5 * (p + 1))


def stroki_stranicy(h):
    """Страница, разрезанная на строки списка. Пункт списка это и есть полоса человека."""
    t = re.sub(r'(?i)<(?:br|/li|/p|/tr|/div|/h\d)[^>]*>', '\n', h)
    t = TEG.sub(' ', t)
    t = html.unescape(t)
    return [re.sub(r'\s+', ' ', x).strip() for x in t.split('\n') if x.strip()]


# Имя человека, названное в тексте: «Фамилия Имя Отчество» либо «Фамилия И.О.».
# Нужно не чтобы имена находить, а чтобы знать, ГДЕ КОНЧАЕТСЯ полоса нашего человека.
CHUZHOE_IMYA = re.compile(
    r'\b[А-ЯЁ][а-яё]{2,}\s+(?:[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}|[А-ЯЁ]\.\s*[А-ЯЁ]\.?)')


def polosa_v_stroke(stroka, fam, chuzhie):
    """Полоса человека ВНУТРИ строки: от его фамилии до ближайшего следующего имени.

    Первую попытку я обрезала по длине строки — мол, длинная строка это слипшаяся
    страница. Проба показала, что правило пустое: подставная слипшаяся строка уложилась
    в 394 знака и прошла заслон, а с ней прошли и четыре чужих человека, объявленных
    работниками нашего предприятия. Порог в знаках не отличает пункт списка от страницы.

    Отличает — ЧУЖОЕ ИМЯ. Если после нашей фамилии в строке названо следующее лицо, всё
    дальше принадлежит ему. Это то самое правило «полосы», которым утром чинились
    карточки площадки, где Нестеров носил должность Савчука. Границы беру двумя путями:
    фамилии ДРУГИХ людей, взятых с этой же страницы (данные, а не догадка), и общий вид
    русского имени — на случай, если сосед по списку в базу не попал.
    """
    m = re.search(r'\b' + re.escape(fam), stroka, re.I)
    if not m:
        return ''
    nachalo = m.start()
    hvost = stroka[m.end():]
    konec = len(hvost)
    for ch in chuzhie:
        if ch.lower() == fam.lower():
            continue
        c = re.search(r'\b' + re.escape(ch), hvost, re.I)
        if c and c.start() < konec:
            konec = c.start()
    for c in CHUZHOE_IMYA.finditer(hvost):
        if c.group(0).split()[0].lower() != fam.lower() and c.start() < konec:
            konec = c.start()
            break
    return stroka[nachalo:m.end() + konec].strip(' \t—–-,;:')


def stroka_cheloveka(stroki, chel, chuzhie=()):
    """Выбрать полосу ЭТОГО человека и вернуть её же, обрезанную по чужому имени.

    Сухой прогон я смотрела глазами, и там строки были короткие пункты списка. Но брала
    я `max(..., key=len)` — самую ДЛИННУЮ из подходящих. На странице, которая не режется
    на строки, самая длинная строка это вся страница целиком: наше предприятие в ней
    найдётся всегда, и прибор выдаст «ПОДТВЕРЖДЕНО», не проверив ничего.
    """
    chasti = str(chel or '').split()
    fam = chasti[0] if chasti else ''
    if not fam:
        return '', 'имени нет'
    godny = [s for s in stroki if fam.lower() in s.lower()]
    if not godny:
        return '', 'строки человека на странице нет'
    # Имя/отчество целиком или инициалы вида «И.И.» — признак, что назван именно он.
    tochnye = []
    for s in godny:
        nizh = s.lower()
        if chasti[1:] and all(c.lower() in nizh for c in chasti[1:] if len(c) > 2):
            tochnye.append(s)
        elif chasti[1:] and re.search(re.escape(fam) + r'\s*[А-ЯЁ]\.\s*[А-ЯЁ]?\.?', s):
            tochnye.append(s)
    vybor = min(tochnye or godny, key=len)
    pol = polosa_v_stroke(vybor, fam, chuzhie)
    if not pol:
        return '', 'строки человека на странице нет'
    # В полосе осталось одно имя — его собственное; если после обрезки не осталось
    # ничего, кроме имени, работодатель в ней не назван.
    if len(re.sub(r'[^а-яёa-z0-9]', '', pol.lower())) <= len(
            re.sub(r'[^а-яёa-z0-9]', '', chel.lower())) + 3:
        return pol, 'в полосе человека место работы не названо'
    return pol, ''


def main():
    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 10 ** 9
    b = sqlite3.connect(PUT)
    polya = [r[1] for r in b.execute('pragma table_info(person)')]
    imena = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}

    celi = []
    for r in b.execute('select id, inn, person, position, source_url, privyazka_somnitelna '
                       'from person where privyazka_somnitelna is not null '
                       "and privyazka_somnitelna <> ''"):
        celi.append(dict(zip(('id', 'inn', 'person', 'position', 'url', 'pometka'), r)))
    celi = celi[:lim]
    print('к перепроверке %d человек' % len(celi), file=sys.stderr, flush=True)

    # Страницы качаем по одному разу: людей много, страниц мало.
    stranicy, sch = {}, collections.Counter()
    for c in celi:
        u = urllib.parse.unquote(str(c['url'] or ''))
        if u and u not in stranicy:
            stranicy[u] = vzyat(u)
    print('страниц скачано %d' % len(stranicy), file=sys.stderr, flush=True)

    # Соседи по странице: их фамилии — границы полосы нашего человека.
    sosedi = collections.defaultdict(set)
    for r in b.execute('select source_url, person from person where source_url is not null'):
        chasti = str(r[1] or '').split()
        if chasti:
            sosedi[urllib.parse.unquote(str(r[0] or ''))].add(chasti[0])

    # Итог перепроверки пишется в СВОЮ колонку. Прежняя пометка остаётся на месте:
    # источники накапливаются, а не заменяются, и «взят со страницы-списка» — факт
    # о происхождении, который перепроверка не отменяет, чем бы она ни кончилась.
    if 'privyazka_proverena' not in polya:
        if APPLY:
            b.execute('alter table person add column privyazka_proverena text')
            b.commit()
            polya.append('privyazka_proverena')
        else:
            print('колонки privyazka_proverena нет, будет создана', file=sys.stderr)

    stroki, obnovit, snyat, itogi = [], [], [], []
    for c in celi:
        u = urllib.parse.unquote(str(c['url'] or ''))
        h = stranicy.get(u) or ''
        nash = imena.get(str(c['inn']), '')
        chel = str(c['person'] or '').strip()
        fam = chel.split()[0] if chel.split() else ''
        itog, gde_rabotaet, polosa = 'НЕ ОПРЕДЕЛЕНО', '', ''
        if not h or h.startswith('__ОШИБКА__'):
            itog = 'страница не открылась (%s)' % (h[10:].strip() or 'причина не названа')
            sch['страница не открылась'] += 1
        elif not fam:
            itog = 'имени нет — проверять нечего'
            sch[itog] += 1
        else:
            polosa, beda = stroka_cheloveka(stroki_stranicy(h), chel, sosedi.get(u, ()))
            yad = yadro(nash)
            if beda:
                itog = beda
                sch[beda] += 1
            elif len(yad) < 5:
                # Короткое ядро («Квант», «Азот») находится в чужих словах случайно.
                itog = 'название предприятия слишком короткое — судить нельзя'
                sch[itog] += 1
            elif yad in yadro(polosa):
                itog = 'ПОДТВЕРЖДЕНО: наше предприятие названо в строке человека'
                sch['ПОДТВЕРЖДЕНО'] += 1
                # Сомнение снято проверкой — панель должна получить человека чистым.
                snyat.append(c['id'])
            else:
                # Что названо вместо нашего — берём кусок после тире или запятой.
                m = re.search(r'[—–-]\s*(.{5,90})$', polosa)
                gde_rabotaet = (m.group(1) if m else polosa)[:90]
                itog = 'ОТВЯЗАТЬ: в строке названо другое место работы'
                sch['ОТВЯЗАТЬ'] += 1
                obnovit.append((c['id'], gde_rabotaet))
            polosa = polosa[:300]
        itogi.append((('%s || строка источника: %s' % (itog, polosa))[:500], c['id']))
        stroki.append({'inn': c['inn'], 'predpriyatie': nash, 'chelovek': chel,
                       'dolzhnost': c['position'], 'itog': itog,
                       'gde_rabotaet_po_stranice': gde_rabotaet,
                       'stroka_istochnika': polosa, 'ssylka': u})

    if APPLY:
        if itogi:
            b.executemany('update person set privyazka_proverena = ? where id = ?', itogi)
            sch['итог проверки записан'] = len(itogi)
        if obnovit:
            # К прежней пометке ДОПИСЫВАЕМ найденного работодателя, а не затираем её.
            b.executemany(
                'update person set privyazka_somnitelna = '
                'coalesce(privyazka_somnitelna, "") || ? where id = ?',
                [(' || перепроверка: в строке источника названо другое место работы — %s'
                  % g, i) for i, g in obnovit])
            sch['отвязано, работодатель дописан'] = len(obnovit)
        if snyat:
            # Сомнение снято: проверено по строке самого источника.
            b.executemany('update person set privyazka_somnitelna = null where id = ?',
                          [(i,) for i in snyat])
            sch['сомнение снято, отдаётся в панель чистым'] = len(snyat)
        b.commit()

    if stroki:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(stroki[0].keys()), delimiter=';',
                           extrasaction='ignore')
        w.writeheader()
        w.writerows(stroki)
        open(VYHOD, 'w', encoding='utf-8-sig', newline='').write(buf.getvalue())
        url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
        if url and tok:
            rq = urllib.request.Request(url.rstrip('/') + '/' + os.path.basename(VYHOD),
                                        data=buf.getvalue().encode('utf-8-sig'),
                                        method='PUT')
            rq.add_header('X-Drop-Token', tok)
            try:
                sch['выложено, ответ дропа %s' % urllib.request.urlopen(
                    rq, timeout=180).status] += 1
            except Exception as e:  # noqa: BLE001
                sch['выкладка не прошла: %s' % str(e)[:40]] += 1

    for s in stroki[:12]:
        if s['itog'].startswith('ОТВЯЗАТЬ'):
            print('  %-26s %-24s -> %s' % (s['chelovek'][:26], s['predpriyatie'][:24],
                                           s['gde_rabotaet_po_stranice'][:44]))
    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({'режим': 'запись' if APPLY else 'сухой прогон',
                                'проверено': len(celi), 'страниц': len(stranicy)},
                               ensure_ascii=False))


if __name__ == '__main__':
    main()
