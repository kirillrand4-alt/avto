# -*- coding: utf-8 -*-
r"""Проверка номеров ЛПР базы Meyer по живой странице-источнику.

Вопрос владельца 05.10: «а свои у тебя правильно записаны?». Для каждого номера:
скачать страницу из «Ссылки на источник», найти номер (в любом написании, в т.ч.
в tel:-ссылке), вырезать фрагмент вокруг и спросить модель (провайдерский API):
чей это номер по тексту, какая должность, совпадает ли с записанной у нас и
та ли это компания.

Вход: C:\sender\server\meyer-proverka-vhod.json (список контактов).
Выход (durable, fsync, резюм по id): C:\sender\server\meyer-proverka.jsonl.
Запуск: python meyer_proverka.py  (detached через _pusk_proverki_meyer.py)
"""
import gzip
import html
import io
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import verify_company as VC  # noqa: E402

ВХОД = os.path.join(DIR, 'meyer-proverka-vhod.json')
ВЫХОД = os.path.join(DIR, 'meyer-proverka.jsonl')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0 Safari/537.36')
КЭШ_ОБХОДА = r'C:\seostat\drop\pagecache'
_лок = threading.Lock()
_кэш = {}
_хосты = {}
_хосты_лок = threading.Lock()
# verify_company ставит глобальный opener через прокси; сначала идём напрямую, прокси — запасной путь
_прямой = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_прямой_без_серт = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))

ПРОМПТ = (
    'Проверяешь контакт в базе продаж. Компания: «{имя}» (ИНН {инн}, сайт {сайт}).\n'
    'У нас записано: номер {номер}{доб} принадлежит: {фио} — {должн}.\n'
    'Страница-источник: {url}\nЗаголовок страницы: {заголовок}\n'
    'Фрагмент страницы вокруг этого номера (номер может быть написан в другом формате):\n'
    '«««{фрагмент}»»»\n\n'
    'Определи ТОЛЬКО по фрагменту:\n'
    '1) есть ли этот номер во фрагменте;\n'
    '2) к кому он относится по тексту: ближайшая подпись — ФИО, должность или отдел. '
    'Учитывай вёрстку: подпись обычно стоит ПЕРЕД номером; номер соседнего человека не '
    'приписывай;\n'
    '3) совпадает ли это с тем, что записано у нас. «верно» — та же должность или тот же '
    'отдел (снабжение = закупки, руководство = директор); «частично» — близко, но не то же '
    '(заместитель вместо директора, отдел вместо руководителя отдела); «неверно» — номер '
    'другого человека/отдела или общий номер/приёмная; «неясно» — по фрагменту не понять;\n'
    '4) о той ли компании страница (или это справочник/сайт другой организации).\n'
    'Ответ — ТОЛЬКО JSON без markdown: {{"есть":true/false,"кому":"ФИО и/или должность/отдел по '
    'тексту","вердикт":"верно|частично|неверно|неясно","компания_та":"да|нет|неясно",'
    '"почему":"до 20 слов"}}')


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def ascii_url(url):
    """Кириллический домен и путь — в IDNA и %-кодировку (urllib иначе падает)."""
    ч = urllib.parse.urlsplit(url)
    хост = ч.hostname.encode('idna').decode('ascii') if ч.hostname else ''
    if ч.port:
        хост += ':%d' % ч.port
    путь = urllib.parse.quote(ч.path, safe='/%:@!$&\'()*+,;=-._~')
    запрос = urllib.parse.quote(ч.query, safe='=&%/:+,;-._~')
    return urllib.parse.urlunsplit((ч.scheme, хост, путь, запрос, ''))


def _открыть(url):
    req = urllib.request.Request(ascii_url(url), headers={
        'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'})
    ошибка = None
    for попытка, opener in enumerate((_прямой, _прямой, _прямой_без_серт, None, None)):
        try:
            if opener is None:
                r = urllib.request.urlopen(req, timeout=30)  # глобальный opener (прокси)
            else:
                r = opener.open(req, timeout=30)
            with r:
                return r.headers.get('Content-Type', ''), r.read(6_000_000)
        except urllib.error.HTTPError as e:
            ошибка = e
            if e.code in (429, 503):
                time.sleep(15 * (попытка + 1))
            elif e.code == 404:
                break
        except Exception as e:  # noqa: BLE001
            ошибка = e
    raise ошибка


def скачать(url):
    if url in _кэш:
        return _кэш[url]
    хост = urllib.parse.urlsplit(url).hostname or ''
    with _хосты_лок:
        лок = _хосты.setdefault(хост, threading.Lock())
    рез = ('', '', '')
    try:
        with лок:  # один хост — по одному запросу, чтобы не ловить 429
            тип, сырое = _открыть(url)
        if 'pdf' in тип.lower() or url.lower().endswith('.pdf'):
            рез = ('pdf', '', '')
        else:
            кодир = 'utf-8'
            м = re.search(r'charset=([\w\-]+)', тип) or re.search(rb'charset=["\']?([\w\-]+)', сырое[:3000])
            if м:
                кодир = м.group(1) if isinstance(м.group(1), str) else м.group(1).decode('ascii', 'ignore')
            try:
                текст = сырое.decode(кодир, errors='replace')
            except LookupError:
                текст = сырое.decode('utf-8', errors='replace')
            з = re.search(r'<title[^>]*>(.*?)</title>', текст, re.S | re.I)
            рез = ('ok', текст, html.unescape(з.group(1)).strip()[:150] if з else '')
    except Exception as e:  # noqa: BLE001
        рез = ('ошибка: ' + repr(e)[:90], '', '')
    _кэш[url] = рез
    return рез


