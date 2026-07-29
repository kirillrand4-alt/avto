# -*- coding: utf-8 -*-
"""АДВЕРСАРИАЛЬНАЯ проверка тезиса «агрегаторы дают ноль контактов».

Задача не подтвердить, а опровергнуть. Поэтому смотрим не то, что вернула
боевая функция, а СЫРОЙ текст страницы: сколько байт пришло, есть ли на листе
почты/телефоны/ФИО ВООБЩЕ, и какими словами подписан контакт — боевой код
знает ровно одну формулировку «Контактное лицо», и если лист пишет
«Ответственный» или «Контактная информация», ноль будет дефектом разбора,
а не пустотой источника.

Запуск: python _ops_check_agg_adv.py [ИНН ...]
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

_ФИО = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
                  r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?')
# все правдоподобные подписи контакта, а не только боевая
ПОДПИСИ = [
    ('боевая_Контактное_лицо', r'Контактн\w+\s+лиц\w+'),
    ('Контактная_информация', r'Контактн\w+\s+информац\w+'),
    ('Контакты', r'\bКонтакты\b'),
    ('Ответственный', r'Ответственн\w+'),
    ('Куратор', r'Куратор\w*'),
    ('Менеджер', r'Менеджер\w*'),
    ('ФИО', r'\bФ\.?И\.?О\.?\b'),
    ('Исполнитель', r'Исполнител\w+'),
    ('Заказчик', r'Заказчик\w*'),
    ('Телефон', r'Телефон\w*|\bтел\.'),
    ('Эл_почта', r'E-?mail|Эл\w*\.?\s*почт\w+|Электронн\w+\s+почт\w+'),
]


def текст(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


def выдача(запрос):
    """Ровно тот же вызов xmlriver, что в боевом коде."""
    import urllib.parse
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return None, 'нет XMLRIVER_USER/KEY'
    u = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
         + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
         + '&query=' + urllib.parse.quote(запрос))
    try:
        return EC._DIRECT.open(u, timeout=35).read().decode('utf-8', 'replace'), ''
    except Exception as ex:  # noqa: BLE001
        return None, f'{type(ex).__name__}: {str(ex)[:80]}'


def ссылки_агрегаторов(xml):
    вс, агг = [], []
    for u in re.findall(r'<url>(.*?)</url>', xml or '', re.S):
        u = u.strip().replace('&amp;', '&')
        вс.append(u)
        d = EC._domain(u)
        if any(d == a or d.endswith('.' + a) for a in EC._АГРЕГАТОРЫ_ТЕНДЕР):
            if u not in агг:
                агг.append(u)
    return вс, агг


def разбор_страницы(u, inn, P):
    P(f'  СТРАНИЦА {u[:120]}')
    h, метод, mt = EC._fetch_site(u)
    if not h:
        P(f'    ПУСТО: {mt.get("error") or mt.get("status") or метод}')
        return {'пусто': 1}
    t = текст(h)
    капча = mt.get('captcha_type') or ''
    P(f'    html={len(h)} текст={len(t)} метод={метод} капча={капча or "нет"} '
      f'инн_на_листе={inn in t}')
    сч = {}
    for имя, rx in ПОДПИСИ:
        сч[имя] = len(re.findall(rx, t, re.I))
    P('    подписи: ' + ', '.join(f'{k}={v}' for k, v in сч.items() if v))
    почты = sorted(set(x.lower() for x in EC.EMAIL_RE.findall(t)))
    свои = [e for e in почты if not EC._is_junk_email(e)
            and not any(a.split('.')[0] in e for a in EC._АГРЕГАТОРЫ_ТЕНДЕР)]
    тел = sorted(set(m.group(0).strip() for m in EC.phones_in(t)))
    P(f'    почт_всего={len(почты)} {почты[:6]}')
    P(f'    почт_после_фильтра_боевого={len(свои)} {свои[:6]}')
    P(f'    телефонов={len(тел)} {тел[:6]}')
    фио = sorted(set(_ФИО.findall(t)))
    P(f'    фио_на_листе={len(фио)} {фио[:8]}')
    # что видит боевая регулярка
    окна = [m.group(1) for m in re.finditer(
        r'Контактн\w+\s+лиц\w+\s*[:\-]?\s*(.{0,260})', t, re.I)]
    P(f'    боевых_окон={len(окна)}')
    for о in окна[:2]:
        P('      окно> ' + о[:240])
    # сырьё вокруг ЛЮБОГО «контакт» — главное доказательство
    for i, m in enumerate(re.finditer(r'онтакт', t)):
        if i >= 2:
            break
        P('      сырьё> ' + t[max(0, m.start() - 60):m.start() + 420])
    # признаки замка
    замки = [с for с in ('зарегистрируйт', 'регистрац', 'авториз', 'войти',
                         'подписк', 'доступ к контакт', 'скрыт', 'платн')
             if с in t.lower()]
    P(f'    замки={замки}')
    return {'почт': len(свои), 'тел': len(тел), 'фио': len(фио),
            'окон': len(окна), 'пусто': 0}


def main():
    буф = []

    def P(s):
        буф.append(str(s))

    инны = [a for a in sys.argv[1:] if a.isdigit()]
    источник = 'аргументы'
    if not инны:
        # ровно та популяция, что дала ноль
        for п in (r'C:\seostat\drop\agg1.jsonl',):
            if os.path.exists(п):
                for ln in io.open(п, encoding='utf-8', errors='replace'):
                    try:
                        x = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    s = str(x.get('inn') or '')
                    if s.isdigit() and s not in инны and not x.get('err'):
                        инны.append(s)
                источник = п
        if not инны:
            п = r'C:\sender\_ops\sales_base.json'
            if os.path.exists(п):
                d = json.load(io.open(п, encoding='utf-8', errors='replace'))
                строки = d if isinstance(d, list) else (d.get('rows') or d.get('items') or [])
                for x in строки:
                    s = str((x or {}).get('inn') or '')
                    if s.isdigit() and s not in инны:
                        инны.append(s)
                источник = п
    P(f'источник ИНН: {источник}, всего {len(инны)}')
    инны = инны[:2]
    итог = {'страниц': 0, 'с_почтой': 0, 'с_телефоном': 0, 'с_фио': 0,
            'боевых_окон': 0, 'боевая_вернула': 0, 'агрегаторов_в_выдаче': 0}
    for inn in инны:
        P(f'=== ИНН {inn} ===')
        xml, ош = выдача(f'{inn} тендер контактное лицо')
        if not xml:
            P(f'  выдача не пришла: {ош}')
            continue
        вс, агг = ссылки_агрегаторов(xml)
        P(f'  ссылок_всего={len(вс)} агрегаторов={len(агг)}')
        P(f'  домены: {sorted(set(EC._domain(u) for u in вс))[:12]}')
        итог['агрегаторов_в_выдаче'] += len(агг)
        for u in агг[:3]:
            r = разбор_страницы(u, inn, P)
            if r.get('пусто'):
                continue
            итог['страниц'] += 1
            итог['с_почтой'] += 1 if r['почт'] else 0
            итог['с_телефоном'] += 1 if r['тел'] else 0
            итог['с_фио'] += 1 if r['фио'] else 0
            итог['боевых_окон'] += r['окон']
        try:
            б = EC.find_tender_aggregator_contacts(inn)
        except Exception as ex:  # noqa: BLE001
            б = f'ОШИБКА {type(ex).__name__}: {str(ex)[:80]}'
        P(f'  БОЕВАЯ ФУНКЦИЯ вернула: {json.dumps(б, ensure_ascii=False)[:300]}')
        if isinstance(б, list):
            итог['боевая_вернула'] += len(б)
    print('\n'.join(буф)[-11000:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
