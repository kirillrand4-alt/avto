# -*- coding: utf-8 -*-
"""Разбор страниц «Вакансии/Карьера» и «О компании/Структура» сайтов предприятий:
кто назван, техническая ли роль, чей телефон.

Зачем провайдер, а не регулярка (правило 6 из задачи): телефон, почта и ИНН имеют
регулярный формат и берутся регуляркой в `razbor.py`; связка «имя — должность — чей
из нескольких номеров» лежит в свободной вёрстке и каждый раз выглядит иначе.

Заслон против выдуманных номеров: после ответа каждый номер сверяется с цифрами
входного текста; номер, которого во входе нет, помечается `telefon_est_v_tekste=нет`
и в список обзвона не идёт.

Вход:  pr3/razbor.json (результат razbor.py) + pr3/pages/*.html
Выход: engineers-lens/centro/dop/lica-stranic.csv
"""
import csv
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import gen_provider as G

MODEL = 'claude-fable-5'
D = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad/pr3'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'engineers-lens', 'centro', 'dop', 'lica-stranic.csv')
TAG = re.compile(r'<[^>]+>')
SCRIPT = re.compile(r'<(script|style)\b.*?</\1>', re.S | re.I)
PH = re.compile(r'(?:\+7|\b8|\b7)[\s\-‐-―().]{0,3}\(?\d{3,5}\)?[\s\-‐-―().]{0,3}'
                r'\d{2,3}[\s\-‐-―().]{0,3}\d{2}[\s\-‐-―().]{0,3}\d{2}\b')
ROL = re.compile(r'(?i)главн\w+\s+(инженер|механик|энергетик)|техническ\w+\s+директор|'
                 r'начальник\w*\s|ОГМ|ОГЭ|КИПиА|энергетик|механик|заместител')