def из_кэша_обхода(inn, цифры):
    """Страницы сайта, сохранённые обходом (pagecache/<ИНН>.json.gz): где стоит номер."""
    п = os.path.join(КЭШ_ОБХОДА, inn + '.json.gz')
    if not os.path.exists(п):
        return None
    try:
        d = json.loads(gzip.open(п).read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return None
    кандидаты = []
    стр = d.get('pages') if isinstance(d, dict) else None
    if isinstance(стр, list):
        for x in стр:
            if isinstance(x, dict):
                тело = x.get('html') or x.get('text') or x.get('body') or ''
                кандидаты.append((x.get('url') or x.get('u') or d.get('site', ''), str(тело)))
            elif isinstance(x, (list, tuple)) and len(x) >= 2:
                кандидаты.append((str(x[0]), str(x[1])))
    elif isinstance(стр, dict):
        кандидаты += [(str(k), str(v)) for k, v in стр.items()]
    if isinstance(d, dict) and d.get('text'):
        кандидаты.append((d.get('site', '') + ' (текст обхода)', str(d['text'])))
    for url, тело in кандидаты:
        текст = в_текст(тело) if '<' in тело else тело
        if найти(текст, цифры):
            return url, текст, d.get('ts', '')
    return None


def в_текст(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?i)<a[^>]+href=["\']tel:([^"\']+)["\'][^>]*>', r' [tel:\1] ', h)
    h = re.sub(r'(?i)<br\s*/?>|</(p|div|li|tr|td|h\d)>', '\n', h)
    h = re.sub(r'<[^>]+>', ' ', h)
    h = html.unescape(h)
    h = re.sub(r'[ \t\u00a0]+', ' ', h)
    return re.sub(r'\s*\n\s*', '\n', h)


def найти(текст, цифры):
    # «89878645759» — номер слитно с 8/7: префикс необязателен, но цифрой перед ним быть нельзя
    шаблон = (r'(?<!\d)(?:\+?[78][\s\-\(\)\.\u00a0]{0,3})?'
              + r'[\s\-\(\)\.\u00a0]{0,3}'.join(цифры) + r'(?!\d)')
    return [м.start() for м in re.finditer(шаблон, текст)]


def проверить(к):
    цифры = re.sub(r'\D', '', к['номер'])[-10:]
    статус, сырое, заголовок = скачать(к['url'])
    з = {'id': к['id'], 'inn': к['inn'], 'номер': к['номер'], 'url': к['url'], 'страница': статус,
         'заголовок': заголовок}
    текст = в_текст(сырое) if статус == 'ok' else ''
    поз = найти(текст, цифры) if текст else []
    з['найден_раз'] = len(поз) if статус == 'ok' else -1
    if not поз:
        # живой страницы нет или номера на ней уже нет — смотрим, что видел обход
        к_обх = из_кэша_обхода(к['inn'], цифры)
        if not к_обх:
            записать(з)
            return
        з['проверено_по'] = 'кэш обхода %s: %s' % (к_обх[2][:10], к_обх[0][:120])
        текст = к_обх[1]
        поз = найти(текст, цифры)
    фрагменты = []
    for п in поз[:3]:
        фрагменты.append(текст[max(0, п - 450):п + 250])
    фрагмент = '\n…\n'.join(фрагменты)[:2400]
    з['доб_на_странице'] = (bool(к['доб']) and bool(re.search(r'(доб|вн|ext)\D{0,4}' + к['доб'], фрагмент, re.I)))
    промпт = ПРОМПТ.format(имя=к['имя'], инн=к['inn'], сайт=к['сайт'] or '—', номер=к['номер'],
                           доб=(' доб. ' + к['доб']) if к['доб'] else '', фио=к['фио'] or '(ФИО нет)',
                           должн=к['должность'], url=к['url'], заголовок=заголовок or '—',
                           фрагмент=фрагмент)
    for попытка in range(3):
        try:
            out = VC._provider_call_stdlib(промпт)
            м = re.search(r'\{.*\}', out or '', re.S)
            з.update(json.loads(м.group(0)))
            break
        except Exception as e:  # noqa: BLE001
            з['ошибка_модели'] = repr(e)[:90]
            time.sleep(5 * (попытка + 1))
    з['фрагмент'] = фрагмент[:900]
    записать(з)


def main():
    вход = json.load(io.open(ВХОД, encoding='utf-8'))
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                if 'вердикт' in з:
                    сделано.add(з['id'])
            except ValueError:
                pass
    очередь = [к for к in вход if к['id'] not in сделано]
    print('всего', len(вход), 'осталось', len(очередь), flush=True)
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(проверить, очередь))
    print('готово', flush=True)


if __name__ == '__main__':
    main()
