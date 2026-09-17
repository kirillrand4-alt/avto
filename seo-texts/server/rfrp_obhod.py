# -*- coding: utf-8 -*-
r"""Обход всех региональных фондов вторым уровнем: что реально лежит в реестрах.

Задача владельца: не обещать «найдётся у 20-40 фондов», а показать результат.
Поэтому скрипт не оценивает, а собирает: заходит на каждый сайт, ищет разделы
про получателей поддержки и профинансированные проекты (по тексту ссылок, по
адресам и по типовым путям), открывает их и вытаскивает то, что видно —
компании, ИНН, суммы, ссылки на файлы.

Durable: результат пишется в rfrp_obhod.jsonl (fsync) и в CSV, копия на дроп.
Печатается сводка ПОСЛЕДНЕЙ строкой — раннер режет stdout сверху.
"""
import csv
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))

СЛОВА = re.compile(
    r'получател\w*|реестр|сведения\s+о\s+получ|профинансирован|поддержанн\w+\s+проект|'
    r'реализованн\w+\s+проект|портфель|выданн\w+\s+займ|наши\s+проект|проекты\s+фонда|'
    r'раскрыти\w+\s+информац|отчетност|отчётност', re.I)
ПУТИ = ('/raskrytie-informatsii/', '/disclosure/', '/reestr/', '/reestr',
        '/proekty/', '/projects/', '/project', '/o-fonde/', '/documents/',
        '/dokumenty/', '/otchetnost/', '/podderzhka/')
ССЫЛКА = re.compile(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.{0,120}?)</a>', re.S | re.I)
ФАЙЛ = re.compile(r'\.(xlsx|xls|csv)(\?|$)', re.I)
КОМПАНИЯ = re.compile(r'(?:ООО|АО|ПАО|ЗАО|НАО)\s*[«"][^»"<>]{3,60}[»"]')
ИНН = re.compile(r'\b(\d{10}|\d{12})\b')
СУММА = re.compile(r'\d{1,4}[,.]?\d*\s*(?:млн|млрд)')

# Лексика профиля — считаем, сколько из найденного вообще про наши рынки.
КЦ = ('металл', 'машиностро', 'станк', 'нефт', 'газ', 'хим', 'полимер', 'пластик',
      'резин', 'цемент', 'кирпич', 'бетон', 'стекл', 'деревообраб', 'фанер', 'бумаг',
      'литей', 'прокат', 'кабел', 'электрод', 'судостро', 'вагон', 'приборостро',
      'фармац', 'лакокрас', 'удобрен', 'компрессор', 'оборудован', 'производств')
MEYER = ('зерн', 'элеватор', 'семен', 'комбикорм', 'мукомол', 'крупян', 'масличн',
         'пищев', 'молок', 'мясо', 'консерв', 'кондитер', 'хлеб', 'овощ', 'ягод',
         'орех', 'рыб', 'сортиров', 'фасов', 'упаковк')


def взять(url, лимит=400000, tmo=20):
    try:
        r = НП.open(urllib.request.Request(url, headers=H), timeout=tmo)
        сырое = r.read(лимит)
        тип = r.headers.get('Content-Type', '')
        return r.getcode(), тип, сырое
    except urllib.error.HTTPError as e:
        return e.code, '', b''
    except Exception:
        return -1, '', b''


def текстом(сырое):
    т = сырое.decode('utf-8', 'replace')
    if 'charset=windows-1251' in т[:900].lower() or 'charset=cp1251' in т[:900].lower():
        т = сырое.decode('cp1251', 'replace')
    ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', т, flags=re.S)
    ч = re.sub(r'<[^>]+>', ' ', ч)
    return т, re.sub(r'\s+', ' ', ч)


def оценить(url, html, чистый):
    компании = sorted({re.sub(r'\s+', ' ', m).strip() for m in КОМПАНИЯ.findall(чистый)})
    инны = sorted({m for m in ИНН.findall(чистый)})
    суммы = СУММА.findall(чистый)
    файлы = sorted({urllib.parse.urljoin(url, m) for m in
                    re.findall(r'href=["\']([^"\']+)["\']', html, re.I) if ФАЙЛ.search(m)})
    низ = чистый.lower()
    return {'url': url, 'компаний': len(компании), 'ИНН': len(инны),
            'сумм': len(суммы), 'таблица': '<table' in html.lower(),
            'файлов': файлы[:4], 'примеры': компании[:6], 'инн_примеры': инны[:6],
            'профиль_кц': sum(1 for k in КЦ if k in низ),
            'профиль_meyer': sum(1 for k in MEYER if k in низ)}


