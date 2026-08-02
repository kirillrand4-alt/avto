# -*- coding: utf-8 -*-
"""Кандидаты в сайты: добить проверку по ССЫЛКАМ с главной, а не по девяти путям.

Массовый поиск даёт на каждый подтверждённый сайт примерно семь кандидатов:
выдача нашла правдоподобный домен, но ИНН не встретился на девяти фиксированных
путях (`/`, `/contacts/`, `/rekvizity/` и т.п.). Это ограничение проверки, а не
свойство сайтов: реквизиты лежат где угодно — `/company/info/`,
`/o-predpriyatii/`, `/svedeniya/`, в подвале отдельной страницы «Раскрытие
информации».

Здесь проверка идёт честнее: с главной собираются ВНУТРЕННИЕ ссылки, чей текст
или адрес похож на реквизиты/контакты/о компании, и ИНН ищется на них. Рубеж
НЕ ослаблен: в `site` попадает только домен, на страницах которого нашёлся сам
ИНН. Не нашёлся — остаётся кандидатом, как и был. Совпадение по НАЗВАНИЮ
сайтом не считается: название компании стоит и на сайтах справочников, и у
дилеров, и мы уже ловили чужой сайт, приписанный по имени.

Durable: журнал `kandidaty_sajtov.jsonl` с flush+fsync, повышение — штатным
`upsert_company`. Резюмируемо: пройденное берётся из журнала.

Запуск: python kandidaty_sajtov.py [--lim N] [--potokov N] [--budget СЕК] [--dry]
"""
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402

СУХОЙ = '--dry' in sys.argv


def арг(имя, поум):
    return sys.argv[sys.argv.index(имя) + 1] if имя in sys.argv else поум


ЦЕЛЕВОЙ = арг('--targets', '')
ЛИМ = int(арг('--lim', '400'))
ПОТОКОВ = int(арг('--potokov', '8'))
БЮДЖЕТ = float(арг('--budget', '1100'))
ЖУРНАЛ = r'C:\sender\server\kandidaty_sajtov.jsonl'
_ЗАМОК = threading.Lock()

# Ссылка «про компанию»: смотрим И текст, И адрес — на части сайтов пункт меню
# называется картинкой, зато адрес говорящий, и наоборот.
_ПОХОЖЕ = re.compile(
    r'реквизит|контакт|о\s*компании|о\s*предприятии|о\s*нас|сведения|'
    r'раскрытие|документ|учредит|kontakt|contact|rekvizit|about|company|'
    r'info|svedeniya|dokument|disclosure', re.I)
_ССЫЛКА = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.{0,120}?)</a>',
                     re.I | re.S)
_ТЕГИ = re.compile(r'<[^>]+>')


def _качать(урл):
    try:
        h, _m, _mt = EC._fetch_site(урл)
        return h or ''
    except Exception:  # noqa: BLE001
        return ''


def _есть_инн(html, цифры):
    if not html:
        return False
    плоско = re.sub(r'[\s\-\u00a0]', '', html)
    return bool(re.search(r'(?<!\d)' + цифры + r'(?!\d)', плоско))


