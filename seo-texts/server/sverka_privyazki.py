# -*- coding: utf-8 -*-
r"""Сверка привязки САЙТ ↔ ИНН по уликам на самих страницах.

Зачем. Соседняя сессия 16.08 прислала сигнал: паспорт ИНН 7716929406 («Трастметалл»,
по ЕГРЮЛ утилизация вторсырья) описывал промышленные швейные машины — обход ушёл на
чужой домен, и письмо про рентген чуть не уехало швейному дилеру. Просьба: прогнать
проверку по свежей партии, ошибка может быть не одна.

Нашлось хуже, чем один случай: у той компании флаг verified='mismatch' В БАЗЕ УЖЕ
СТОЯЛ — его ставит обогащение, — но сбор фактов про этот флаг не знал и собрал
паспорт. Таких паспортов 650.

Слепо чистить по флагу нельзя: он мнение модели-судьи, и в выборке сразу видно
ложные срабатывания (ferrozink.ru у ООО «Феррроцинк-Дон» — привязка верная).
Поэтому здесь улики, а не мнения, и все три — из текста самих страниц:

    инн     — ИНН компании напечатан на сайте (футер, контакты, реквизиты);
    огрн    — то же для ОГРН;
    имя     — ядро названия («трастметалл») встречается на страницах;
    домен   — ядро названия совпадает с доменом, в том числе транслитом
              (транс/транc, ч/ch, щ/sch — таблица ниже).

Улика найдена — привязка ПОДТВЕРЖДЕНА, что бы ни думал судья. Ни одной улики и
флаг mismatch — привязка ОТКЛОНЕНА: паспорт уезжает в карантин (колонка
otkloneno_json), facts_json пустеет, письма его больше не увидят. Данные не
удаляем: вернуть можно одной командой, если привязку починят.

    python sverka_privyazki.py --stat        что покажет проверка (ничего не меняя)
    python sverka_privyazki.py --primenit    отклонённые — в карантин
    python sverka_privyazki.py --verdikt     снять mismatch там, где ИНН/ОГРН на сайте
    python sverka_privyazki.py --vernut ИНН  достать паспорт из карантина
"""
import gzip
import json
import os
import re
import sqlite3
import sys

KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')

# транслитерация для сверки имени с доменом: длинные сочетания первыми
ТРАНСЛИТ = [('щ', 'sch'), ('ш', 'sh'), ('ч', 'ch'), ('ж', 'zh'), ('ю', 'yu'),
            ('я', 'ya'), ('ё', 'e'), ('й', 'y'), ('ц', 'c'), ('х', 'h'),
            ('э', 'e'), ('ы', 'y'), ('а', 'a'), ('б', 'b'), ('в', 'v'),
            ('г', 'g'), ('д', 'd'), ('е', 'e'), ('з', 'z'), ('и', 'i'),
            ('к', 'k'), ('л', 'l'), ('м', 'm'), ('н', 'n'), ('о', 'o'),
            ('п', 'p'), ('р', 'r'), ('с', 's'), ('т', 't'), ('у', 'u'),
            ('ф', 'f'), ('ь', ''), ('ъ', '')]
_ФОРМА = re.compile(r'\b(ооо|оао|зао|пао|ао|ип|нао|общество|с|ограниченной|'
                    r'ответственностью|акционерное|публичное|непубличное|'
                    r'управляющая|компания|производственная|торговый|дом|'
                    r'группа|завод|фирма|нпо|нпп|тд|пкф|гк)\b')


