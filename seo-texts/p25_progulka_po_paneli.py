# -*- coding: utf-8 -*-
"""Пройти по ЖИВОЙ панели случайными карточками и провалиться из них в первоисточники.

ЗАЧЕМ ИМЕННО ЖИВАЯ СТРАНИЦА. Между базой и глазами продавца стоят запрос, шаблон и
отбор. Сегодня там нашлась дыра: карточка печатала должность из поля `post`, которого в
таблице нет, — база говорила «8 909 должностей есть», глаз видел пустой значок. Проверка
по базе такое пропускает по устройству. Поэтому хожу по странице.

ЧТО СЧИТАЕТСЯ ПРОВЕРЕННОЙ ЦЕПОЧКОЙ. Не «ссылка есть» и не «страница открылась», а:
на карточке заявлен номер (или человек) со ссылкой на источник; источник открыт; и в его
тексте ЭТОТ ЖЕ номер найден. Три исхода называются словами:

  * ПОДТВЕРЖДЕНО ИСТОЧНИКОМ — номер найден в тексте страницы-источника;
  * В ИСТОЧНИКЕ НЕТ — страница открылась, номера в ней нет: цепочка рвётся здесь;
  * ИСТОЧНИК НЕ ОТКРЫЛСЯ / ССЫЛКИ НЕТ — проверить нечем, и это не то же самое, что «нет».

Номер сверяется ЦИФРАМИ, а не строкой: «+7 (343) 229-00-75» на карточке и
«8 343 229 00 75» в источнике — один номер, и написание тут ни при чём. Тем же правилом
я весь день чинила свои разборы.

Случайность НАСТОЯЩАЯ: строки берутся по случайным номерам из всей очереди, а не первые
попавшиеся. Первые попавшиеся — это всегда самые заполненные, и по ним витрина выглядит
лучше, чем есть.

Запуск: python3 p25_progulka_po_paneli.py [--kart N] [--zerno N] [--bazy centro,centro1]
"""
import base64
import collections
import http.cookiejar
import io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PANEL = 'http://127.0.0.1:8012'
TOKEN_FAYL = r'C:\sender\_ops\p25_user3_token.txt'
VYHOD = r'C:\sender\_ops\P25-PROGULKA-PO-PANELI-3S.json'
TEG = re.compile(r'<[^>]+>')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0 Safari/537.36')


def dovod(s):
    """Аргумент командной строки со значением."""
    return sys.argv[sys.argv.index(s) + 1] if s in sys.argv else ''


KART = int(dovod('--kart') or 12)
ZERNO = int(dovod('--zerno') or 20260805)
BAZY = (dovod('--bazy') or 'centro,centro1,centro2').split(',')


