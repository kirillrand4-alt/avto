# -*- coding: utf-8 -*-
"""Обход поломки шлюза: сырьё собрал сервер, классифицирует ПЕСОЧНИЦА.

Почему так. С сервера владельца имя `router.cheap` разъезжается на два адреса Cloudflare,
и один из них с этого сервера мёртв (подробности и замеры - `SHLYUZ-PROVAJDERA-OPIS.md`).
Из песочницы тот же шлюз отвечает 200 за 2-5 с, потому что песочница выходит в сеть другим
маршрутом. Значит сбор оставляем серверу (у него ключ xmlriver и база), а разбор уводим
сюда.

ПРОМПТ ВЗЯТ ДОСЛОВНО из `news_scan.extract_event` на сервере, чтобы замер «сколько
событий» был сравним со старым, а не с новой формулировкой.

Клиент - штатный `gen_provider` (`make_client`/`call`): в нём ретраи, сырой разбор SSE и
правило про `stop_reason`, которых у самодельного urllib нет. У `call` НЕТ параметра
`max_tokens` - передашь, получишь TypeError и молчаливый пустой прогон.

Материалы идут пачками по `--pachka` штук на вызов: поштучно это 50 оплаченных вызовов
вместо пяти, а владелец просил квоту беречь. Каждый материал в пачке пронумерован, ответ
обязан вернуть объект на каждый номер; недостающие номера считаются ОТКАЗОМ, а не «не
капекс» - ровно та разница, из-за которой месяц молчания никто не заметил.

Использование:
    python3 seo-texts/novosti_razbor_pesochnica.py --syryo <файл.json> [--skolko 50]
                                                   [--pachka 10] [--inn]
"""
import argparse
import json
import os
import re
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

import gen_provider as G  # noqa: E402

MODEL = 'claude-fable-5'

# --- дословно из C:\sender\server\news_scan.py, функция extract_event ---
PRAVILO = (
    'Из текста новости/сигнала определи, есть ли ПРОМЫШЛЕННОЕ КАПЕКС-событие компании '
    '(стройка/модернизация/запуск цеха-линии/расширение/инвестиции/займ ФРП/резидентство/'
    'всплеск найма под расширение), после которого компании скоро нужно промышленное '
    'оборудование Руспрома — ЛИБО компрессоры/генераторы азота-кислорода (любое '
    'производство/стройка/добыча), ЛИБО фотосепараторы/рентген-инспекция (зерно, '
    'пищёвка, переработка, сортировка вторсырья/руды, логистика). '
    'is_capex=false для: ЖИЛЬЯ и жилых кварталов, дорог/мостов, школ/больниц/соцобъектов, '
    'парков/благоустройства, офисов/ТЦ, а также анонсов БЕЗ конкретной компании-инвестора '
    '(«в регионе планируют», «технопарк откроют») и рекламных/блоговых постов. ')

POLYA = (
    '{"n":номер материала,"is_capex":true/false,'
    '"company":"ОФИЦИАЛЬНОЕ название компании В ИМЕНИТЕЛЬНОМ ПАДЕЖЕ (как в ЕГРЮЛ: '
    '«Северсталь», НЕ «Северстали»; без слов завод/компания/предприятие, если они не '
    'часть названия) или пусто",'
    '"event_type":"новый завод|модернизация|запуск линии|расширение|инвестиции|тендер|найм|прочее",'
    '"what":"что строят/делают: 1-2 ПОЛНЫХ предложения с конкретикой из текста '
    '(объект, что за производство/линия, этап, мощность если названа) — это '
    'читает оператор и генератор письма, «модернизация производства» без '
    'деталей БЕСПОЛЕЗНА","region":"регион/город или пусто",'
    '"country":"РФ если в России, иначе страна",'
    '"sum":"сумма инвестиций если есть","hotness":1-5,'
    '"inn":"ИНН компании, ТОЛЬКО если он прямо назван в тексте, иначе пусто"}')


def promt(pachka):
    kuski = []
    for m in pachka:
        t = (m.get('title') or '').strip()
        sn = (m.get('snippet') or '').strip()
        kuski.append('%d. "%s"%s (источник: %s)'
                     % (m['n'], t, (' — ' + sn[:400]) if sn else '', m.get('source') or ''))
    return (PRAVILO
            + 'Разбери КАЖДЫЙ материал списка по отдельности. '
            + 'Верни СТРОГО JSON-массив без markdown, РОВНО по одному объекту на материал, '
            + 'в том же порядке, вида ' + POLYA + '. '
            + 'Ни одного номера не пропускай: если материал пустой или непонятный, всё равно '
            + 'верни объект с is_capex=false.\n\nМАТЕРИАЛЫ:\n' + '\n'.join(kuski))