def _tekst(inn):
    p = os.path.join(KESH, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return ''
    try:
        d = json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return ''
    куски = []
    for pg in (d.get('pages') or []):
        h = pg.get('html') or ''
        h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
        куски.append(re.sub(r'<[^>]+>', ' ', h))
    return re.sub(r'\s+', ' ', ' '.join(куски).lower().replace('ё', 'е'))


def _ядро(имя):
    """Название без организационной формы и кавычек: «ООО ТД «Трастметалл»» → трастметалл."""
    s = (имя or '').lower().replace('ё', 'е')
    s = re.sub(r'[«»"\'()]', ' ', s)
    s = _ФОРМА.sub(' ', s)
    s = re.sub(r'[^a-zа-я0-9 -]', ' ', s)
    части = [ч for ч in s.split() if len(ч) >= 4]
    return max(части, key=len) if части else ''


# буквы, которые на сайтах пишут латиницей по-разному: ферроцинк живёт на
# ferrozink.ru, а не на ferrocink.ru. Варианты перебираем ЯВНО и сверяем точным
# вхождением. Похожесть «на глазок» тут запрещена: trast и trans отличаются одной
# буквой, и именно на этой паре обход ушёл на чужой сайт — ради чего всё и затеяно.
_НЕОДНОЗНАЧНЫЕ = {'ц': ('c', 'z', 'ts'), 'к': ('k', 'c'), 'х': ('h', 'kh'),
                  'ж': ('zh', 'j'), 'й': ('y', 'i'), 'ы': ('y', 'i'),
                  'я': ('ya', 'ia'), 'ю': ('yu', 'iu'), 'щ': ('sch', 'shch'),
                  'в': ('v', 'w'), 'и': ('i', 'y')}
_ПРОСТО = dict(ТРАНСЛИТ)


def _translit(s):
    for a, b in ТРАНСЛИТ:
        s = s.replace(a, b)
    return re.sub(r'[^a-z0-9]', '', s)


def _варианты(s, предел=32):
    """Все разумные латинские написания слова — перебором неоднозначных букв."""
    вар = ['']
    for ch in s:
        альт = _НЕОДНОЗНАЧНЫЕ.get(ch)
        if not альт or len(вар) * len(альт) > предел:
            альт = (_ПРОСТО.get(ch, ch if ch.isalnum() else ''),)
        вар = [в + a for в in вар for a in альт]
    return {re.sub(r'[^a-z0-9]', '', в) for в in вар if len(в) >= 5}


def улики(inn, имя, сайт, ogrn=None, текст=None):
    """Что на страницах доказывает, что сайт принадлежит именно этой компании."""
    t = текст if текст is not None else _tekst(inn)
    найдено = []
    if not t:
        return найдено, 'страниц в кэше нет'
    цифры = re.sub(r'\D', '', t)
    if inn and re.sub(r'\D', '', str(inn)) in цифры:
        найдено.append('инн')
    if ogrn and re.sub(r'\D', '', str(ogrn)) in цифры:
        найдено.append('огрн')
    ядро = _ядро(имя)
    if ядро and len(ядро) >= 4 and ядро in t:
        найдено.append('имя')
    if ядро and сайт:
        домен = re.sub(r'^www\.', '', (сайт or '').lower().split('/')[0])
        основа = re.sub(r'[^a-z0-9]', '', домен.split('.')[0])
        слова = [ядро] + [ч for ч in ядро.split('-') if len(ч) >= 4]
        вар = set()
        for сл in слова:
            вар |= _варианты(сл)
        if основа and any(в in основа or основа in в for в in вар):
            найдено.append('домен')
    return найдено, ''


def _бд():
    c = sqlite3.connect(BD, timeout=60)
    try:
        c.execute('ALTER TABLE site_facts ADD COLUMN otkloneno_json TEXT')
    except Exception:  # noqa: BLE001
        pass
    try:
        c.execute('ALTER TABLE site_facts ADD COLUMN privyazka TEXT')
    except Exception:  # noqa: BLE001
        pass
    return c


def проверить(только_mismatch=True, предел=0):
    """Пройти по паспортам и сказать про каждый, чем подтверждена его привязка."""
    c = _бд()
    c.row_factory = sqlite3.Row
    где = "and k.verified='mismatch'" if только_mismatch else ''
    сql = ("select f.inn, coalesce(k.name,'') name, coalesce(k.site,k.cand_site,'') site, "
           "coalesce(k.ogrn,'') ogrn, coalesce(k.verified,'') verified "
           "from site_facts f join companies k on k.inn=f.inn "
           "where coalesce(f.facts_json,'')<>'' %s order by f.ts desc" % где)
    строки = list(c.execute(сql))
    if предел:
        строки = строки[:предел]
    итог = {'проверено': 0, 'подтверждено': 0, 'отклонено': 0, 'без_страниц': 0,
            'по_уликам': {}, 'отклонённые': []}
    решения = []
    for r in строки:
        найдено, беда = улики(str(r['inn']), r['name'], r['site'], r['ogrn'])
        итог['проверено'] += 1
        if беда:
            итог['без_страниц'] += 1
            continue
        if найдено:
            итог['подтверждено'] += 1
            for у in найдено:
                итог['по_уликам'][у] = итог['по_уликам'].get(у, 0) + 1
            решения.append((str(r['inn']), '+'.join(найдено), False))
        else:
            итог['отклонено'] += 1
            решения.append((str(r['inn']), 'улик нет', True))
            if len(итог['отклонённые']) < 12:
                итог['отклонённые'].append({'инн': str(r['inn']),
                                            'имя': r['name'][:60], 'сайт': r['site']})
    c.close()
    return итог, решения


РЕШЕНИЯ = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sverka_privyazki.jsonl')
ПОДНЯТЫЕ = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'privyazka_podnyatye.jsonl')


