# -*- coding: utf-8 -*-
"""ФИО и должности из НОВОСТЕЙ компании и отраслевой прессы.

Зачем отдельный способ. Структурный разбор берёт человека из блока разметки —
строки таблицы, карточки сотрудника. У завода, чей сайт — каталог продукции, ни
таблиц, ни карточек нет вовсе: у Криогенмаша на сайте нет даже слова
«руководство». Зато в новостях люди названы прозой: «как отметил главный
инженер АО «Криогенмаш» Иванов И. И.». Регулярка тут слабое место — падежи,
кавычки, вставки, — поэтому прозу разбирает модель, что и требует правило
владельца про тяжёлую работу через провайдерский API.

Берём: раздел новостей самого сайта плюс страницы из выдачи по запросам с
названиями технических должностей. Модель возвращает СТРОГО тех, у кого в
тексте названа и должность, и принадлежность ИМЕННО этой компании, — иначе в
базу поедут чиновники и партнёры из того же абзаца.

Запуск: python people_from_news.py ИНН [--apply] [--pages N]
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ИНН = next((a for a in sys.argv[1:] if a.isdigit()), '')
СТРАНИЦ = int(sys.argv[sys.argv.index('--pages') + 1]
              if '--pages' in sys.argv else 18)

db = EDB.EnrichDB()
e = db.cx

_ЗАПРОСЫ = ('{имя} главный инженер', '{имя} технический директор',
            '{имя} главный энергетик', '{имя} начальник производства',
            '{имя} главный механик', '{имя} назначен директором')


def провайдер(промпт):
    """Один вызов провайдерского API стримом (заголовки как в боевом клиенте)."""
    key = os.environ.get('PROVIDER_API_KEY', '')
    if not key:
        return ''
    base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    тело = json.dumps({'model': 'claude-fable-5', 'max_tokens': 1800,
                       'stream': True,
                       'messages': [{'role': 'user', 'content': промпт}]},
                      ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        base + '/v1/messages', data=тело, method='POST',
        headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                 'content-type': 'application/json',
                 'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0'})
    куски = []
    with urllib.request.urlopen(req, timeout=240) as r:
        for сырая in r:
            стр = сырая.decode('utf-8', 'replace').strip()
            if not стр.startswith('data:'):
                continue
            try:
                ev = json.loads(стр[5:].strip())
            except Exception:  # noqa: BLE001
                continue
            if ev.get('type') == 'content_block_delta':
                куски.append((ev.get('delta') or {}).get('text', ''))
    return ''.join(куски)


def серп(запрос, n=8):
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return []
    u = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
         + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
         + '&query=' + urllib.parse.quote(запрос))
    try:
        xml = EC._DIRECT.open(u, timeout=35).read().decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        return []
    return [x.strip().replace('&amp;', '&')
            for x in re.findall(r'<url>(.*?)</url>', xml, re.S)][:n]


def main():
    c = e.execute('SELECT name, site FROM companies WHERE inn=?',
                  (ИНН,)).fetchone()
    имя = (c or ['', ''])[0] or ''
    дом = EC.site_domain((c or ['', ''])[1] or '')
    out = {'инн': ИНН, 'компания': имя, 'домен': дом, 'страниц': 0,
           'символов': 0, 'людей': [], 'записано': 0,
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)'}
    if not имя:
        print(json.dumps({'ошибка': 'нет компании с таким ИНН'},
                         ensure_ascii=False))
        return

    # 1. новости на сайте компании
    адреса = []
    if дом:
        for корень in (f'http://{дом}/news/', f'http://{дом}/press/',
                       f'http://{дом}/company/news/'):
            try:
                h, _m, _mt = EC._fetch_site(корень)
            except Exception:  # noqa: BLE001
                continue
            if not h:
                continue
            адреса.append(корень)
            for u in re.findall(r'href="([^"#]+)"', h):
                if u.startswith('/'):
                    u = f'http://{дом}' + u
                if EC.site_domain(u) == дом and re.search(
                        r'/(news|press|smi)/[^/]+', u) and u not in адреса:
                    адреса.append(u)
    # 2. страницы из выдачи по техническим должностям
    for шаблон in _ЗАПРОСЫ:
        for u in серп(шаблон.format(имя=имя.replace('АКЦИОНЕРНОЕ ОБЩЕСТВО ', '')),
                      6):
            d = EC._domain(u)
            # справочники контрагентов людей не называют, а место в бюджете едят
            if any(k in d for k in ('checko', 'rusprofile', 'list-org', 'audit-it',
                                    'zachestnyibiznes', 'kontur', 'companies.rbc')):
                continue
            if u not in адреса:
                адреса.append(u)
        time.sleep(0.5)

    куски = []
    for u in адреса[:СТРАНИЦ]:
        try:
            h, _m, mt = EC._fetch_site(u)
        except Exception:  # noqa: BLE001
            continue
        if not h or mt.get('captcha_type'):
            continue
        t = EC._текст(h)
        # оставляем только окрестности слов-должностей: иначе в бюджет
        # уезжает каталог продукции, а людей в нём нет
        окна = []
        for m in re.finditer(r'(главн\w+\s+(?:инженер\w*|энергетик\w*|механик\w*|'
                             r'технолог\w*)|техническ\w+\s+директор\w*|'
                             r'начальник\w*\s+\w+|директор\w*|заместител\w+)',
                             t, re.I):
            окна.append(t[max(0, m.start() - 220):m.end() + 260])
        if окна:
            out['страниц'] += 1
            куски.append(f'--- {u}\n' + ' … '.join(окна[:8]))
        time.sleep(0.4)

    текст = '\n'.join(куски)[:22000]
    out['символов'] = len(текст)
    if not текст.strip():
        print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
        return

    промпт = (
        'Ниже куски новостей и публикаций. Найди ЛЮДЕЙ, про которых прямо '
        f'сказано, что они работают в компании «{имя}» (ИНН {ИНН}), и у которых '
        'НАЗВАНА ДОЛЖНОСТЬ. Только эта компания: сотрудников партнёров, '
        'заказчиков, чиновников и журналистов НЕ включай. Если принадлежность '
        'к компании не сказана прямо — пропусти человека. Должность приводи как '
        'в тексте, ФИО в именительном падеже. Верни СТРОГО JSON без markdown: '
        '{"people":[{"person":"Фамилия Имя Отчество","post":"должность",'
        '"quote":"фраза из текста, где это сказано","url":"адрес из строки --- '
        'над куском"}]}\n\n' + текст)
    try:
        ответ = провайдер(промпт)
    except Exception as ex:  # noqa: BLE001
        out['ошибка_провайдера'] = f'{type(ex).__name__}: {str(ex)[:90]}'
        ответ = ''
    m = re.search(r'\{.*\}', ответ or '', re.S)
    данные = {}
    if m:
        try:
            данные = json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            out['ответ_не_json'] = (ответ or '')[:200]
    for ч in (данные.get('people') or []):
        фио = (ч.get('person') or '').strip()
        пост = (ч.get('post') or '').strip()
        if not (фио and пост):
            continue
        роль = EDB.EnrichDB._canon_role(пост)
        out['людей'].append({'фио': фио, 'должность': пост, 'роль': роль,
                             'цитата': (ч.get('quote') or '')[:160],
                             'ссылка': (ч.get('url') or '')[:100]})
        if ПРИМЕНИТЬ:
            db.add_person(ИНН, фио, post=пост, source='новости',
                          source_url=ч.get('url') or '')
            out['записано'] += 1
    if ПРИМЕНИТЬ:
        e.commit()
    out['техЛПР'] = sum(1 for x in out['людей']
                        if x['роль'] in EDB.EnrichDB.TECH_ROLES)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:7000])


if __name__ == '__main__':
    main()
