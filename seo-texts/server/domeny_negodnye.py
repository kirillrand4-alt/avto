# -*- coding: utf-8 -*-
r"""Единый справочник негодных доменов почты — по ВСЕЙ базе, а не по нашей выборке.

Владелец 19.08: «adygheya.gov.ru, eo.tensor.ru — подобные пометить как негодные
для отправки», и следом: «там было около 200к почт». Счёт подтвердился: 199 375
уникальных адресов, из них 163 953 живут в базе обзвона и лишь 35 422 собраны
нами. Помечать только в enrich.emails — закрыть шестую часть проблемы, поэтому
справочник строится ПО ОБОИМ источникам и хранится отдельной таблицей: любой
потребитель (выборка рассылки, панель, будущие сессии) сверяется по домену.

Три уровня, и разница в том, что с ними делать:

  запрет      сервис отчётности/ЭДО (tensor, sbis, kontur, diadoc, taxcom,
              astral, nalog.*): это ящик документооборота, живого адресата нет
              никогда. Слать нельзя.
  запрет      госпортал (gov.ru, mos.ru и подобные), обслуживающий 3+ юрлица:
              письмо уйдёт в общую канцелярию, а не адресату.
  осторожно   прочий чужой домен на 5+ юрлиц: это либо группа компаний со своим
              доменом (doorhan.ru, gazprom-neft.ru — писать МОЖНО, но адресата
              надо проверить), либо справочник. Запрещать вслепую нельзя.

Бесплатная почта (mail.ru, yandex.ru и т.д.) НЕ считается общим доменом: для
российского малого предприятия это нормальный рабочий ящик, а по числу юрлиц
она держит первые места (mail.ru — 2813) и без исключения утопила бы правило.

    python domeny_negodnye.py            посчитать
    python domeny_negodnye.py --primenit построить справочник
"""
import json
import os
import re
import sqlite3
import sys
import time

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
OBZVON = r'C:\sender\obzvon-index.db'
СХЕМА = """CREATE TABLE IF NOT EXISTS domeny_negodnye(
    domen TEXT PRIMARY KEY, uroven TEXT, prichina TEXT,
    yurlic INTEGER, ts TEXT)"""
ЭДО = re.compile(
    r'(^|\.)(tensor|sbis|kontur|diadoc|taxcom|astral|edo|nalog)\.', re.I)
ГОСПОРТАЛ = re.compile(r'(^|\.)(gov|mos|spb|gosuslugi)\.(ru|рф)$|(^|\.)gov\.', re.I)
FREEMAIL = {'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'list.ru',
            'inbox.ru', 'rambler.ru', 'internet.ru', 'mail.com', 'icloud.com',
            'outlook.com', 'hotmail.com', 'yahoo.com', 'narod.ru', 'me.com',
            'bk.ru', 'vk.com', 'mail.ua', 'ukr.net'}
ПОРОГ_ПОРТАЛА = 3
ПОРОГ_ОБЩЕГО = 5
_АДРЕС = re.compile(r'[\w.+-]+@([\w.-]+\.[a-zA-Zрф]{2,})')


def юрлица_по_доменам():
    """Домен -> множество ИНН. Считаем по обоим источникам сразу."""
    из = {}
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    for inn, email in c.execute("select inn, email from emails "
                                "where coalesce(email,'')<>''"):
        д = (str(email).split('@')[-1] or '').lower().strip('.')
        if д:
            из.setdefault(д, set()).add(str(inn))
    c.close()
    if os.path.exists(OBZVON):
        o = sqlite3.connect('file:%s?mode=ro' % OBZVON.replace('\\', '/'), uri=True)
        for inn, base, site in o.execute(
                "select inn, coalesce(emails_base,''), coalesce(emails_site,'') "
                'from obzvon'):
            инн = ''.join(ch for ch in str(inn or '') if ch.isdigit())
            if not инн:
                continue
            for кусок in (base, site):
                for д in _АДРЕС.findall(кусок or ''):
                    из.setdefault(д.lower().strip('.'), set()).add(инн)
        o.close()
    return из


def разбор(применять=False):
    домены = юрлица_по_доменам()
    решения, свод = [], {'доменов_всего': len(домены), 'запрет_эдо': 0,
                         'запрет_госпортал': 0, 'осторожно_общий': 0}
    примеры = {}
    for д, инны in домены.items():
        n = len(инны)
        уровень = причина = ''
        if ЭДО.search(д):
            уровень, причина = 'запрет', 'сервис отчётности/ЭДО — живого адресата нет'
            свод['запрет_эдо'] += 1
        elif ГОСПОРТАЛ.search(д) and n >= ПОРОГ_ПОРТАЛА:
            уровень = 'запрет'
            причина = 'госпортал на %d юрлиц — письмо уйдёт в общую канцелярию' % n
            свод['запрет_госпортал'] += 1
        elif д not in FREEMAIL and n >= ПОРОГ_ОБЩЕГО:
            уровень = 'осторожно'
            причина = ('общий домен на %d юрлиц — группа компаний или справочник, '
                       'адресата проверить' % n)
            свод['осторожно_общий'] += 1
        if not уровень:
            continue
        решения.append((д, уровень, причина, n))
        сп = примеры.setdefault(уровень, [])
        if len(сп) < 6:
            сп.append({'домен': д, 'юрлиц': n, 'почему': причина[:60]})
    if применять:
        c = sqlite3.connect(BD, timeout=90)
        c.execute(СХЕМА)
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        for д, у, п, n in решения:
            c.execute('INSERT OR REPLACE INTO domeny_negodnye'
                      '(domen, uroven, prichina, yurlic, ts) VALUES(?,?,?,?,?)',
                      (д, у, п, n, ts))
        c.commit()
        c.close()
        свод['записано'] = len(решения)
    свод['примеры'] = примеры
    return свод


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    и = разбор('--primenit' in sys.argv)
    прим = и.pop('примеры', {})
    print(json.dumps({'примеры': прим}, ensure_ascii=False, indent=1))
    print(json.dumps(и, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
