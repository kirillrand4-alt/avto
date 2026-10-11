# -*- coding: utf-8 -*-
r"""Дообход страниц контактов, которые обход пропустил (владелец 11.10: «может, не на все страницы заходим, где
могут быть почты»). Замер: у 1663 компаний сайт открылся, а почт нет; у 325 из них на сайте есть ссылки на
«Контакты/Реквизиты/Структуру/Руководство», куда обход не заходил (лимит 12 первых ссылок главной — подвал отрезан,
.рф-ссылки в punycode, относительные ссылки после <base href>).

Компании с открывшимся сайтом и без почт: ссылки со страниц из кэша (с учётом <base href>, IDN), до 3 непосещённых
страниц на компанию по приоритету (контакты > реквизиты > руководство/структура > о компании > закупки); вакансии,
вход, новости, каталог — мимо. Скачивание — meyer_nalichie.скачать (запасные адреса). Из страниц — почты
(kc_pochty.почты + pochty_izvlech.найти) и номера (telefony_izvlech). Новое — строкой в <набор>-kontakty.jsonl (копия
последней записи + новые контакты без роли: роль — kc_dorazmetka, «чей» — kc_audit), прочие — отметкой в
<набор>-doobhod-sdelano.txt. Стоп — при старте шагов после агентов.
"""
import html as H
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_kontakty as KK  # noqa: E402
import kc_pochty as KP  # noqa: E402
import kc_zakupki_dobor as KZ  # noqa: E402
import meyer_nalichie as MN  # noqa: E402
import pochty_izvlech as PI  # noqa: E402
import telefony_izvlech as TI  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'pilot')
ВЫХОД = os.path.join(DIR, НАБОР + '-kontakty.jsonl')
СДЕЛАНО = os.path.join(DIR, НАБОР + '-doobhod-sdelano.txt')
ПРИОРИТЕТ = [re.compile(x, re.I) for x in (
    r'kontakt|contact|svyaz|контакт|связ', r'rekvizit|requisit|реквизит|kartochka|карточк', r'rukovod|руковод|struktur|структур|'
    r'komand|команд|personal|сотрудник|direkc|дирекц|administr', r'o-kompanii|about|o-nas|o_kompanii|о-компании|о компании|о нас|'
    r'company', r'zakup|закуп|snab|снабж|tender|тендер')]
МИМО = re.compile(r'vakans|вакан|career|kariera|feedback|obratn|forgot|auth|login|register|basket|cart|korzin|news|novost|'
                  r'новост|blog|catalog|katalog|product|tovar|route=|\{\{|\.(pdf|docx?|xlsx?|jpe?g|png|gif|zip|rar)$', re.I)
_лок = threading.Lock()


def дом(u):
    try:
        h = urllib.parse.urlsplit(u).hostname or ''
        h = h.encode('ascii').decode('idna') if 'xn--' in h else h
    except Exception:  # noqa: BLE001
        h = ''
    return re.sub(r'^www\.', '', h.lower())


def норм(u):
    return re.sub(r'/+$', '', re.sub(r'^https?://(www\.)?', '', urllib.parse.unquote(u or '').lower()))


def кандидаты(з, стр):
    сайт_д = дом(з['сайт']) or MN.домен(з['сайт'])
    были = {норм(x.get('url')) for x in стр} | {норм(u) for u, _ in з.get('страницы') or []}
    найдено = {}
    for x in стр[:8]:
        h = x.get('html') or ''
        база = re.search(r'(?i)<base[^>]+href=["\']([^"\']+)', h)
        осн = база.group(1) if база else x.get('url') or ''
        if not re.match(r'(?i)https?://', осн):  # 2-08: «//xn--…/about» при адресе без схемы — «unknown url type»
            осн = 'http://' + осн.lstrip('/')
        for м in re.finditer(r'(?is)<a\b[^>]*?href\s*=\s*["\']?([^"\'\s>]+)[^>]*>(.*?)</a>', h):
            href, текст = H.unescape(м.group(1)), re.sub(r'<[^>]+>', ' ', м.group(2))[:80]
            if href.startswith(('mailto:', 'tel:', 'javascript:', '#')):
                continue
            u = urllib.parse.urljoin(осн, href).split('#')[0]
            if дом(u).endswith('tilda.ws') and дом(u) != сайт_д:  # 2-08: меню на техническом домене Tilda — свой хост
                u = urllib.parse.urlunsplit(urllib.parse.urlsplit(з['сайт'] if з['сайт'].startswith('http') else
                                                                  'https://' + з['сайт'])[:2] + urllib.parse.urlsplit(u)[2:])
            if дом(u) != сайт_д or норм(u) in были or МИМО.search(urllib.parse.unquote(u)):
                continue
            for k, rx in enumerate(ПРИОРИТЕТ):
                if rx.search(urllib.parse.unquote(u)) or rx.search(текст):
                    if норм(u) not in найдено or найдено[норм(u)][0] > k:
                        найдено[норм(u)] = (k, u)
                    break
    return [u for _, u in sorted(найдено.values())][:3]