def vytashchit_json(text):
    """Массив объектов из ответа. Пустой текст и мусор - это ОТКАЗ, а не пустой результат."""
    if not text or not text.strip():
        return None, 'пустой текст ответа'
    m = re.search(r'\[.*\]', text, re.S)
    if not m:
        m = re.search(r'\{.*\}', text, re.S)
        if not m:
            return None, 'в ответе нет JSON: ' + text[:80].replace('\n', ' ')
        try:
            return [json.loads(m.group(0))], None
        except Exception as ex:  # noqa: BLE001
            return None, 'JSON не разобрался: %s' % str(ex)[:60]
    try:
        d = json.loads(m.group(0))
        return (d if isinstance(d, list) else [d]), None
    except Exception as ex:  # noqa: BLE001
        return None, 'JSON не разобрался: %s' % str(ex)[:60]


def razobrat(materialy, pachka=10, attempts=3):
    client = G.make_client()
    vsego = len(materialy)
    rezultat = {}
    otkazy = []        # ВИДИМЫЙ счётчик отказа провайдера
    vyzovov = 0
    t0 = time.time()
    for i in range(0, vsego, pachka):
        kusok = materialy[i:i + pachka]
        nomera = [m['n'] for m in kusok]
        t = time.time()
        vyzovov += 1
        try:
            msg = G.call(client, [{'role': 'user', 'content': promt(kusok)}],
                         model=MODEL, attempts=attempts)
        except Exception as ex:  # noqa: BLE001
            otkazy.append({'nomera': nomera, 'prichina': '%s: %s'
                                                         % (type(ex).__name__, str(ex)[:120])})
            print('  пачка %2d (%s): ОТКАЗ ПРОВАЙДЕРА %s: %s'
                  % (vyzovov, '%d-%d' % (nomera[0], nomera[-1]), type(ex).__name__,
                     str(ex)[:90]), flush=True)
            continue
        text = ''.join(b.text for b in msg.content if b.type == 'text').strip()
        dannye, bеda = vytashchit_json(text)
        if dannye is None:
            otkazy.append({'nomera': nomera, 'prichina': bеda,
                           'stop_reason': msg.stop_reason})
            print('  пачка %2d (%s): ОТВЕТ БЕЗ РАЗБОРА (%s, stop_reason=%s)'
                  % (vyzovov, '%d-%d' % (nomera[0], nomera[-1]), bеda, msg.stop_reason),
                  flush=True)
            continue
        prishlo = 0
        for d in dannye:
            if not isinstance(d, dict):
                continue
            n = d.get('n')
            if n is None or n not in nomera:
                # без номера кладём по порядку
                svobodnye = [x for x in nomera if x not in rezultat]
                if not svobodnye:
                    continue
                n = svobodnye[0]
                d['n'] = n
            rezultat[n] = d
            prishlo += 1
        poteryano = [n for n in nomera if n not in rezultat]
        if poteryano:
            otkazy.append({'nomera': poteryano, 'prichina': 'номера не вернулись в ответе'})
        print('  пачка %2d (%s): разобрано %d из %d за %.1f с%s'
              % (vyzovov, '%d-%d' % (nomera[0], nomera[-1]), prishlo, len(kusok),
                 time.time() - t,
                 ('   ПОТЕРЯНЫ: %s' % poteryano) if poteryano else ''), flush=True)
    return rezultat, otkazy, vyzovov, time.time() - t0


def dadata_token():
    t = os.environ.get('DADATA_TOKEN')
    if t:
        return t
    for p in (os.path.join(DIR, 'rs.env'), os.path.join(DIR, 'runner-secrets.env'),
              os.path.join(DIR, 'server', 'runner-secrets.env'),
              '/tmp/rs.env'):
        try:
            for line in open(p, encoding='utf-8', errors='replace'):
                if line.strip().startswith('DADATA_TOKEN'):
                    return line.split('=', 1)[1].strip()
        except Exception:  # noqa: BLE001
            continue
    return None


