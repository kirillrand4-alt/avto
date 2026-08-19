# -*- coding: utf-8 -*-
r"""Сколько ИНН из 161 799 имеют сайт — по КАЖДОМУ найденному столбцу, и что
из этого ещё не стоит в очереди зенки и не разобрано.

Ревизия столбцов (_sayty_vse_stolbcy.py) показала, что адреса сайтов лежат
не в двух местах, а в тринадцати. Но большинство — это СЛЕДЫ краулинга
(site_facts, site_text, qc_site, email_sources): такой сайт мы уже качали.
Ценность только у тех столбцов, что дают сайт компании, которую ещё не
трогали. Здесь считается именно это: вклад каждого столбца поверх очереди.
"""
import json
import os
import re
import sqlite3

BD = r'C:\sender\enrich.db'
OBZVON = r'C:\sender\obzvon-index.db'
ZENNO = r'C:\seostat\drop\zenno'

ДОМЕН = re.compile(r'([a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:ru|xn--p1ai|com|net|org|su|by|kz|biz|info|pro|shop|store|online|site))', re.I)
ПЛОЩАДКИ = {'tender.pro', 'rusprofile.ru', 'list-org.com', 'sbis.ru', 'zachestnyibiznes.ru',
            'checko.ru', 'e-disclosure.ru', 'vk.com', 'ok.ru', 'facebook.com',
            'instagram.com', 'youtube.com', 'avito.ru', 'yandex.ru', 'google.com',
            'zakupki.gov.ru', 'nalog.ru', 'rbc.ru', 'kartoteka.ru', 'audit-it.ru',
            'seldon.ru', 'sbis.com', 'tenderguru.ru', 'b2b-center.ru', 'flamp.ru',
            'yell.ru', 'orgpage.ru', '2gis.ru', 'spark-interfax.ru', 'prom.ua'}


def дом(v):
    s = str(v or '').lower()
    m = ДОМЕН.search(s)
    if not m:
        return ''
    d = m.group(1).strip('.')
    if d.startswith('www.'):
        d = d[4:]
    if d in ПЛОЩАДКИ or d.split('.')[-2:] == ['gov', 'ru']:
        return ''
    return d


def инн(v):
    return ''.join(ch for ch in str(v or '') if ch.isdigit())


def собрать(путь, запросы):
    """запросы: список (метка, sql) -> метка -> {инн: домен}"""
    из = {}
    if not os.path.exists(путь):
        return из
    c = sqlite3.connect('file:%s?mode=ro' % путь.replace('\\', '/'), uri=True)
    for метка, sql in запросы:
        d = {}
        try:
            for i, v in c.execute(sql):
                n, dm = инн(i), дом(v)
                if n and dm:
                    d.setdefault(n, dm)
        except Exception as e:  # noqa: BLE001
            d = {'ошибка': str(e)[:120]}
        из[метка] = d
    c.close()
    return из


def главное():
    из_e = собрать(BD, [
        ('enrich.companies.site', "select inn, site from companies where coalesce(site,'')<>''"),
        ('enrich.email_class.site_domain', "select inn, site_domain from email_class where coalesce(site_domain,'')<>''"),
        ('enrich.email_class.domain', "select inn, domain from email_class where coalesce(domain,'')<>''"),
        ('enrich.site_facts.site', "select inn, site from site_facts where coalesce(site,'')<>''"),
        ('enrich.site_text.url', "select inn, url from site_text where coalesce(url,'')<>''"),
        ('enrich.qc_site.url', "select inn, url from qc_site where coalesce(url,'')<>''"),
        ('enrich.email_sources.url', "select inn, url from email_sources where coalesce(url,'')<>''"),
        ('enrich.imena.dokazatelstvo', "select inn, dokazatelstvo from imena where coalesce(dokazatelstvo,'')<>''"),
        ('enrich.emails.домен', "select inn, email from emails where coalesce(email,'')<>''"),
    ])
    из_o = собрать(OBZVON, [
        ('obzvon.sites', "select inn, sites from obzvon where coalesce(sites,'')<>''"),
        ('obzvon.emails_base.домен', "select inn, emails_base from obzvon where coalesce(emails_base,'')<>''"),
        ('obzvon.emails_site.домен', "select inn, emails_site from obzvon where coalesce(emails_site,'')<>''"),
    ])
    все = {}
    все.update(из_e)
    все.update(из_o)

    # что уже в работе
    в_очереди, разобрано = set(), set()
    for имя in ('ochered.txt', 'otdano.txt', 'ne_otkrylis.txt'):
        оч = os.path.join(ZENNO, имя)
        if not os.path.exists(оч):
            continue
        with open(оч, encoding='utf-8-sig', errors='replace') as f:
            for s in f:
                ч = s.strip().split(';')
                if ч and ч[0].strip().isdigit():
                    в_очереди.add(ч[0].strip())
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    for (i,) in c.execute('select distinct inn from site_facts'):
        разобрано.add(инн(i))
    for (i,) in c.execute('select distinct inn from site_text'):
        разобрано.add(инн(i))
    c.close()
    в_работе = в_очереди | разобрано

    свод, накопом = {}, set()
    for метка, d in все.items():
        if 'ошибка' in d:
            свод[метка] = d
            continue
        свои = set(d)
        свод[метка] = {
            'инн_с_сайтом': len(свои),
            'не_в_работе': len(свои - в_работе),
            'нового_сверх_предыдущих': len(свои - в_работе - накопом),
        }
        накопом |= (свои - в_работе)

    все_инн = set()
    o = sqlite3.connect('file:%s?mode=ro' % OBZVON.replace('\\', '/'), uri=True)
    for (i,) in o.execute('select inn from obzvon'):
        n = инн(i)
        if n:
            все_инн.add(n)
    o.close()

    покрыто = set()
    for d in все.values():
        if 'ошибка' not in d:
            покрыто |= set(d)

    print(json.dumps({
        'ИТОГ': {
            'юрлиц_в_базе': len(все_инн),
            'есть_хоть_какой_сайт': len(покрыто),
            'уже_в_очереди_или_разобрано': len(в_работе),
            'НЕ_В_РАБОТЕ_можно_добавить': len(покрыто - в_работе),
            'сайта_нет_нигде': len(все_инн - покрыто),
        },
        'по_столбцам': свод,
    }, ensure_ascii=False, indent=1))


главное()