def фонд(домен):
    зап = {'домен': домен, 'страницы': []}
    код, тип, сырое = взять('https://' + домен + '/')
    зап['код_главной'] = код
    кандидаты = []
    if код == 200 and сырое:
        html, чистый = текстом(сырое)
        for href, текст in ССЫЛКА.findall(html):
            подпись = re.sub(r'<[^>]+>|\s+', ' ', текст).strip()
            цель = urllib.parse.urljoin('https://' + домен + '/', href)
            if not цель.startswith('http'):
                continue
            if urllib.parse.urlparse(цель).netloc.replace('www.', '') != домен.replace('www.', ''):
                continue
            if СЛОВА.search(подпись) or СЛОВА.search(urllib.parse.unquote(href)):
                кандидаты.append(цель)
    for п in ПУТИ:
        кандидаты.append('https://' + домен + п)
    видели, лучшие = set(), []
    for цель in кандидаты:
        if цель in видели or len(видели) >= 10:
            continue
        видели.add(цель)
        к, тип, сырое = взять(цель)
        if к != 200 or not сырое:
            continue
        if 'html' not in (тип or 'html').lower():
            continue
        html, чистый = текстом(сырое)
        оц = оценить(цель, html, чистый)
        if оц['компаний'] >= 3 or оц['ИНН'] >= 3 or оц['файлов']:
            лучшие.append(оц)
    лучшие.sort(key=lambda x: (x['компаний'] + x['ИНН'], len(x['файлов'])), reverse=True)
    зап['страницы'] = лучшие[:3]
    return зап


def main():
    код, тип, сырое = взять('https://frprf.ru/zaymy-regfondy/proekty-razvitiya-s-rfrp/')
    html = сырое.decode('utf-8', 'replace')
    домены = sorted({m for m in re.findall(r'https?://([a-z0-9.\-]+\.(?:ru|рф))/', html)
                     if 'frprf' not in m and 'gov.ru' not in m and 'yandex' not in m})
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=12) as ex:
        итоги = list(ex.map(фонд, домены))

    путь = os.path.join(DIR, 'rfrp_obhod.jsonl')
    with io.open(путь, 'w', encoding='utf-8') as f:
        for з in итоги:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())

    строки = []
    for з in итоги:
        for с in з['страницы']:
            строки.append({
                'фонд': з['домен'], 'страница': с['url'], 'компаний': с['компаний'],
                'ИНН': с['ИНН'], 'сумм': с['сумм'], 'таблица': 'да' if с['таблица'] else '',
                'файлы': ' | '.join(с['файлов'][:2]),
                'профиль_кц': с['профиль_кц'], 'профиль_meyer': с['профиль_meyer'],
                'примеры_компаний': ' | '.join(с['примеры'][:4]),
                'примеры_ИНН': ' '.join(с['инн_примеры'][:4]),
            })
    csv_путь = os.path.join(DIR, 'rfrp_obhod.csv')
    if строки:
        with io.open(csv_путь, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(строки[0].keys()), delimiter=';')
            w.writeheader()
            w.writerows(строки)
            f.flush()
            os.fsync(f.fileno())
        try:
            import shutil
            shutil.copyfile(csv_путь, os.path.join(r'C:\seostat\drop\drop-storage',
                                                   'rfrp_obhod.csv'))
        except Exception:  # noqa: BLE001
            pass

    с_данными = [з for з in итоги if з['страницы']]
    всего_компаний = sum(с['компаний'] for з in итоги for с in з['страницы'])
    всего_инн = sum(с['ИНН'] for з in итоги for с in з['страницы'])
    с_файлами = [з for з in итоги if any(с['файлов'] for с in з['страницы'])]
    сводка = {
        'фондов': len(домены),
        'ответили': sum(1 for з in итоги if з['код_главной'] == 200),
        'с_данными': len(с_данными),
        'из_них_с_файлами_xls': len(с_файлами),
        'компаний_видно_суммарно': всего_компаний,
        'ИНН_видно_суммарно': всего_инн,
        'секунд': round(time.time() - t0),
        'топ': [{'фонд': з['домен'], 'компаний': з['страницы'][0]['компаний'],
                 'ИНН': з['страницы'][0]['ИНН'],
                 'url': з['страницы'][0]['url'][:70],
                 'примеры': з['страницы'][0]['примеры'][:3]}
                for з in sorted(с_данными,
                                key=lambda x: x['страницы'][0]['компаний'] + x['страницы'][0]['ИНН'],
                                reverse=True)[:12]],
    }
    print('===СВОДКА===')
    print(json.dumps(сводка, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    sys.exit(main())
