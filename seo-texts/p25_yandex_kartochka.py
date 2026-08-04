# -*- coding: utf-8 -*-
"""Карточка организации Яндекса: сайт, адрес и телефон предприятия. Канал, которого у нас не было.

ВОПРОС ВЛАДЕЛЬЦА: «карточки, которые справа даются, — получаются?» Ответ был «нет», и он
подтверждён разбором ответа поиска: xmlriver отдаёт нам ТОЛЬКО домен (`site_source: xmlriver`),
после чего сервер краулит сам сайт. Карточка организации не приходит ни в каком виде.

ЧТО ОНА ДАЁТ СВЕРХ УЖЕ ИМЕЮЩЕГОСЯ. Замер на АО «Апатит» (место 3 по сумме, 125,6 млн):

    поиск сайта нашёл           phosagro.ru        и судья пометил «ЧУЖОЙ» — юрлицо не то
    карточка Яндекса дала       phosagro.ru/about/holding_kirovsk    страницу ИМЕННО ЭТОГО завода
                                +7 (81531) 5-55-90                   телефон
                                Ленинградская ул., 1, Кировск        адрес

То есть карточка закрывает случай «завод внутри холдинга», на котором наш судья сайта
спотыкается: он умеет отвечать «сайт не тот», но не умеет находить страницу завода внутри
чужого сайта. Это же и есть дыра, из-за которой у 3-й сессии приёмка не подтверждала людей
сайтом ни разу: `company.sayt` пуст у всех 491.

ЧЕГО КАРТОЧКА НЕ ДАЁТ, И ЭТО НАДО СКАЗАТЬ ЧЕСТНО. Телефон там — линия организации, приёмная
или диспетчерская. Личных мобильных технических ЛПР — нашей главной меры — она не приносит и
не может. Ценность канала в другом: сайт, страница завода внутри холдинга, адрес и проверка
«то ли это вообще предприятие».

ДВА ЗАХОДА, А НЕ ОДИН. Переход по ссылке ВНУТРИ страницы (`location.href = ...`) убивает
контекст выполнения, и результат не возвращается вовсе — проверено, ответ приходил пустым
объектом. Поэтому: первый запрос ищет карточку и отдаёт её адрес, второй открывает её.

Использование:
    python3 p25_yandex_kartochka.py --predel 20 --parallel 3
"""
import csv
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
OCHERED = os.path.join(L, 'P25-OCHERED.csv')
VYHOD = os.path.join(L, 'P25-YANDEX-KARTOCHKI.csv')
KARTA = os.path.join(L, 'P25-yandex-kartochki-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'nazvanie_na_karte', 'adres', 'telefony', 'sayt_iz_kartochki',
        'ssylka_kartochki', 'organizaciy_naydeno', 'prinadlezhnost', 'chem_proverena']

# КАРТЫ ИЩУТ ПО НАЗВАНИЮ И ИНН ИГНОРИРУЮТ. Поймано на четвёртом же прогоне, до выпуска на
# 491: по запросу «АО "АПАТИТ" ИНН 5103070023» карточка отдала телефон +7 (8453) 49-40-34 —
# код 8453 это Балаково Саратовской области, а завод в Кировске Мурманской. Сайтом при этом
# подставился YouTube-канал холдинга. То есть карточка настоящая, телефон настоящий, и он
# чужой. Без проверки принадлежности канал был бы генератором чужих номеров.
#
# Проверяем двумя независимыми признаками:
#   1) хост сайта из карточки совпал с сайтом, который мы уже подтвердили по ИНН — сильный;
#   2) регион адреса совпал с регионом постановки на учёт по коду ИНН — слабее, но дешёвый.
# Ни один не сработал — строка пишется с пометкой «НЕ подтверждена» и в заливку не идёт.

# ТЕЛЕФОН С КОДОМ ЛЮБОЙ ДЛИНЫ. Первая версия искала `\d{3}` кодом города и не увидела
# «+7 (81531) 5-55-90» — код Кировска пятизначный, а номер там шестизначный. Ошибка тихая:
# карточка была открыта, телефон в тексте стоял, а в выдаче оказался пустой список.
TEL = re.compile(r'(?:\+7|8)[\s\-()]*\d{3,5}[\s\-()]*\d{1,3}[\s\-]?\d{2,3}[\s\-]?\d{2}')

JS_POISK = """window.__RES = JSON.stringify({
  org: [...new Set([...document.querySelectorAll('a[href*="/maps/org/"]')]
        .map(a => a.href.split('?')[0])
        .filter(h => !/\\/(gallery|reviews|photos|prices|inside|edit)\\/?$/.test(h)))].slice(0, 3),
  dlina: document.body ? document.body.innerText.length : 0,
  kapcha: /капч|вы не робот|подтвердите/i.test(document.body ? document.body.innerText : '')
});"""

