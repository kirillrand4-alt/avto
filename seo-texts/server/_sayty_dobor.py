# -*- coding: utf-8 -*-
r"""Добор очереди зенки: всё, что осталось после первой заливки, по ВСЕЙ базе.

Владелец: «и сайты ты по всем столбцам смотрел? по всем 160к+». Смотрел не по
всем — первая заливка брала companies.site/cand_site и obzvon.sites. Ревизия
столбцов нашла ещё пять мест, где адрес сайта лежит в связке с ИНН:

  email_class.site_domain / domain    домен, уже сопоставленный компании;
  imena.dokazatelstvo                 страница, где нашли ЛПР (часто чужая);
  qc_site.url, email_sources.url      следы прошлых обходов;
  домены из адресов почты             obzvon.emails_base / emails_site / enrich.emails.

Последний источник и даёт основной остаток — 44 тысячи ИНН. Но домен из почты
сайтом является не всегда: mail.ru сайтом «Ромашки» не станет. Поэтому здесь
каждый кандидат проходит разбор, и в очередь идёт только то, что похоже на
собственный сайт компании.

    python _sayty_dobor.py             посчитать и показать примеры
    python _sayty_dobor.py --pisat [N] дописать в очередь
"""
import json
import os
import re
import sqlite3
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
OBZVON = r'C:\sender\obzvon-index.db'
OCHERED = os.path.join(ZENNO, 'ochered.txt')
OTDANO = os.path.join(ZENNO, 'otdano.txt')

ДОМЕН = re.compile(
    r'([a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:ru|su|com|net|org|by|kz|biz|info|pro|shop|store|online|site|tech|group|company|moscow|spb\.ru))\b',
    re.I)
ЭДО = re.compile(r'(^|\.)(tensor|sbis|kontur|diadoc|taxcom|astral|edo|nalog|1cfresh|kaluga-astral)\.', re.I)
ГОСПОРТАЛ = re.compile(
    r'(^|\.)(gov\d*|mos|gosuslugi|admin|adm|mil|minzdrav|mchs|mvd)\.(ru|su)$'
    r'|(^|\.)gov\d*\.', re.I)
ВИТРИНА = re.compile(
    r'(^|\.)(pulscen|tiu|satom|blizko|flagma|all|propartner|rabota|hh|zoon|yell|'
    r'orgpage|spr|bizorg|regmarkets|prom|deal|b2b-center|skrin|licexpert|'
    r'rusprofile|list-org|zachestnyibiznes|checko|sbis|audit-it|kartoteka|'
    r'promportal|trudvsem|rosminzdrav|kommersant|rbc|ria|tass|interfax|'
    r'licexpert|gisp|torgi|roseltorg|etp-ets)\.'
    r'(ru|su|biz|com|net|org)$', re.I)
СОЦСЕТЬ = {'youtube.com', 'vk.com', 'ok.ru', 'facebook.com', 'instagram.com',
           't.me', 'telegram.me', 'twitter.com', 'zen.yandex.ru', 'dzen.ru',
           'avito.ru', 'drom.ru', 'auto.ru', 'wildberries.ru', 'ozon.ru'}
ХОСТИНГ = re.compile(
    r'(^|\.)(narod|ucoz|wix|tilda|tildacdn|nethouse|jimdo|a5\.ru|bitrix24|wixsite|ru\.com)\.', re.I)
