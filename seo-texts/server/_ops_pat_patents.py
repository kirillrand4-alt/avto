# -*- coding: utf-8 -*-
"""ЗАМЕР ИСТОЧНИКА №1: ПАТЕНТЫ как поставщик технических ЛПР.

Что меряем честно:
  - у скольких компаний из выборки НАШЛИСЬ патенты, где патентообладатель —
    ИМЕННО ЭТА компания (а не однофамилец/тёзка);
  - сколько всего авторов вытащено;
  - сколько из них привязано к компании ДОКАЗАТЕЛЬНО (автор стоит в патенте,
    в патентообладателях которого — проверенное имя компании).

Разведано перед замером (см. _ops_pat_probe*.py):
  - patentdb.ru отдаёт 500 Server Error на любой странице — источник мёртв,
    это доказано сырым HTML, а не пустым разбором;
  - findpatent.ru/search.pl — поиск на Google CSE, сервер отдаёт 209 символов
    без результатов; сами страницы патентов findpatent/freepatent читаются;
  - patents.google.com/xhr/query — рабочий JSON-поиск, но с серверного IP
    ловит 429/503, поэтому ходим через VC._fetch (прокси);
  - XHR отдаёт ПЕРВОГО автора, полный список — только на странице патента.

Резюмируемо: состояние в C:\\sender\\_ops\\pat_patents.jsonl (fsync).
В enrich.db НИЧЕГО не пишем — это разведка.
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402
import verify_company as VC      # noqa: E402

ПОТОК = r'C:\sender\_ops\pat_patents.jsonl'
НАЧАЛО = time.time()
БЮДЖЕТ = float(os.environ.get('PAT_SEC', '195'))

# 15 компаний из sales_base: производственный профиль, внятное русское имя.
# Имя для поиска задаём ЯВНО: у части компаний бренд в базе — латинский домен
# («aecc», «npoa»), по нему в русских патентных базах не найдётся ничего.
ВЫБОРКА = [
    ('4026007424', 'Калужский турбинный завод'),
    ('6664013880', 'Уралхиммаш'),
    ('5001000066', 'Криогенмаш'),
    ('1660004229', 'Казанский оптико-механический завод'),
    ('5919470019', 'Соликамский магниевый завод'),
    ('4345000930', 'Электромашиностроительный завод ЛЕПСЕ'),
    ('4718011856', 'Сясьский целлюлозно-бумажный комбинат'),
    ('5911013780', 'Березниковский содовый завод'),
    ('3801098402', 'Ангарский электролизный химический комбинат'),
    ('5908007560', 'Галополимер Пермь'),
    ('0258005638', 'ПОЛИЭФ'),
    ('6679007712', 'НИПИГОРМАШ'),
    ('2128006240', 'ЗЭиМ'),
    ('7735007358', 'Микрон'),
    ('3821008439', 'Кремний'),
]

_ОПФ = re.compile(
    r'(открыт\w*|закрыт\w*|публичн\w*|непубличн\w*)?\s*акционерн\w*\s*обществ\w*|'
    r'обществ\w*\s*с\s*ограниченн\w*\s*ответственност\w*|'
    r'федеральн\w*\s*государственн\w*|государственн\w*\s*предпри\w*|'
    r'\b(оао|пао|зао|ао|ооо|нао|фгуп|гуп|фгбоу|фгаоу|ру|ru)\b', re.I)


def ключи(имя):
    """Опорные слова названия для сверки с патентообладателем."""
    ч = _ОПФ.sub(' ', ' ' + имя.lower() + ' ')
    ч = re.sub(r'[^0-9a-zа-яё]+', ' ', ч)
    слова = [w for w in ч.split() if len(w) >= 4]
    return слова


def свой(assignee, слова, имя):
    """Патентообладатель — ЭТА компания? Требуем совпадения опорных слов.

    Именно здесь отсекается однофамилец: у Уралхиммаша выдача Google Patents
    по строке «Уралхиммаш» возвращает в том числе патенты УрФУ — по одному
    лишь факту упоминания в тексте. Пока имя компании не стоит в поле
    «патентообладатель», автор к ней не привязан.
    """
    a = re.sub(r'[^0-9a-zа-яё]+', ' ', (assignee or '').lower())
    if not a.strip():
        return False, 'патентообладатель пуст'
    цел = re.sub(r'[^0-9a-zа-яё]', '', имя.lower())
    if цел and цел in re.sub(r'[^0-9a-zа-яё]', '', a):
        return True, 'имя целиком в патентообладателе'
    если = [w for w in слова if w in a]
    # одного общего слова («завод», «химический») мало
    значимые = [w for w in если if w not in
                ('завод', 'комбинат', 'обществ', 'компани', 'производственн',
                 'научно', 'объединение', 'имени', 'пермь')]
    if len(если) >= 2 and значимые:
        return True, 'совпали слова: ' + ','.join(если[:4])
    if len(значимые) == 1 and len(значимые[0]) >= 8:
        return True, 'совпало редкое слово: ' + значимые[0]
    return False, 'нет совпадения (обладатель: %s)' % (assignee or '')[:60]


def xhr(запрос, стр=0):
    вн = 'q=' + запрос + ('&page=%d' % стр if стр else '')
    u = ('https://patents.google.com/xhr/query?url='
         + urllib.parse.quote(вн, safe='') + '&exp=')
    try:
        h, _m, _meta = VC._fetch(u)
    except Exception:  # noqa: BLE001
        return [], 'ошибка сети'
    if not h:
        return [], 'пустой ответ'
    if not h.lstrip().startswith('{'):
        return [], 'не JSON: ' + h.lstrip()[:60]
    try:
        j = json.loads(h)
    except Exception:  # noqa: BLE001
        return [], 'сбой JSON'
    кл = (j.get('results') or {}).get('cluster') or []
    рез = []
    for c in кл:
        рез += (c.get('result') or [])
    return норм(рез), 'всего=%s' % ((j.get('results') or {}).get('total_num_results'),)


def норм(рез):
    из = []
    for r in рез:
        p = r.get('patent') or {}
        из.append({'pn': p.get('publication_number') or '',
                   'assignee': p.get('assignee') or '',
                   'inv1': p.get('inventor') or '',
                   'title': (p.get('title') or '')[:70]})
    return из


_ЧИСТКА = re.compile(r'&#\d+;|\(RU\)|\(SU\)|\(US\)')


def авторы_страницы(pn):
    """ПОЛНЫЙ список авторов + патентообладатель со страницы патента."""
    u = 'https://patents.google.com/patent/%s/ru' % pn
    try:
        h, _m, _meta = VC._fetch(u)
    except Exception:  # noqa: BLE001
        return [], '', 'ошибка сети'
    t = EC._текст(h or '')
    if not t:
        return [], '', 'пустой текст (html %d)' % len(h or '')
    m = re.search(r'\bInventor\b(.{0,1200}?)(?:Original|Current)\s+Assignee', t, re.S)
    блок = m.group(1) if m else ''
    m2 = re.search(r'(?:Original|Current)\s+Assignee(.{0,400}?)'
                   r'(?:Priority date|Application|Publication|Legal|Info)', t, re.S)
    обл = _ЧИСТКА.sub('"', m2.group(1)).strip() if m2 else ''
    обл = re.sub(r'\s+', ' ', обл).replace('""', '"')
    # на странице каждое имя идёт дважды: «И.И. Иванов (RU) И.И. Иванов»
    имена, было = [], set()
    for кус in re.split(r'\(RU\)|\(SU\)|\(US\)|\(DE\)', блок):
        кус = re.sub(r'\s+', ' ', _ЧИСТКА.sub(' ', кус)).strip()
        if not кус or len(кус) < 5:
            continue
        for имя in re.findall(
                r'[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2}|'
                r'[А-ЯЁ]\.\s*[А-ЯЁ]\.\s*[А-ЯЁ][а-яё]+|'
                r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.', кус):
            к = re.sub(r'\s+', ' ', имя).strip()
            если = к.lower().replace('.', '').replace(' ', '')
            if если not in было and len(к) > 6:
                было.add(если)
                имена.append(к)
    return имена, обл, 'ок'


def сделано():
    было = set()
    if os.path.exists(ПОТОК):
        for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                было.add(str(json.loads(ln).get('inn')))
            except Exception:  # noqa: BLE001
                pass
    return было


def компания(inn, имя):
    сл = ключи(имя)
    рез, инфо = xhr('"%s"' % имя)
    out = {'inn': inn, 'имя': имя, 'xhr': инфо, 'найдено_в_выдаче': len(рез),
           'свои_патенты': [], 'чужие': 0, 'авторы': [], 'примеры': []}
    свои = []
    for r in рез:
        да, почему = свой(r['assignee'], сл, имя)
        if да:
            свои.append((r, почему))
        else:
            out['чужие'] += 1
    out['свои_патенты'] = [r['pn'] for r, _ in свои]
    # полный состав авторов — только по СВОИМ патентам, не больше 5 страниц
    было = set()
    for r, почему in свои[:5]:
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            out['оборвано'] = True
            break
        имена, обл, статус = авторы_страницы(r['pn'])
        да2, почему2 = свой(обл or r['assignee'], сл, имя)
        if not да2:
            out['чужие'] += 1
            continue
        for ч in имена:
            если = ч.lower().replace('.', '').replace(' ', '')
            if если in было:
                continue
            было.add(если)
            out['авторы'].append(ч)
            if len(out['примеры']) < 6:
                out['примеры'].append(
                    {'фио': ч, 'патент': r['pn'], 'обладатель': (обл or '')[:80],
                     'основание': почему2, 'название': r['title'],
                     'ссылка': 'https://patents.google.com/patent/%s/ru' % r['pn']})
        time.sleep(0.3)
    out['авторов'] = len(out['авторы'])
    return out


def main():
    гот = сделано()
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    прошло = 0
    for inn, имя in ВЫБОРКА:
        if inn in гот:
            continue
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            break
        try:
            r = компания(inn, имя)
        except Exception as ex:  # noqa: BLE001
            r = {'inn': inn, 'имя': имя, 'ошибка': '%s: %s' % (type(ex).__name__,
                                                               str(ex)[:90])}
        ф.write(json.dumps(r, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
        прошло += 1
        print('OK', inn, имя, '| патентов своих', len(r.get('свои_патенты') or []),
              '| авторов', r.get('авторов', 0), '| чужих', r.get('чужие'),
              '|', r.get('xhr') or r.get('ошибка'))
    ф.close()
    гот2 = сделано()
    print('ПРОГРЕСС: за проход %d, всего %d из %d' % (прошло, len(гот2), len(ВЫБОРКА)))


if __name__ == '__main__':
    main()
