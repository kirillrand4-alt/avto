# -*- coding: utf-8 -*-
"""ЛПР по ЭкоНиве: искать людей, а не одного человека. И посмотреть образец — Мосмедыньагропром.

Владелец переставил задачу: искать ЛПР по ЭкоНиве целиком, «можно поискать как
Мосмедыньагропром». Значит сперва смотрю, ЧТО и ОТКУДА добыто по образцу, а потом тем же
приёмом иду по ЭкоНиве.

ПОЧЕМУ ПРЕДЫДУЩИЙ ЗАХОД ДАЛ НОЛЬ И ЭТО МОЯ ОШИБКА. Прицельный поиск вернул 30 документов,
и все 30 мой же фильтр выбросил как «документ без фамилии» — потому что искал ровно
«Самсонов». Под новую задачу фильтр обязан быть другим: брать ЛЮБОГО названного человека
с должностью, а не заранее известного.

ЧТО СПРАШИВАЮ. Форма запроса решает, что попадёт в снимок выдачи, поэтому спрашиваю
несколькими формами: должности круга 1-2 по отдельности плюс страницы руководства и
контактов. ЭкоНива — холдинг, у него много юрлиц и площадок, поэтому иду и по головному
домену, и по слову «ЭкоНива» без site: — но тогда с заслоном.

ЗАСЛОНЫ, КОТОРЫЕ ОБЯЗАНЫ БЫТЬ (наши оплаченные уроки):
  * документ с ЧУЖОГО домена при запросе `site:` — оператор не применён, выдаче не верим;
  * близость не доказывает принадлежность: фамилия рядом со словом «ЭкоНива» на странице
    агрегатора это не сотрудник ЭкоНивы. Поэтому у каждой находки печатается ЦИТАТА и
    ссылка, а вывод не делается за читателя;
  * агрегатор — не первоисточник, помечается отдельно.
"""
import collections
import importlib.util
import json
import os
import re
import sqlite3
import sys

KANDIDATY_SERP = [r'C:\sender\_ops\3s_lpr_obratnyy.py',
                  r'C:\sender\server\lpr_obratnyy.py']
DOMEN = 'ekoniva-apk.ru'
FORMY = [
    'site:%s "главный инженер"' % DOMEN,
    'site:%s "главный энергетик"' % DOMEN,
    'site:%s "главный механик"' % DOMEN,
    'site:%s "технический директор"' % DOMEN,
    'site:%s руководство' % DOMEN,
    'site:%s контакты отдел' % DOMEN,
    'ЭкоНива "главный инженер"',
    'ЭкоНива-АПК "главный энергетик" ФИО',
    'ЭкоНива директор по производству контакты',
]
AGREGATOR = re.compile(r'checko|rusprofile|list-org|zachestnyi|sbis\.ru|audit-it|'
                       r'2gis|yell\.ru|orgpage|spark|kartoteka|sudact', re.I)
FIO = re.compile(r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{3,}'
                 r'(?:ич|вна|чна))\b')
FIO_KRATKO = re.compile(r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ]\.\s*[А-ЯЁ]\.)')
DOLZH = re.compile(
    r'(?:главн\w+|гл\.?)\s*(?:инженер\w*|энергетик\w*|механик\w*|технолог\w*|агроном\w*)|'
    r'техническ\w+\s+директор\w*|директор\w*\s+по\s+[а-яё]+|исполнительн\w+\s+директор\w*|'
    r'начальник\w*\s+[а-яё]+|руководител\w*\s+[а-яё]+|заместител\w*\s+[а-яё]+', re.I)
TEL = re.compile(r'(?:\+7|\b8)[\s\-(]{0,3}\d[\d\s\-()]{7,18}\d')
POCHTA = re.compile(r'[\w.\-]+@[\w.\-]+\.[a-z]{2,}', re.I)


def host(u):
    return re.sub(r'^www\.', '',
                  re.sub(r'^https?://', '', str(u or '')).split('/')[0].lower())