FREEMAIL = {
    'mail.ru', 'inbox.ru', 'bk.ru', 'list.ru', 'internet.ru', 'yandex.ru', 'ya.ru',
    'yandex.com', 'gmail.com', 'googlemail.com', 'rambler.ru', 'lenta.ru', 'ro.ru',
    'autorambler.ru', 'myrambler.ru', 'rambler.ua', 'mail.ua', 'ukr.net', 'i.ua',
    'meta.ua', 'bigmir.net', 'qip.ru', 'pochta.ru', 'pisem.net', 'nm.ru', 'hotbox.ru',
    'front.ru', 'krovatka.su', 'newmail.ru', 'orc.ru', 'smtp.ru', 'land.ru',
    'mail.com', 'outlook.com', 'hotmail.com', 'live.com', 'msn.com', 'yahoo.com',
    'icloud.com', 'me.com', 'mac.com', 'aol.com', 'proton.me', 'protonmail.com',
    'gmx.de', 'web.de', 'bk.com', 'vk.com', 'ok.ru', 'narod.ru', 'mail.kz',
    'tut.by', 'tut.by.ru', 'yandex.by', 'yandex.kz', 'yandex.ua', 'sibmail.com',
    'nxt.ru', 'bossmail.ru', 'mail.ru.com',
}
# опечатки в бесплатной почте: домен не существует, качать нечего
ОПЕЧАТКИ = re.compile(
    r'^(m+a+i+l+|мail|maii|nail|mial|mai|mali|malii|maill|gmai|gmial|gmal|gamil|'
    r'yandeks|yandes|yadex|yandx|ynadex|iandex|ramler|rambeler|bck|inbx|lst)\.'
    r'(ru|com|ry|ri|rи|u|r|cm|co|om|net)$', re.I)


def дом(v):
    s = str(v or '').lower().replace('\\', '/')
    s = re.sub(r'^https?://', '', s).split('/')[0]
    if '@' in s:
        s = s.split('@')[-1]
    m = ДОМЕН.search(s)
    if not m:
        return ''
    d = m.group(1).strip('.')
    return d[4:] if d.startswith('www.') else d


def инн(v):
    return ''.join(ch for ch in str(v or '') if ch.isdigit())


def _мерки():
    свой, площадка = (lambda u: True), (lambda u: '')
    try:
        import enrich_contacts as _E
        свой = _E._is_own_site
    except Exception:  # noqa: BLE001
        pass
    try:
        import ploshchadki as _PL
        площадка = _PL.из_списка
    except Exception:  # noqa: BLE001
        pass
    return свой, площадка


def негодные_домены():
    """Справочник domeny_negodnye: домен -> уровень (запрет/осторожно)."""
    из = {}
    try:
        c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
        for д, ур in c.execute('select domen, uroven from domeny_negodnye'):
            из[str(д).lower()] = str(ур)
        c.close()
    except Exception:  # noqa: BLE001
        pass
    return из


def разбор(д, свой, площадка, спрв=None, из_почты=False):
    """Почему домен не годится в очередь — или пусто, если годится."""
    if д in FREEMAIL:
        return 'бесплатная_почта'
    if д in СОЦСЕТЬ:
        return 'соцсеть_маркетплейс'
    if ВИТРИНА.search(д):
        return 'витрина_справочник'
    ур = (спрв or {}).get(д, '')
    if ур == 'запрет':
        return 'справочник_запрет'
    if ур == 'осторожно' and из_почты:
        # домен на 5+ юрлиц, а «сайтом» он стал только потому, что там почта:
        # это либо группа компаний, либо провайдер — обходить по разу, не 83 раза
        return 'общий_домен_из_почты'
    if ОПЕЧАТКИ.match(д):
        return 'опечатка_в_почте'
    if ЭДО.search(д + '.'):
        return 'сервис_эдо'
    if ГОСПОРТАЛ.search(д):
        return 'госпортал'
    if ХОСТИНГ.search(д + '.'):
        return 'конструктор_хостинг'
    if площадка(д):
        return 'площадка'
    if not свой('http://' + д):
        return 'не_свой_сайт'
    return ''