def _env():
    key = os.environ.get('PROVIDER_API_KEY')
    if not key:
        sys.exit('нет PROVIDER_API_KEY в окружении')
    return {'PROVIDER_API_KEY': key,
            'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}


G.env = _env

PROMPT = """Ты разбираешь страницы сайтов российских промышленных предприятий: разделы
«Вакансии/Карьера» и «О компании/Структура/Руководство».

ЗАЧЕМ. ООО «Руспром» продаёт промышленные воздушные центробежные компрессоры и воздуходувки.
Нужен человек, отвечающий за это оборудование: главный инженер, главный механик, главный
энергетик, начальник компрессорной или цеха, их заместители, инженер ОГМ/ОГЭ/КИПиА.
Снабженец (ОМТС, отдел закупок) — тоже полезен, но помечается отдельно и стоит ниже.
Кадровик и рекрутёр — НЕ цель, но его номер надо явно пометить, чтобы он не уехал в
список обзвона как технарь.

ЧТО СДЕЛАТЬ. Для каждой страницы вернуть названных людей И названные подразделения с прямым
телефоном (телефон отдела без имени тоже ценен — это прямой номер в цех, а не приёмная).
Для каждой записи:
- `imya` — ФИО как в тексте; если названо только подразделение — пустая строка;
- `dolzhnost_ili_otdel` — словами ИЗ ТЕКСТА;
- `rol` — одно из: `техническая`, `снабжение`, `кадры`, `руководство`, `неясно`;
- `telefony` — номера ЭТОГО человека или ЭТОГО отдела, ровно как в тексте;
- `pochta` — почта, стоящая рядом;
- `osnovanie` — короткая цитата из текста, по которой видно, чей это номер.

ПРАВИЛА, нарушать нельзя:
1. Ни одного номера, которого нет во входном тексте. Выдуманный номер хуже пропуска.
2. Если людей и отделов с телефонами на странице нет — верни пустой список `lyudi`.
   Не угадывай и не обобщай.
3. Общий номер приёмной, справочной, 8-800 и факс помечай словом «приёмная» в `osnovanie`.
4. «Инженер по закупкам», «инженер отдела снабжения», «инженер-сметчик» — это `снабжение`,
   а не техническая роль.
5. Телефон в тексте вакансии, подписанный отделом кадров, HR, рекрутёром или сторонним
   агентством — `rol` = `кадры`, и это надо написать в `osnovanie`.

ОТВЕТ — строго JSON без пояснений, массив по числу страниц, в том же порядке:
[{"page_id":"...","lyudi":[{"imya":"","dolzhnost_ili_otdel":"","rol":"","telefony":[],
"pochta":"","osnovanie":""}]}]

СТРАНИЦЫ:
"""


def tekst(path):
    b = open(path, 'rb').read()
    for e in ('utf-8', 'cp1251'):
        try:
            s = b.decode(e)
            break
        except Exception:
            s = None
    if s is None:
        s = b.decode('utf-8', 'replace')
    s = SCRIPT.sub(' ', s)
    # строчные теги убираем без пробела: иначе номер, разорванный <span>, распадается
    s = re.sub(r'</?(span|b|strong|em|i|a|font|wbr|nobr|sup|sub|u|small)\b[^>]*>', '', s)
    s = TAG.sub(' ', s)
    s = s.replace('&nbsp;', ' ').replace('&#160;', ' ')
    s = re.sub(r'&[a-z]{2,8};', ' ', s)
    return re.sub(r'[ \t ]+', ' ', s)


def okna(s, limit=7000):
    """Окна вокруг телефонов и должностей — целиком страница не нужна и дорога."""
    poz = [m.start() for m in PH.finditer(s)] + [m.start() for m in ROL.finditer(s)]
    if not poz:
        return ''
    poz.sort()
    sp = []
    for p in poz:
        a, b = max(0, p - 400), p + 400
        if sp and a <= sp[-1][1]:
            sp[-1] = (sp[-1][0], b)
        else:
            sp.append((a, b))
    out = ' […] '.join(s[a:b] for a, b in sp)
    return out[:limit]


def main():
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 5
    pachka = int(sys.argv[sys.argv.index('--pachka') + 1]) if '--pachka' in sys.argv else 3
    rows = json.load(open(D + '/razbor.json'))
    zadachi = []
    for r in rows:
        if not r['tel']:
            continue
        p = os.path.join(D, 'pages', r['file'])
        if not os.path.exists(p):
            continue
        t = okna(tekst(p))
        if not t:
            continue
        zadachi.append({'page_id': r['domain'] + r['path'], 'domain': r['domain'],
                        'path': r['path'], 'tekst': t})
    print(f'страниц к разбору: {len(zadachi)}', file=sys.stderr)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cols = ['domain', 'path', 'imya', 'dolzhnost_ili_otdel', 'rol', 'telefon', 'pochta',
            'osnovanie', 'telefon_est_v_tekste']
    f = open(OUT, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    w.writeheader()
    lock = threading.Lock()
    sch = {'lyudey': 0, 'teh': 0, 'kadry': 0, 'vydumka': 0, 'err': 0}
    client = G.make_client()

    def odna(gr):
        telo = PROMPT
        for z in gr:
            telo += f'\n--- page_id: {z["page_id"]}\nтекст: {z["tekst"]}\n'
        try:
            out = G.call(client, [{'role': 'user', 'content': telo}], model=MODEL, attempts=5)
            txt = ''.join(b.text for b in out.content if b.type == 'text').strip()
        except Exception as e:  # noqa: BLE001
            return gr, None, f'{type(e).__name__}: {str(e)[:90]}'
        m = re.search(r'\[.*\]', txt, re.S)
        if not m:
            return gr, None, 'ответ без JSON'
        try:
            return gr, json.loads(m.group(0)), None
        except Exception as e:  # noqa: BLE001
            return gr, None, f'json: {str(e)[:80]}'

    grs = [zadachi[i:i + pachka] for i in range(0, len(zadachi), pachka)]
    with ThreadPoolExecutor(max_workers=threads) as ex:
        for gr, res, err in ex.map(odna, grs):
            if err:
                with lock:
                    sch['err'] += 1
                print('ошибка:', err, file=sys.stderr)
                continue
            by = {z['page_id']: z for z in gr}
            for item in res or []:
                z = by.get(item.get('page_id')) or (gr[0] if len(gr) == 1 else None)
                if not z:
                    continue
                cifry = re.sub(r'\D', '', z['tekst'])
                for l in item.get('lyudi') or []:
                    tels = l.get('telefony') or ['']
                    for t in tels:
                        d = re.sub(r'\D', '', str(t))
                        est = 'да' if d and (d in cifry or d[1:] in cifry or d[-10:] in cifry) else 'нет'
                        if d and est == 'нет':
                            with lock:
                                sch['vydumka'] += 1
                        with lock:
                            sch['lyudey'] += 1
                            if l.get('rol') == 'техническая':
                                sch['teh'] += 1
                            if l.get('rol') == 'кадры':
                                sch['kadry'] += 1
                            w.writerow({'domain': z['domain'], 'path': z['path'],
                                        'imya': l.get('imya', ''),
                                        'dolzhnost_ili_otdel': l.get('dolzhnost_ili_otdel', ''),
                                        'rol': l.get('rol', ''), 'telefon': t,
                                        'pochta': l.get('pochta', ''),
                                        'osnovanie': (l.get('osnovanie') or '')[:300],
                                        'telefon_est_v_tekste': est})
                            f.flush()
    print(f'записей: {sch["lyudey"]}, техническая роль: {sch["teh"]}, кадры: {sch["kadry"]}, '
          f'номеров не из текста (помечены): {sch["vydumka"]}, ошибок пачек: {sch["err"]}',
          file=sys.stderr)


main()