def _решения(предел=0):
    """Решения из durable-файла, а если его нет — считаем заново.

    Проход по 650 паспортам читает столько же gzip-кэшей и идёт минуты; результат
    пишем на СЕРВЕР (правило владельца про durability), чтобы применение работало
    по готовому списку и переживало рестарт песочницы.
    """
    if os.path.exists(РЕШЕНИЯ):
        готово = []
        for s in open(РЕШЕНИЯ, encoding='utf-8'):
            s = s.strip()
            if s:
                d = json.loads(s)
                готово.append((d['inn'], d['признак'], d['отклонить']))
        if готово:
            return {'из_файла': len(готово)}, готово
    итог, решения = проверить(только_mismatch=True, предел=предел)
    with open(РЕШЕНИЯ, 'w', encoding='utf-8') as f:
        for inn, признак, отклонить in решения:
            f.write(json.dumps({'inn': inn, 'признак': признак, 'отклонить': отклонить},
                               ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return итог, решения


def применить(предел=0):
    """Отклонённые паспорта — в карантин: facts_json пустеет, текст остаётся рядом."""
    итог, решения = _решения(предел)
    c = _бд()
    убрано = отмечено = 0
    for inn, признак, отклонить in решения:
        if отклонить:
            # rowcount, а не total_changes: второй счётчик копится по соединению
            убрано += c.execute(
                "UPDATE site_facts SET otkloneno_json=facts_json, facts_json='', "
                "privyazka=?, note=? WHERE inn=? AND coalesce(facts_json,'')<>''",
                (признак, 'привязка сайта не подтверждена (verified=mismatch, улик на '
                 'страницах нет) — паспорт в карантине', inn)).rowcount
        else:
            отмечено += c.execute('UPDATE site_facts SET privyazka=? WHERE inn=?',
                                  (признак, inn)).rowcount
    c.commit()
    c.close()
    итог['убрано_в_карантин'] = убрано
    итог['подтверждённых_отмечено'] = отмечено
    return итог


def поднять_вердикт(предел=0):
    """Где на страницах напечатан ИНН или ОГРН — снять клеймо mismatch.

    Иерархия доверия в обогащении уже такая: 'inn' и 'ogrn' — жёсткие улики, они
    стоят выше мнения модели-судьи. Но судья выносил вердикт по тем страницам,
    которые видел ОН, а Зенка потом привезла сайт целиком, вместе со страницей
    реквизитов. Здесь мы и пересматриваем: улика поздняя, но улика.

    Это не косметика: verified='mismatch' выбрасывает почту компании (blocked в
    enrich_contacts), то есть ошибочный флаг стоит нам контактов.
    """
    c = _бд()
    c.row_factory = sqlite3.Row
    строки = list(c.execute(
        "select inn, coalesce(name,'') name, coalesce(site,cand_site,'') site, "
        "coalesce(ogrn,'') ogrn from companies where verified='mismatch'"))
    if предел:
        строки = строки[:предел]
    поднято = {'inn': 0, 'ogrn': 0}
    for r in строки:
        if not os.path.exists(os.path.join(KESH, '%s.json.gz' % r['inn'])):
            continue
        найдено, _ = улики(str(r['inn']), r['name'], r['site'], r['ogrn'])
        жёсткая = 'инн' if 'инн' in найдено else ('огрн' if 'огрн' in найдено else '')
        if not жёсткая:
            continue
        новый = 'inn' if жёсткая == 'инн' else 'ogrn'
        c.execute('UPDATE companies SET verified=? WHERE inn=? AND verified=?',
                  (новый, str(r['inn']), 'mismatch'))
        поднято[новый] += 1
        # пишем поимённо: вердикт меняет судьбу контактов компании, и «кого именно
        # подняли» должно оставаться на сервере, а не только в счётчике ответа
        with open(ПОДНЯТЫЕ, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'inn': str(r['inn']), 'было': 'mismatch',
                                'стало': новый, 'улика': жёсткая},
                               ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    c.commit()
    c.close()
    return {'проверено': len(строки), 'поднято': поднято}


def вернуть(inn):
    c = _бд()
    c.execute("UPDATE site_facts SET facts_json=otkloneno_json, otkloneno_json='', "
              "note='возвращён из карантина вручную' WHERE inn=? "
              "AND coalesce(otkloneno_json,'')<>''", (str(inn),))
    n = c.total_changes
    c.commit()
    c.close()
    return {'возвращено': n}


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        итог, _ = проверить(только_mismatch=True,
                            предел=int(a[1]) if len(a) > 1 else 0)
        print(json.dumps(итог, ensure_ascii=False, indent=1))
    elif a[0] == '--primenit':
        print(json.dumps(применить(int(a[1]) if len(a) > 1 else 0),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--verdikt':
        print(json.dumps(поднять_вердикт(int(a[1]) if len(a) > 1 else 0),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--vernut' and len(a) > 1:
        print(json.dumps(вернуть(a[1]), ensure_ascii=False))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