def cifry(s):
    c = re.sub(r'\D', '', str(s or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    if len(c) == 10 and c[0] == '9':
        return '7' + c
    return ''


def tekst(h):
    t = re.sub(r'(?is)<(?:script|style)[^>]*>.*?</(?:script|style)>', ' ', h or '')
    t = re.sub(r'(?i)<(?:br|/li|/p|/tr|/div|/h\d)[^>]*>', '\n', t)
    t = TEG.sub(' ', t)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"'), ('&#39;', "'"),
                 ('&laquo;', '«'), ('&raquo;', '»'), ('&mdash;', '—'), ('&ndash;', '–')):
        t = t.replace(a, b)
    return t


def pary_iz_fayla():
    """Пары логин:пароль из токен-файла. Значения НЕ печатаются — только используются.

    Вход в панель — HTTP Basic (`_login` читает заголовок Authorization), а не форма:
    оттого прежние 422 и 429. Файл `p25_user3_token.txt` — четыре строки с двоеточиями;
    возможные написания пары разные, поэтому беру всё, что похоже на «логин:пароль» или
    «логин=пароль», где логин это userN/admin. Отдельный POST /login не нужен: Basic-
    заголовок просто прикладывается к каждому запросу.
    """
    syroy = ''
    if os.path.exists(TOKEN_FAYL):
        syroy = io.open(TOKEN_FAYL, encoding='utf-8', errors='replace').read()
    pary = []

    # Формат файла (проверено структурой, значения не печатались):
    #   логин: <имя>
    #   пароль: <секрет>
    # Собираю пару из строк с метками «логин»/«пароль» — левая часть здесь русская
    # метка, а не сам логин, оттого первый разбор и промахнулся.
    login, parol = '', ''
    for stroka in syroy.split('\n'):
        m = re.match(r'\s*(логин|login|user|имя)\s*[:=]\s*(\S.*)$', stroka, re.I)
        if m:
            login = m.group(2).strip()
        m = re.match(r'\s*(пароль|password|pass|токен|token)\s*[:=]\s*(\S.*)$', stroka, re.I)
        if m:
            parol = m.group(2).strip()
    if login and parol:
        pary.append((login, parol))

    # Запасной вход: пары «логин=пароль» из окружения (владелец передал user1/user2).
    # Приходит окружением раннера, в файлы репозитория не попадает.
    for kus in os.environ.get('PANEL_LOGINS', '').replace(',', '\n').split('\n'):
        im, _, par = kus.strip().partition('=')
        if im.strip() and par.strip():
            pary.append((im.strip(), par.strip()))
    return pary


class Hodok:
    """Ходок с Basic-заголовком и банкой кук: один вход, дальше просто ходим."""

    def __init__(self):
        self.banka = http.cookiejar.CookieJar()
        self.otkryvalka = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.banka))
        self.avtorizaciya = ''   # 'Basic ...' — секрет держим тут, не печатаем

    def vzyat(self, url, dannye=None, svoy=True, popytok=2):
        for p in range(popytok):
            rq = urllib.request.Request(
                url, data=dannye, method='POST' if dannye is not None else 'GET')
            rq.add_header('User-Agent', 'progulka-3s' if svoy else UA)
            if dannye is not None:
                rq.add_header('Content-Type', 'application/x-www-form-urlencoded')
            # Basic-заголовок только на СВОЮ панель, наружу его не носим.
            if svoy and self.avtorizaciya:
                rq.add_header('Authorization', self.avtorizaciya)
            try:
                with self.otkryvalka.open(rq, timeout=50) as o:
                    syroy = o.read()
                    for kod in ('utf-8', 'cp1251'):
                        try:
                            return o.status, syroy.decode(kod), o.headers
                        except Exception:  # noqa: BLE001
                            continue
                    return o.status, syroy.decode('utf-8', 'replace'), o.headers
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode('utf-8', 'replace'), e.headers
            except Exception as e:  # noqa: BLE001
                if p == popytok - 1:
                    return 0, '__ОШИБКА__ %s' % type(e).__name__, None
                time.sleep(1.2)

    def voyti(self):
        """Вход Basic-заголовком. Пар мало, перебор короткий — 429 не ловим."""
        pary = pary_iz_fayla()
        if not pary:
            return False, 'в токен-файле не нашлось пары логин:пароль'
        for im, par in pary:
            self.avtorizaciya = 'Basic ' + base64.b64encode(
                ('%s:%s' % (im, par)).encode()).decode()
            kod, proba, _ = self.vzyat(PANEL + '/obzvon/centro')
            forma = bool(re.search(r'name="?password', proba, re.I))
            if kod == 200 and not forma:
                return True, 'вошли как %s' % im
        return False, 'ни одна пара не подошла (последний код %s)' % kod


def lyudi_iz_kartochki(h):
    """Люди карточки: имя, значок должности и строка про привязку — как их видно."""
    out = []
    for m in re.finditer(r'<div class="ct-person(?:[^"]*)">(.*?)(?=<div class="ct-person"|'
                         r'</div>\s*</section>|$)', h, re.S):
        kus = m.group(1)
        imya = re.search(r'<b>(.*?)</b>', kus, re.S)
        znachok = re.search(r'class="ct-badge[^"]*">(.*?)</span>', kus, re.S)
        privyazka = re.search(r'привязка[^<]{0,200}', tekst(kus))
        tel = [x for x in (cifry(t) for t in re.findall(r'tel:([+\d\-()\s]+)', kus)) if x]
        out.append({'chelovek': re.sub(r'\s+', ' ', tekst(imya.group(1))).strip()
                    if imya else '',
                    'dolzhnost': re.sub(r'\s+', ' ', tekst(znachok.group(1))).strip()
                    if znachok else '',
                    'pro_privyazku': privyazka.group(0).strip() if privyazka else '',
                    'telefony': tel})
    return out