def obrazec():
    """Что добыто по Мосмедыньагропрому и ОТКУДА — образец, названный владельцем."""
    print('=== ОБРАЗЕЦ: Мосмедыньагропром — что у нас есть и чем доказано')
    nashli = 0
    for baza in (r'C:\sender\enrich.db', r'C:\seostat\data\p25.db',
                 r'C:\seostat\data\centrifugal.db', r'C:\sender\tehlpr.db'):
        if not os.path.exists(baza):
            continue
        try:
            cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
            tabl = [r[0] for r in cx.execute(
                "select name from sqlite_master where type='table'")]
        except Exception:  # noqa: BLE001
            continue
        for t in tabl:
            try:
                kol = [r[1] for r in cx.execute('pragma table_info(%s)' % t)]
                stroki = list(cx.execute('select %s from %s' % (','.join(kol), t)))
            except Exception:  # noqa: BLE001
                continue
            for r in stroki:
                sk = ' '.join(str(x or '') for x in r).lower()
                if 'медынь' not in sk and 'medyn' not in sk:
                    continue
                z = {k: v for k, v in zip(kol, r) if v not in (None, '', 0)}
                if not any(k in z for k in ('person', 'post', 'phone', 'email', 'role')):
                    continue
                nashli += 1
                if nashli <= 12:
                    print('  %s.%s: %s' % (os.path.basename(baza), t,
                                           json.dumps(z, ensure_ascii=False)[:230]))
        cx.close()
    print('  строк с людьми по образцу: %d' % nashli)
    return nashli


def main():
    if '--obrazec' in sys.argv:
        obrazec()
        return
    obrazec()

    serp = None
    for put in KANDIDATY_SERP:
        if os.path.exists(put):
            spec = importlib.util.spec_from_file_location('lpr_obr', put)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            serp = m.serp
            print('\nмодуль поиска: %s' % put)
            break
    if not serp:
        print('ИТОГ ' + json.dumps({'поиска нет': True}, ensure_ascii=False))
        return

    sch = collections.Counter()
    lyudi = {}
    print('\n=== ПОИСК ЛПР ПО ЭКОНИВЕ')
    for z in FORMY:
        try:
            docs, err = serp(z)
        except Exception as e:  # noqa: BLE001
            sch['запрос упал: %s' % type(e).__name__] += 1
            continue
        if err:
            sch['ошибка канала'] += 1
            continue
        docs = docs or []
        sch['запросов сделано'] += 1
        svoy = z.split('site:')[1].split()[0] if 'site:' in z else ''
        print('\n### %s -> %d' % (z, len(docs)))
        for d in docs[:10]:
            url, tekst = d.get('url') or '', d.get('tekst') or ''
            h = host(url)
            if svoy and h and svoy not in h:
                sch['ЧУЖОЙ домен вопреки site:'] += 1
                continue
            vid = ('агрегатор — НЕ первоисточник' if AGREGATOR.search(url)
                   else ('сайт предприятия' if DOMEN in h else 'сторонний сайт'))
            dolzh = [x.strip() for x in DOLZH.findall(tekst)][:4]
            polnye = ['%s %s %s' % m for m in FIO.findall(tekst)][:5]
            kratkie = ['%s %s' % m for m in FIO_KRATKO.findall(tekst)][:5]
            if not (polnye or kratkie):
                sch['документ без имён'] += 1
                continue
            for f in polnye + kratkie:
                k = f.lower()
                if k not in lyudi:
                    lyudi[k] = {'fio': f, 'url': url, 'vid': vid,
                                'dolzhnosti_ryadom': dolzh,
                                'telefony': TEL.findall(tekst)[:3],
                                'pochty': [p for p in POCHTA.findall(tekst)
                                           if 'ekoniva' in p.lower()][:3],
                                'citata': re.sub(r'\s+', ' ', tekst)[:300],
                                'zapros': z}
            sch['документов с именами'] += 1
            print('  %s  [%s]' % (url[:88], vid))
            print('     имена: %s' % '; '.join((polnye + kratkie)[:5]))
            if dolzh:
                print('     должности рядом: %s' % '; '.join(x[:44] for x in dolzh[:3]))

    print('\n=== СВОД: найденные люди')
    for k, v in lyudi.items():
        print('\n  %-34s [%s]' % (v['fio'], v['vid']))
        print('     должности рядом: %s' % ('; '.join(v['dolzhnosti_ryadom'][:3]) or '—'))
        if v['telefony']:
            print('     телефоны на странице: %s' % ', '.join(v['telefony']))
        if v['pochty']:
            print('     почты ЭкоНивы: %s' % ', '.join(v['pochty']))
        print('     ссылка: %s' % v['url'][:100])
        print('     цитата: %s' % v['citata'][:200])

    print()
    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({'запросов': sch.get('запросов сделано', 0),
                                'людей найдено': len(lyudi)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
