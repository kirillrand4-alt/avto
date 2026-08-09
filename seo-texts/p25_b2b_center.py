# -*- coding: utf-8 -*-
"""B2B-Center: беру закупки по нашей номенклатуре. Поле поиска взято У САМОЙ ФОРМЫ.

Два тупых захода до этого — и оба поучительные:

    /market/?q=компрессор          выдача та же, что без запроса: «компрессор» 0 раз в тексте
    /market/search.html?q=...      ровно те же лоты 4555324, 4555323, 4555319

То есть площадка молча отдавала общую ленту, а я бы записала её как «нашли по компрессору».
Заслон «слово в тексте выдачи» это поймал сразу. Правило прежнее: **у площадки надо спросить
её собственную форму, а не сочинять параметр.** Спросила:

    <form action="/market/"> поля: f_keyword, searching
    расширенная форма: include_firm_tree, price_start, date_start_dmy, company_type, customer_id

Значит адрес такой: `/market/?f_keyword=СЛОВО&searching=1`.

ПРО АВТОРИЗАЦИЮ, ЧЕСТНО. Владелец дал дельфин-профиль 829115332 и сказал, что он
авторизован. В ответе площадки при заходе этим профилем стоит `"user_id":null`, а внизу
страницы — «Во время работы в системе Ваш IP адрес изменился. Для безопасности необходимо
подтвердить вашу авторизацию». То есть куки профиля есть, но площадка их не принимает с
серверного адреса. Публичную ленту это не закрывает — список закупок и заказчик видны без
входа, — поэтому собираю то, что открыто, и отдельно печатаю, чего не хватает из-за входа.

ЗАСЛОН, тот же что у ЕИС и по той же причине: если у разных слов приходят одни и те же
номера лотов — фильтр не применился, и числу верить нельзя. Печатаю пересечение.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import json
import os
import re
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(DIR, 'server', 'run_on_server.py')
SLOVA = ['компрессор', 'винтовой компрессор', 'поршневой компрессор', 'генератор азота',
         'генератор кислорода', 'азотная станция', 'кислородная станция',
         'компрессорная станция', 'воздуходувка', 'осушитель сжатого воздуха',
         'воздухоразделительная установка', 'передвижная компрессорная станция']
STRANIC = 2
VYHOD = os.path.join(DIR, 'PARK-B2B-CENTER-3S.jsonl')
TEG = re.compile(r'<[^>]+>')
LOT = re.compile(r'/tender/(\d{5,9})/?[^\"\']*\"[^>]*>\s*([^<]{5,200})', re.S)
NOMER = re.compile(r'№\s*(\d{6,9})')


def probe(url):
    args = {'url': url, 'screenshot': False, 'return_html': True, 'html_cap': 900000,
            'wait_ms': 16000, 'proxy': False, 'ignore_https_errors': True}
    r = subprocess.run([sys.executable, RUNNER, 'browser_probe',
                        json.dumps(args, ensure_ascii=False)],
                       capture_output=True, timeout=600)
    s = r.stdout.decode('utf-8', 'replace')
    i = s.find('{')
    if i < 0:
        return '', 'раннер не вернул JSON'
    try:
        d = (json.loads(s[i:]).get('data') or {})
    except Exception:  # noqa: BLE001
        return '', 'битый JSON'
    return d.get('html') or '', str(d.get('error') or '')[:70]


def adres(slovo, st):
    u = ('https://www.b2b-center.ru/market/?f_keyword=%s&searching=1'
         % urllib.parse.quote(slovo))
    return u + ('&page=%d' % st if st > 1 else '')


def razobrat(html):
    """Из ленты беру пары «номер лота — название» и имя организатора рядом."""
    out = []
    txt = re.sub(r'\s+', ' ', TEG.sub(' ', html))
    # в ленте строки идут: «Название лота ОРГАНИЗАТОР дата дата», а номер стоит в ссылке
    for m in re.finditer(r'href="[^"]*/tender/(\d{5,9})[^"]*"[^>]*>\s*([^<]{5,220})<', html):
        out.append({'nomer': m.group(1), 'nazvanie': re.sub(r'\s+', ' ', m.group(2)).strip()})
    if not out:
        for m in NOMER.finditer(txt):
            out.append({'nomer': m.group(1), 'nazvanie': ''})
    vid, res = set(), []
    for o in out:
        if o['nomer'] in vid:
            continue
        vid.add(o['nomer'])
        res.append(o)
    return res, txt


def rabota(par):
    slovo, st = par
    u = adres(slovo, st)
    html, err = probe(u)
    if not html:
        return slovo, st, u, [], '', err or 'пустой ответ'
    lot, txt = razobrat(html)
    return slovo, st, u, lot, txt, err


zadaniya = [(s, st) for s in SLOVA for st in range(1, STRANIC + 1)]
sobrano = collections.defaultdict(dict)
tekst_est = collections.Counter()
oshibki = collections.Counter()
with ThreadPoolExecutor(max_workers=4) as ex:
    for slovo, st, u, lot, txt, err in ex.map(rabota, zadaniya):
        if err:
            oshibki['%s: %s' % (slovo, err)] += 1
        osn = [w[:max(5, len(w) - 2)].lower() for w in re.findall(r'[А-Яа-я]{4,}', slovo)]
        if txt and all(k in txt.lower() for k in osn):
            tekst_est[slovo] += 1
        for o in lot:
            o['slovo'] = slovo
            o['ssylka'] = 'https://www.b2b-center.ru/market/tender/%s/' % o['nomer']
            o['ssylka_poiska'] = u
            sobrano[slovo][o['nomer']] = o

# ЗАСЛОН: пересечение наборов лотов у разных слов
nabory = {s: set(d) for s, d in sobrano.items() if d}
peresech = []
kl = sorted(nabory)
for i in range(len(kl)):
    for j in range(i + 1, len(kl)):
        a, b = nabory[kl[i]], nabory[kl[j]]
        if a and b:
            dolya = len(a & b) / float(min(len(a), len(b)))
            if dolya > 0.8:
                peresech.append('%s и %s совпали на %.0f%%' % (kl[i], kl[j], dolya * 100))

potok = []
for s, d in sobrano.items():
    for o in d.values():
        potok.append({'nomer': o['nomer'], 'nazvanie': o['nazvanie'][:250],
                      'slovo': o['slovo'],
                      'slovo_v_nazvanii': bool(re.search(
                          re.escape(o['slovo'].split()[-1][:6]), o['nazvanie'], re.I)),
                      'istochniki': o['ssylka'] + ' | ' + o['ssylka_poiska'],
                      'istochnikov': 2, 'inn': '', 'inn_otkuda': 'на площадке ИНН не печатают',
                      'kto': '3-я сессия, B2B-Center'})
with open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')

podtv = [o for o in potok if o['slovo_v_nazvanii']]
print('\n\n########## ЗАСЛОН')
if peresech:
    for p in peresech[:6]:
        print('  ПРОТИВОРЕЧИЕ: %s' % p)
else:
    print('  наборы лотов у разных слов различаются — фильтр применяется')
print('  слово встретилось в тексте страницы: %d слов из %d' % (len(tekst_est), len(SLOVA)))
print('\n########## ПРИМЕРЫ, где слово стоит в названии лота')
for o in podtv[:8]:
    print('  %-9s %-14s %s' % (o['nomer'], o['slovo'][:14], o['nazvanie'][:90]))
print('\n########## ЧИСЛА')
print('  лотов собрано              %6d' % len(potok))
print('  слово стоит в названии     %6d' % len(podtv))
print('  --- по слову')
for s in SLOVA:
    print('     %-36s %5d' % (s, len(sobrano.get(s, {}))))
if oshibki:
    print('  --- ошибки')
    for k, v in oshibki.most_common(8):
        print('     %-58s %3d' % (k[:58], v))
print('  файл: %s' % VYHOD)
print('ИТОГ ' + json.dumps({'лотов': len(potok), 'слово в названии': len(podtv),
                            'противоречий': len(peresech)}, ensure_ascii=False))