def kontakty_iz_kartochki(h):
    """Контакты со ссылкой на источник: номер, кто, откуда и КУДА ведёт ссылка."""
    out = []
    # Каждый контакт — свой блок; берём номер, ближайшую внешнюю ссылку и подпись.
    for m in re.finditer(r'tel:([+\d\-()\s]{6,})', h):
        nachalo = max(0, m.start() - 900)
        okno = h[nachalo:m.start() + 900]
        ssylki = [u for u in re.findall(r'href="(https?://[^"]+)"', okno)
                  if '127.0.0.1' not in u and 'sort-inspection' not in u]
        podpis = tekst(okno)
        out.append({'nomer': cifry(m.group(1)), 'ssylka': ssylki[0] if ssylki else '',
                    'okolo': re.sub(r'\s+', ' ', podpis)[-190:]})
    # Один и тот же номер в карточке встречается дважды (список и карточка) — схлопываем.
    vidno = {}
    for k in out:
        if k['nomer'] and (k['nomer'] not in vidno or (k['ssylka'] and
                                                       not vidno[k['nomer']]['ssylka'])):
            vidno[k['nomer']] = k
    return list(vidno.values())


def main():
    random.seed(ZERNO)
    h = Hodok()
    ok, kak = h.voyti()
    print('вход: %s — %s' % ('да' if ok else 'НЕТ', kak), file=sys.stderr, flush=True)
    if not ok:
        print('ИТОГ ' + json.dumps({'вход': False, 'почему': kak}, ensure_ascii=False))
        return

    sch = collections.Counter()
    cepochki, kartochki = [], []
    istochniki = {}

    for baza in BAZY:
        kod, spisok, _ = h.vzyat('%s/obzvon/%s' % (PANEL, baza))
        if kod != 200:
            sch['база %s не открылась (%s)' % (baza, kod)] += 1
            continue
        m = re.search(r'(?:всего|найдено)[^\d]{0,20}(\d[\d\s]{0,9})', tekst(spisok), re.I)
        vsego = int(re.sub(r'\s', '', m.group(1))) if m else 0
        sch['%s: строк в очереди' % baza] = vsego
        if not vsego:
            # Счётчика не нашли — ходим по первым двум сотням, честно это назвав.
            vsego = 200
            sch['%s: счётчика не нашли, беру из первых 200' % baza] += 1
        nomera = random.sample(range(vsego), min(KART, vsego))
        for nn in nomera:
            kod, kart, _ = h.vzyat('%s/obzvon/%s/card?skip=%d' % (PANEL, baza, nn))
            if kod != 200 or 'ct-card' not in kart:
                sch['карточка не открылась (%s)' % kod] += 1
                continue
            tk = tekst(kart)
            nazv = re.search(r'ИНН\s*(\d{10,12})', tk)
            imya_pr = re.sub(r'\s+', ' ', tk.strip())[:70]
            lyudi = lyudi_iz_kartochki(kart)
            kont = kontakty_iz_kartochki(kart)
            sch['карточек открыто'] += 1
            sch['людей на карточках'] += len(lyudi)
            sch['людей со значком должности'] += sum(1 for x in lyudi if x['dolzhnost'])
            sch['людей с пометкой привязки'] += sum(1 for x in lyudi if x['pro_privyazku'])
            sch['номеров на карточках'] += len(kont)
            kartochki.append({'baza': baza, 'skip': nn,
                              'inn': nazv.group(1) if nazv else '',
                              'predpriyatie': imya_pr, 'lyudey': len(lyudi),
                              'nomerov': len(kont),
                              'lyudi': lyudi[:8]})

            for k in kont:
                zapis = {'baza': baza, 'inn': nazv.group(1) if nazv else '',
                         'predpriyatie': imya_pr, 'nomer': k['nomer'],
                         'ssylka': k['ssylka'], 'okolo': k['okolo']}
                if not k['ssylka']:
                    zapis['itog'] = 'ССЫЛКИ НЕТ — провалиться некуда'
                    sch['ССЫЛКИ НЕТ'] += 1
                else:
                    u = k['ssylka']
                    if u not in istochniki:
                        kodi, telo, _ = h.vzyat(u, svoy=False)
                        istochniki[u] = (kodi, telo)
                    kodi, telo = istochniki[u]
                    if kodi != 200 or telo.startswith('__ОШИБКА__'):
                        zapis['itog'] = 'ИСТОЧНИК НЕ ОТКРЫЛСЯ (%s)' % kodi
                        sch['ИСТОЧНИК НЕ ОТКРЫЛСЯ'] += 1
                    else:
                        t_ist = tekst(telo)
                        vse = {cifry(x) for x in re.findall(
                            r'(?:\+7|\b8)?[\s\-(]{0,3}\d[\d\s\-()]{7,18}\d', t_ist)}
                        if k['nomer'] in vse:
                            zapis['itog'] = 'ПОДТВЕРЖДЕНО ИСТОЧНИКОМ'
                            sch['ПОДТВЕРЖДЕНО ИСТОЧНИКОМ'] += 1
                        else:
                            zapis['itog'] = 'В ИСТОЧНИКЕ НЕТ'
                            zapis['chto_v_istochnike'] = sorted(x for x in vse if x)[:6]
                            sch['В ИСТОЧНИКЕ НЕТ'] += 1
                cepochki.append(zapis)

    # Печатаем глазами: по одной карточке из каждой базы и десяток цепочек.
    print('\n=== карточки, как их видно')
    for k in kartochki[:8]:
        print('\n--- %s skip=%d  ИНН %s  %s' % (k['baza'], k['skip'], k['inn'] or '—',
                                                k['predpriyatie'][:52]))
        for l in k['lyudi'][:4]:
            print('    %-28s значок: %-22s %s'
                  % (l['chelovek'][:28], l['dolzhnost'][:22] or 'ПУСТО',
                     l['pro_privyazku'][:54]))
    print('\n=== цепочки: что заявлено -> что в первоисточнике')
    for c in cepochki[:22]:
        print('  %-26s %-11s %-28s %s' % (c['predpriyatie'][:26], c['nomer'],
                                          c['itog'][:28], c['ssylka'][:56] or '—'))

    io.open(VYHOD, 'w', encoding='utf-8').write(json.dumps(
        {'kartochki': kartochki, 'cepochki': cepochki,
         'schet': dict(sch)}, ensure_ascii=False, indent=1))
    url, tokd = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    if url and tokd:
        rq = urllib.request.Request(url.rstrip('/') + '/' + os.path.basename(VYHOD),
                                    data=io.open(VYHOD, 'rb').read(), method='PUT')
        rq.add_header('X-Drop-Token', tokd)
        try:
            sch['выложено, ответ дропа %s' % urllib.request.urlopen(rq, timeout=180).status] += 1
        except Exception as e:  # noqa: BLE001
            sch['выкладка не прошла: %s' % str(e)[:40]] += 1

    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    vsego_cep = sum(sch[x] for x in ('ПОДТВЕРЖДЕНО ИСТОЧНИКОМ', 'В ИСТОЧНИКЕ НЕТ',
                                     'ИСТОЧНИК НЕ ОТКРЫЛСЯ', 'ССЫЛКИ НЕТ'))
    print('ИТОГ ' + json.dumps({
        'карточек пройдено': sch['карточек открыто'],
        'цепочек проверено': vsego_cep,
        'подтверждено первоисточником': sch['ПОДТВЕРЖДЕНО ИСТОЧНИКОМ'],
        'разрыв цепочки': sch['В ИСТОЧНИКЕ НЕТ'],
        'зерно случайности': ZERNO}, ensure_ascii=False))


if __name__ == '__main__':
    main()