def в_работе():
    было = set()
    for имя in ('ochered.txt', 'otdano.txt'):
        p = os.path.join(ZENNO, имя)
        if os.path.exists(p):
            with open(p, encoding='utf-8-sig', errors='replace') as f:
                for s in f:
                    ч = s.strip().split(';')
                    if ч and ч[0].strip().isdigit():
                        было.add(ч[0].strip())
    if os.path.isdir(KESH):
        для = {n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')}
        было |= {x for x in для if x.isdigit()}
    return было


def кандидаты():
    """ИНН -> (домен, откуда). Порядок источников = порядок доверия."""
    из = {}

    def влить(метка, пары):
        for i, v in пары:
            n, d = инн(i), дом(v)
            if n and d and n not in из:
                из[n] = (d, метка)

    e = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    влить('companies.site', e.execute(
        "select inn, site from companies where coalesce(site,'')<>''"))
    влить('email_class.site_domain', e.execute(
        "select inn, site_domain from email_class where coalesce(site_domain,'')<>''"))
    влить('email_class.domain', e.execute(
        "select inn, domain from email_class where coalesce(domain,'')<>''"))
    влить('qc_site.url', e.execute(
        "select inn, url from qc_site where coalesce(url,'')<>''"))
    влить('email_sources.url', e.execute(
        "select inn, url from email_sources where coalesce(url,'')<>''"))
    влить('imena.dokazatelstvo', e.execute(
        "select inn, dokazatelstvo from imena where coalesce(dokazatelstvo,'')<>''"))
    влить('enrich.emails', e.execute(
        "select inn, email from emails where coalesce(email,'')<>''"))
    e.close()
    if os.path.exists(OBZVON):
        o = sqlite3.connect('file:%s?mode=ro' % OBZVON.replace('\\', '/'), uri=True)
        влить('obzvon.sites', o.execute(
            "select inn, sites from obzvon where coalesce(sites,'')<>''"))
        влить('obzvon.emails_site', o.execute(
            "select inn, emails_site from obzvon where coalesce(emails_site,'')<>''"))
        влить('obzvon.emails_base', o.execute(
            "select inn, emails_base from obzvon where coalesce(emails_base,'')<>''"))
        o.close()
    return из


def главное(писать=False, предел=0):
    свой, площадка = _мерки()
    спрв = негодные_домены()
    было, все = в_работе(), кандидаты()
    ПОЧТОВЫЕ = {'enrich.emails', 'obzvon.emails_base', 'obzvon.emails_site',
                'email_class.domain'}
    видел_домен = {}
    свод = {'кандидатов_всего': len(все), 'уже_в_работе': 0, 'годно': 0}
    причины, откуда, примеры, годные = {}, {}, {}, []
    for n, (д, м) in все.items():
        if n in было:
            свод['уже_в_работе'] += 1
            continue
        поч = разбор(д, свой, площадка, спрв, м in ПОЧТОВЫЕ)
        if not поч and видел_домен.get(д, 0) >= 2:
            # один и тот же сайт третий раз качать незачем — страница та же
            поч = 'домен_уже_взят'
        if поч:
            причины[поч] = причины.get(поч, 0) + 1
            примеры.setdefault(поч, []).append('%s %s' % (n, д))
            continue
        видел_домен[д] = видел_домен.get(д, 0) + 1
        свод['годно'] += 1
        откуда[м] = откуда.get(м, 0) + 1
        примеры.setdefault('годно:' + м, []).append('%s %s' % (n, д))
        годные.append('%s;http://%s;oba' % (n, д))
    свод['отсеяно'] = причины
    свод['годные_по_источнику'] = откуда
    свод['примеры'] = {k: v[:6] for k, v in примеры.items()}

    if писать and годные:
        куски = годные[:предел] if предел else годные
        with open(OCHERED, 'a', encoding='utf-8') as f:
            f.write('\n'.join(куски) + '\n')
            f.flush()
            os.fsync(f.fileno())
        with open(OTDANO, 'a', encoding='utf-8') as f:
            f.write('\n'.join(s.split(';')[0] for s in куски) + '\n')
            f.flush()
            os.fsync(f.fileno())
        свод['ЗАПИСАНО'] = len(куски)
        with open(OCHERED, encoding='utf-8-sig', errors='replace') as f:
            свод['очередь_теперь'] = sum(1 for s in f if s.strip())
    print(json.dumps(свод, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    главное('--pisat' in sys.argv,
            int(sys.argv[sys.argv.index('--pisat') + 1])
            if '--pisat' in sys.argv and len(sys.argv) > sys.argv.index('--pisat') + 1
            and sys.argv[sys.argv.index('--pisat') + 1].isdigit() else 0)