def одна(з):
    стр = KK.прочитать_кэш(з['inn']).get('pages') or []
    урлы = кандидаты(з, стр)
    есть_п = {(н.get('почта') or '').lower() for н in з.get('номера') or [] if н.get('почта')}
    есть_н = {re.sub(r'\D', '', н.get('номер') or '')[-10:] + '|' + (н.get('доб') or '') for н in з.get('номера') or [] if н.get('номер')}
    нов, страницы = {}, []
    for u in урлы:
        ст, html, _ = MN.скачать(u)
        страницы.append([u, 'дообход: ' + ст])
        if ст != 'ok':
            continue
        try:  # 2-08: страницы дообхода — и в кэш (повторное извлечение, паспорт, ревизии их видят)
            KK.в_кэш(з['inn'], {u: html}, сайт=з.get('сайт') or '')
        except Exception:  # noqa: BLE001
            pass
        html = KK.без_длинного(html)
        текст = KK.MP.в_текст(html) + KK.json_текст(html)
        for x in KP.почты(html, текст):
            e = x['почта'].lower()
            if e not in есть_п and e not in нов:
                нов[e] = {'почта': e, 'доб': '', 'страницы': [u], 'контекст': x.get('контекст') or '', 'фио': '', 'должность': '',
                          'дообход': 1}
        for e, как, поз in PI.найти(html):
            if e not in есть_п and e not in нов:
                нов[e] = {'почта': e, 'доб': '', 'страницы': [u], 'контекст': PI.видимый(html[max(0, (поз if поз >= 0 else 0) - 4000):max(поз, 0)])[-220:],
                          'фио': '', 'должность': '', 'дообход': 1, 'доизвлечена': как}
        for номер, доб, поз in TI.извлечь_номера(текст):
            ключ = re.sub(r'\D', '', номер)[-10:] + '|' + доб
            if ключ not in есть_н and номер + доб not in нов:
                нов[номер + доб] = {'номер': номер, 'доб': доб, 'страницы': [u], 'фио': '', 'должность': '', 'дообход': 1,
                                   'контекст': re.sub(r'\s+', ' ', текст[max(0, поз - 200):поз + len(номер) + 60])}
    return list(нов.values())[:40], страницы, урлы


def main():
    последняя = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn'):
            последняя[з['inn']] = з
    сделано = set(io.open(СДЕЛАНО, encoding='utf-8').read().split()) if os.path.exists(СДЕЛАНО) else set()
    КОНТ = re.compile(r'kontakt|contact|контакт|svyaz|связ', re.I)

    def мало_страниц(з):
        """2-08: дообход брал только компании без почт — 142 из 158 с необойдённой «Контакты» отсеялись (info@ с главной).
        Теперь: своих страниц ≤2 или среди обойдённых нет страницы контактов — независимо от почт."""
        свои = [u for u, ст in з.get('страницы') or [] if ст in ('ok', 'кэш')]
        return len(свои) <= 2 or not any(КОНТ.search(urllib.parse.unquote(u)) for u in свои)
    # 11.10: KC_TOLKO_INN=<файл со списком ИНН> — только эти компании, отметки «сделано» по ИНН не в счёт (хвост: компании,
    # обойдённые заново по новому сайту, — их прежние отметки относятся к старому сайту)
    if os.environ.get('KC_TOLKO_INN'):
        только = set(io.open(os.environ['KC_TOLKO_INN'], encoding='utf-8').read().split())
        сделано = set()
    else:
        только = None
    задачи = [з for з in последняя.values() if з.get('итог') == 'ok' and з.get('сайт') and not з.get('дообход')
              and з['inn'] not in сделано and (только is None or з['inn'] in только) and any(ст in ('ok', 'кэш') for _, ст in з.get('страницы') or [])
              and (not any(н.get('почта') for н in з.get('номера') or []) or мало_страниц(з))]
    print('компаний без почт с открывшимся сайтом', len(задачи), flush=True)
    сч = {'страниц': 0, 'компаний_с_новыми': 0, 'новых_почт': 0, 'новых_номеров': 0}
    t0, t0_iso, стоп = time.time(), time.strftime('%Y-%m-%dT%H:%M:%S'), [False, time.time()]
    n = [0]

    def шаг(з):
        if стоп[0]:
            return
        try:
            нов, страницы, урлы = одна(з)
        except Exception as e:  # noqa: BLE001
            print('сбой', з['inn'], repr(e)[:100], flush=True)
            return
        with _лок:
            сч['страниц'] += len(урлы)
            if нов:
                сч['компаний_с_новыми'] += 1
                сч['новых_почт'] += sum(1 for x in нов if x.get('почта'))
                сч['новых_номеров'] += sum(1 for x in нов if x.get('номер'))
                with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(dict(з, номера=(з.get('номера') or []) + нов, страницы=(з.get('страницы') or []) + страницы,
                                            дообход=time.strftime('%Y-%m-%d %H:%M')), ensure_ascii=False) + '\n')
                    f.flush()
                    os.fsync(f.fileno())
            else:
                with io.open(СДЕЛАНО, 'a', encoding='utf-8') as f:
                    f.write(з['inn'] + '\n')
                    f.flush()
                    os.fsync(f.fileno())
            n[0] += 1
            if n[0] % 100 == 0:
                print('готово %d/%d' % (n[0], len(задачи)), json.dumps(сч, ensure_ascii=False), flush=True)
                if KZ.пора_стоп(t0_iso):
                    стоп[0] = True
                    print('оркестратор начал шаги после агентов — стоп', flush=True)

    with ThreadPoolExecutor(int(os.environ.get('KC_DOOBHOD_POTOKOV', '16'))) as ex:
        list(ex.map(шаг, задачи))
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    сч['минут'] = round((time.time() - t0) / 60, 1)
    print('===ИТОГ===')
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