JS_KARTOCHKA = r"""window.__RES = (async () => {
  const spat = (ms) => new Promise(r => setTimeout(r, ms));
  // «Показать телефон» — кнопка, а не ссылка. Пока не нажата, в тексте виден только первый
  // номер; остальные скрыты. Жмём все, какие нашлись, но не больше трёх: дальше идут чужие
  // организации в том же списке.
  const kn = [...document.querySelectorAll('div,button,a')]
      .filter(e => /Показать телефон/i.test(e.textContent || '') && (e.textContent || '').length < 40);
  for (const k of kn.slice(0, 3)) { try { k.click(); await spat(1200); } catch (e) {} }
  await spat(1200);
  const t = document.body ? document.body.innerText : '';
  const stroki = t.split('\n').map(s => s.trim()).filter(Boolean);
  const adres = (stroki[stroki.indexOf('Адрес') + 1] || '').slice(0, 120);
  return JSON.stringify({
    zagolovok: document.title.slice(0, 90),
    nazvanie: stroki[0] || '',
    adres: adres,
    tekst: t.slice(0, 4000),
    // ЧУЖИЕ ПЛОЩАДКИ ОТСЕИВАЮТСЯ СПИСКОМ, А НЕ НА ГЛАЗ. Первая версия отсекала ВК, ОК и
    // Телеграм — и пропустила `youtube.com`, который уехал в список подтверждённых сайтов
    // предприятия и дошёл до обхода страниц. Канал организации на видеохостинге, страница в
    // соцсети и карточка агрегатора — не сайт предприятия ни в каком смысле, но выглядят как
    // «внешняя ссылка с карточки» одинаково.
    ssylki: [...new Set([...document.querySelectorAll('a[href^="http"]')].map(a => a.href)
             .filter(h => !/yandex|ya\.ru|kinopoisk|market|dzen|vk\.(com|ru)|ok\.ru|t\.me|telegram|youtube|youtu\.be|rutube|facebook|instagram|twitter|x\.com|linkedin|wikipedia|rusprofile|list-org|checko|zachestnyibiznes|sbis\.ru|audit-it|sravni|2gis|zoon|flamp|hh\.ru|avito|wildberries|ozon/i.test(h)))].slice(0, 5)
  });
})();"""


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def region_iz_adresa(adres, region):
    """Совпал ли регион. Сравниваем по КОРНЮ названия области: в адресе Яндекса пишут
    «Кировск», «Оренбург», «Ставрополь» — без слова «область», поэтому сличать строки целиком
    нельзя, а корень («мурманск», «оренбург») в адресе встречается."""
    if not region or not adres:
        return False
    koren = re.split(r'\s+', region.lower())[0]
    koren = re.sub(r'(ая|ий|ое|ой|ья)$', '', koren)[:6]
    return bool(koren) and koren in adres.lower()