def inn_po_imeni(nazvanie, tok):
    import urllib.request as U
    req = U.Request('https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
                    data=json.dumps({'query': nazvanie, 'count': 3}).encode(),
                    headers={'Content-Type': 'application/json',
                             'Accept': 'application/json',
                             'Authorization': 'Token ' + tok}, method='POST')
    with U.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode('utf-8', 'replace'))
    sug = d.get('suggestions') or []
    plohie = ('профсоюз', 'садовод', 'товарищество собственников')
    for s in sug:
        nm = (s.get('value') or '').lower()
        if any(p in nm for p in plohie):
            continue
        dd = s.get('data') or {}
        return dd.get('inn'), s.get('value'), len(sug)
    return None, None, len(sug)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--syryo', required=True)
    ap.add_argument('--skolko', type=int, default=50)
    ap.add_argument('--pachka', type=int, default=10)
    ap.add_argument('--attempts', type=int, default=3)
    ap.add_argument('--inn', action='store_true', help='разрешать названия в ИНН через DaData')
    ap.add_argument('--out', default='')
    a = ap.parse_args()

    syryo = json.load(open(a.syryo, encoding='utf-8'))
    materialy = [m for m in syryo if (m.get('title') or '').strip()][:a.skolko]
    for i, m in enumerate(materialy, 1):
        m['n'] = i
    print('### РАЗБОР В ПЕСОЧНИЦЕ: материалов %d, пачка %d, модель %s'
          % (len(materialy), a.pachka, MODEL))

    rezultat, otkazy, vyzovov, sek = razobrat(materialy, a.pachka, a.attempts)

    po_n = {m['n']: m for m in materialy}
    sobytiya = []
    for n, d in sorted(rezultat.items()):
        if d.get('is_capex') is True:
            d['title'] = po_n[n].get('title', '')
            d['url'] = po_n[n].get('url', '')
            sobytiya.append(d)

    s_kompaniey = [d for d in sobytiya if (d.get('company') or '').strip()]
    s_inn_iz_teksta = [d for d in sobytiya if (d.get('inn') or '').strip()]

    # ИНН по названию - через справочник ЕГРЮЛ, если есть токен
    s_inn = list(s_inn_iz_teksta)
    tok = dadata_token() if a.inn else None
    if a.inn and not tok:
        print('  ИНН: токена DaData нет ни в окружении, ни в rs.env - разрешение пропущено')
    elif tok:
        print('  ИНН: разрешаю %d названий через справочник ЕГРЮЛ' % len(s_kompaniey))
        for d in s_kompaniey:
            if (d.get('inn') or '').strip():
                continue
            try:
                inn, nm, kand = inn_po_imeni(d['company'], tok)
            except Exception as ex:  # noqa: BLE001
                print('    %-34s справочник отказал: %s' % (d['company'][:34], str(ex)[:60]))
                continue
            if inn:
                d['inn'] = inn
                d['inn_nazvanie'] = nm
                d['inn_kandidatov'] = kand
                s_inn.append(d)
            time.sleep(0.2)

    razobrano = len(rezultat)
    ne_doehalo = len(materialy) - razobrano
    print('\n=== ЧИСЛА (материалов %d) ===' % len(materialy))
    print('  вызовов провайдера:        %d за %.0f с' % (vyzovov, sek))
    print('  разобрано материалов:      %d' % razobrano)
    print('  ОТКАЗОВ провайдера/разбора:%d (материалов не доехало: %d)'
          % (len(otkazy), ne_doehalo))
    print('  признано КАПЕКС-событием:  %d' % len(sobytiya))
    print('  из них с названием компании:%d' % len(s_kompaniey))
    print('  из них с ИНН:              %d (из текста %d)'
          % (len({id(x) for x in s_inn}), len(s_inn_iz_teksta)))
    print('  не капекс:                 %d' % (razobrano - len(sobytiya)))
    if otkazy:
        print('  причины отказов:')
        for o in otkazy[:6]:
            print('    %s -> %s' % (o['nomera'], o['prichina'][:80]))
    print('\n  первые события:')
    for d in sobytiya[:10]:
        print('   * [%s] %-30s %s' % (d.get('inn') or '     -    ',
                                      (d.get('company') or '(без компании)')[:30],
                                      (d.get('what') or '')[:74]))

    out = a.out or os.path.join(DIR, 'novosti-razbor-rezultat.json')
    json.dump({'materialov': len(materialy), 'vyzovov': vyzovov, 'sekund': round(sek),
               'razobrano': razobrano, 'otkazov': len(otkazy), 'otkazy': otkazy,
               'sobytiy': len(sobytiya), 's_inn': len(s_inn), 'sobytiya': sobytiya,
               'vse': [rezultat[k] for k in sorted(rezultat)]},
              open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n  результат: %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
