# -*- coding: utf-8 -*-
"""Выборочная проверка ТИПА провайдером на блоках, размеченных регэкспом/словарём.
Не переразмечает базу — МЕРЯЕТ долю ошибок по каждому блоку."""
import json, os, re, sys, time, urllib.request
sys.path.insert(0, '/home/user/avto/seo-texts')
from gen_provider import env
_E = env(); _BASE = (_E.get('PROVIDER_BASE_URL') or 'https://router.cheap').rstrip('/')
_KEY = _E['PROVIDER_API_KEY']
_NP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MODEL = os.environ.get('PARK_MODEL', 'gemini-3.5-flash')
D = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(D, 'park_tipy_sverka.jsonl')

PROMPT = """Ты проверяешь РАЗМЕТКУ ТИПА оборудования в базе парка машин.
Компания продаёт: промышленные компрессоры, МКС (МОДУЛЬНЫЕ компрессорные станции),
ПКС (ПЕРЕДВИЖНЫЕ компрессорные станции), генераторы азота и кислорода, ВРУ, воздуходувки.

Даны текст факта и тип, который ему поставили. Скажи, ВЕРЕН ли тип.
  verno   true/false
  tip     правильный тип: компрессор | воздуходувка | турбокомпрессор | нагнетатель | ВРУ |
          генератор азота | генератор кислорода | МКС | ПКС | ресивер | осушитель | ГПА |
          узел: <что это> | НЕ НАША МАШИНА
  pochemu одно короткое предложение

ЧАСТЫЕ ОШИБКИ, которые надо ловить:
* «фонтанная и нагнетательная арматура», «АФК 65х14», «нагнетательная скважина» —
  это НЕФТЕПРОМЫСЕЛ, а не воздуходувка и не нагнетатель -> НЕ НАША МАШИНА;
* трубопроводы, охладители, фильтры, буферные ёмкости, холодильники ступеней —
  это УЗЛЫ машины: тип «узел: <что>», продавать нельзя, но наличие машины доказывают;
* «кислородно-конвертерный цех», конвертер, донная продувка — МЕТАЛЛУРГИЯ;
* завод аммиака/карбамида, азотная кислота, удобрения — ХИМИЯ, не генератор азота;
* буровые станки, осветительные мачты, дизель-генераторы, погрузочно-доставочные
  машины — НЕ НАША МАШИНА, даже если бренд Atlas Copco;
* МКС = модульная (блок-контейнер, БМКС), ПКС = передвижная (XATS, PDS, DCA, ЗИФ-ПВ,
  на шасси, гаражный номер). Не путать.

Ответ — ТОЛЬКО массив JSON: [{"id":1,"verno":true,"tip":"...","pochemu":"..."}]"""

def sprosit(s, popytok=4):
    posl = None
    for n in range(popytok):
        if n: time.sleep(min(60, 8 * 2 ** (n - 1)))
        try:
            body = json.dumps({'model': MODEL, 'stream': False, 'max_tokens': 4000,
                               'messages': [{'role': 'user', 'content': s}]}).encode()
            req = urllib.request.Request(_BASE + '/v1/chat/completions', data=body, headers={
                'Content-Type': 'application/json', 'Authorization': 'Bearer ' + _KEY,
                'User-Agent': 'curl/8.5.0'})
            return json.loads(_NP.open(req, timeout=240).read())['choices'][0]['message']['content']
        except Exception as e: posl = e
    raise posl

zad = json.load(open(os.path.join(D, '_proverka_tipov.json'), encoding='utf-8'))
sdelano = set()
if os.path.exists(OUT):
    for ln in open(OUT, encoding='utf-8'):
        try: sdelano.add(json.loads(ln)['id'])
        except Exception: pass
zad = [z for z in zad if z['id'] not in sdelano]
print('к проверке', len(zad), flush=True)
P = 15
for i in range(0, len(zad), P):
    pach = zad[i:i + P]
    vhod = json.dumps([{'id': z['id'], 'tip_postavlen': z['tip_bylo'], 'tekst': z['tekst']}
                       for z in pach], ensure_ascii=False)
    try:
        t = sprosit(PROMPT + '\n\nВХОД:\n' + vhod)
        m = re.search(r'\[.*\]', t, re.S)
        dan = json.loads(m.group(0)) if m else []
    except Exception as e:
        print('пачка %s СБОЙ %r' % (i, e), flush=True); continue
    kto = {z['id']: z['kto'] for z in pach}
    bylo = {z['id']: z['tip_bylo'] for z in pach}
    with open(OUT, 'a', encoding='utf-8') as f:
        for d in dan:
            d['kto'] = kto.get(d.get('id')); d['tip_bylo'] = bylo.get(d.get('id'))
            f.write(json.dumps(d, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())
    print('пачка %s-%s: %s' % (i, i + len(pach), len(dan)), flush=True)
print('ГОТОВО', flush=True)