def probe(url, js, after_ms):
    zad = {'url': url, 'screenshot': False,
           'eval_js': {'script': js, 'after_ms': after_ms, 'return': 'window.__RES'}}
    try:
        p = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                            json.dumps(zad, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return None, 'таймаут раннера'
    try:
        d = json.loads(p.stdout[p.stdout.index('{'):]).get('data') or {}
    except (ValueError, json.JSONDecodeError):
        return None, (p.stdout or p.stderr)[-140:]
    if d.get('eval_js_err'):
        return None, str(d['eval_js_err'])[:140]
    try:
        return json.loads(d.get('eval_js_value') or 'null'), ''
    except json.JSONDecodeError as e:
        return None, f'ответ не разобран: {str(e)[:70]}'


def odna_kompaniya(c):
    zapros = urllib.parse.quote(f"{c['predpriyatie']} ИНН {c['inn']}")
    r1, err = probe(f'https://yandex.ru/maps/?text={zapros}', JS_POISK, 12000)
    if r1 is None:
        return c, None, f'поиск: {err}'
    if r1.get('kapcha'):
        return c, None, 'капча на поиске'
    org = r1.get('org') or []
    if not org:
        # По названию с ИНН не нашлось — пробуем одним названием. Раздельно, чтобы в журнале
        # было видно, каким запросом карточка взята.
        r1b, err = probe('https://yandex.ru/maps/?text=' + urllib.parse.quote(c['predpriyatie']),
                         JS_POISK, 12000)
        org = (r1b or {}).get('org') or []
        if not org:
            return c, {'organizaciy_naydeno': 0}, ''
    r2, err = probe(org[0], JS_KARTOCHKA, 9000)
    if r2 is None:
        return c, None, f'карточка: {err}'
    tekst = r2.get('tekst') or ''
    telefony = []
    for m in TEL.finditer(tekst):
        t = re.sub(r'\s+', ' ', m.group(0)).strip()
        if t not in telefony:
            telefony.append(t)
    ssylki = r2.get('ssylki') or []
    adres = r2.get('adres') or ''
    nash_sayt = (c.get('_sayt') or '').split('//')[-1].replace('www.', '').strip('/')
    po_saytu = bool(nash_sayt) and any(nash_sayt in (u or '') for u in ssylki)
    region = (c.get('_region') or '')
    po_regionu = region_iz_adresa(adres, region)
    if po_saytu:
        prinadl, chem = 'подтверждена', f'сайт из карточки совпал с подтверждённым {nash_sayt}'
    elif po_regionu:
        prinadl, chem = 'подтверждена', f'регион адреса совпал с регионом по ИНН ({region})'
    else:
        prinadl, chem = 'НЕ подтверждена', (
            f'ни сайт, ни регион не совпали (по ИНН {region or "регион неизвестен"}, '
            f'адрес «{adres[:50]}»)')
    return c, {'nazvanie_na_karte': (r2.get('nazvanie') or '')[:90],
               'prinadlezhnost': prinadl, 'chem_proverena': chem,
               'adres': r2.get('adres') or '',
               'telefony': ' | '.join(telefony[:4]),
               'sayt_iz_kartochki': ' | '.join((r2.get('ssylki') or [])[:2]),
               'ssylka_kartochki': org[0],
               'organizaciy_naydeno': len(org)}, ''


def main():
    parallel = dovod('--parallel', 3)
    predel = dovod('--predel', 10 ** 9)
    import pochinka_dlya_paneli as pochinka
    sajty = {}
    for r in chitat(os.path.join(L, 'P25-SAJTY.csv')):
        if r.get('itog') == 'подтверждён' and r.get('inn'):
            sajty[r['inn']] = r.get('sayt', '')
    och = chitat(OCHERED)
    for r in och:
        r['_sayt'] = sajty.get(r['inn'], '')
        r['_region'] = pochinka.region_po_inn(r['inn'])[0]
    proydeno = {r['inn'] for r in chitat(KARTA)}
    celi = [r for r in och if r['inn'] not in proydeno][:predel]
    if not celi:
        print('целей нет', file=sys.stderr)
        return

    import predel_rannera
    predel_rannera.preduprezhdenie(parallel * 2)      # два захода на предприятие
    print(f'предприятий: {len(celi)} (пройдено {len(proydeno)})', file=sys.stderr)

    import p25_hodok as hodok
    fv, novyy_v, per_v, otl_v = hodok.dopisyvat(VYHOD, COLS)
    fk, novyy_k, per_k, otl_k = hodok.dopisyvat(
        KARTA, ['inn', 'predpriyatie', 'pochemu'])
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    wk = csv.DictWriter(fk, fieldnames=['inn', 'predpriyatie', 'pochemu'], delimiter=';',
                        extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'карточек': 0, 'принадлежность подтверждена': 0, 'с телефоном': 0,
           'с сайтом': 0, 'не нашлось': 0, 'сбоев': 0}
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (c, r, err) in enumerate(pool.map(odna_kompaniya, celi), 1):
            with lock:
                if r is None:
                    sch['сбоев'] += 1
                    print(f'  СБОЙ {c["inn"]}: {err[:100]}', file=sys.stderr, flush=True)
                    continue
                if not r.get('organizaciy_naydeno'):
                    sch['не нашлось'] += 1
                else:
                    sch['карточек'] += 1
                    if r.get('prinadlezhnost') == 'подтверждена':
                        sch['принадлежность подтверждена'] += 1
                    if r.get('telefony'):
                        sch['с телефоном'] += 1
                    if r.get('sayt_iz_kartochki'):
                        sch['с сайтом'] += 1
                    wv.writerow(dict(r, inn=c['inn'], predpriyatie=c['predpriyatie']))
                wk.writerow({'inn': c['inn'], 'predpriyatie': c['predpriyatie'],
                             'pochemu': 'обойдено'})
                fv.flush()
                fk.flush()
                if n % 5 == 0 or n == len(celi):
                    print(f'  {n}/{len(celi)}: ' + ', '.join(f'{k} {v}' for k, v in sch.items()),
                          file=sys.stderr, flush=True)
    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