def проверить(инн, сайт):
    """Вернуть URL страницы, где нашёлся ИНН, либо ''."""
    цифры = re.sub(r'\D', '', инн)
    осн = сайт if sys.version_info else сайт
    осн = осн.rstrip('/')
    if not осн.startswith('http'):
        осн = 'http://' + осн
    дом = EC.site_domain(осн)
    главная = _качать(осн)
    if _есть_инн(главная, цифры):
        return осн + '/'
    if not главная:
        return ''
    # внутренние ссылки, похожие на «про компанию»
    кандидаты = []
    for адрес, текст in _ССЫЛКА.findall(главная):
        подпись = _ТЕГИ.sub(' ', текст)
        if not (_ПОХОЖЕ.search(подпись) or _ПОХОЖЕ.search(адрес)):
            continue
        полный = urllib.parse.urljoin(осн + '/', адрес.strip())
        if EC.site_domain(полный) != дом:
            continue          # чужой домен по ссылке нас не интересует
        if полный not in кандидаты:
            кандидаты.append(полный)
    for у in кандидаты[:14]:
        if _есть_инн(_качать(у), цифры):
            return у
    return ''


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    пройдены = set()
    if os.path.exists(ЖУРНАЛ):
        for ln in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                пройдены.add(json.loads(ln).get('инн'))
            except Exception:  # noqa: BLE001
                continue

    ряды = q("SELECT inn,cand_site FROM companies "
             "WHERE COALESCE(cand_site,'')<>'' AND COALESCE(site,'')=''"
             ).fetchall()
    # Кандидаты в `companies` копились всеми сессиями и по всем задачам: среди
    # них попадаются и мусорные (vk.ru как «сайт» ООО), и просто чужие нашей
    # задаче. Без списка целей оп честно проверяет случайные 25 и даёт ноль —
    # это ничего не говорит о НАШИХ предприятиях.
    if ЦЕЛЕВОЙ:
        хочу = set()
        for ln in open(ЦЕЛЕВОЙ, encoding='utf-8-sig', errors='replace'):
            m = re.search(r'\b(\d{10}|\d{12})\b', ln)
            if m:
                хочу.add(m.group(1))
        ряды = [(и, с) for и, с in ряды if и in хочу]
        print(f'целевой файл: {ЦЕЛЕВОЙ}, ИНН в нём {len(хочу)}', flush=True)
    работа = [(и, с) for и, с in ряды if и not in пройдены][:ЛИМ]
    print(f'кандидатов без подтверждённого сайта: {len(ряды)}; '
          f'уже проверены глубоко: {len(пройдены)}; в работу: {len(работа)}',
          flush=True)
    if not работа:
        print('проверять нечего')
        return

    было = q("SELECT COUNT(*) FROM companies WHERE COALESCE(site,'')<>''"
             ).fetchone()[0]
    начало = time.time()
    стоп = threading.Event()

    def одна(з):
        инн, сайт = з
        if стоп.is_set():
            return None
        try:
            где = проверить(инн, сайт)
        except Exception as e:  # noqa: BLE001
            return {'инн': инн, 'сайт': сайт, 'где': '',
                    'ошибка': str(e)[:60]}
        return {'инн': инн, 'сайт': сайт, 'где': где}

    поднято = мимо = ошибок = сделано = 0
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        будущие = [пул.submit(одна, з) for з in работа]
        for ф in as_completed(будущие):
            if time.time() - начало > БЮДЖЕТ:
                стоп.set()
            зап = ф.result()
            if зап is None:
                continue
            сделано += 1
            with _ЗАМОК:
                with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
                    ж.write(json.dumps(зап, ensure_ascii=False) + '\n')
                    ж.flush()
                    os.fsync(ж.fileno())
            if зап.get('ошибка'):
                ошибок += 1
            elif зап['где']:
                поднято += 1
                if not СУХОЙ:
                    with _ЗАМОК:
                        db.upsert_company(зап['инн'], site=зап['сайт'])
            else:
                мимо += 1
            if сделано % 50 == 0:
                print(f'  … {сделано}/{len(работа)}: подтверждено {поднято}, '
                      f'мимо {мимо}, ошибок {ошибок}, '
                      f'{time.time() - начало:.0f}с', flush=True)

    стало = q("SELECT COUNT(*) FROM companies WHERE COALESCE(site,'')<>''"
              ).fetchone()[0]
    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    print(f'  компаний с подтверждённым сайтом: было {было} → стало {стало} '
          f'(+{стало - было})')
    print('ИТОГ ' + json.dumps(
        {'проверено': сделано, 'подтверждено': поднято, 'мимо': мимо,
         'ошибок': ошибок, 'секунд': round(time.time() - начало)},
        ensure_ascii=False))


if __name__ == '__main__':
    main()
