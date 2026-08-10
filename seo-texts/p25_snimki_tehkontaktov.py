# -*- coding: utf-8 -*-
"""СНИМОК ДОКАЗАТЕЛЬСТВА У КАЖДОГО ТЕХКОНТАКТА. Владелец просил провалиться в каждый.

Повод — разобранный случай: Зайнуллин, 8-950-940-37-30, «главный инженер» у ЛУКОЙЛ-Западная
Сибирь. Снимок документа показал, что номер стоит в блоке ИСПОЛНИТЕЛЯ (ООО ПЦ УГНТУ
«НЕФТЕГАЗИНЖИНИРИНГ», ИНН 0277928462), а не заказчика, и последняя цифра в базе перебита
(в документе 37-31, у меня 37-30). Ни один прежний заслон этого не ловил: номер встречается
один раз, страница живая, цитата честная.

Здесь каждому техконтакту делается СНИМОК его доказательства и кладётся на дроп рядом с
данными. Снимок нужен затем, что глазами видно то, чего не видит ни один шаблон: чей это
блок, стоит ли номер рядом с именем, не подпись ли это чужой организации.

ЧТО СЧИТАЕТСЯ ТЕХКОНТАКТОМ: человек с названной технической должностью (главный инженер,
энергетик, механик, начальник цеха/КС, снабжение, закупки) и с номером.

Снимок делает серверный `browser_probe`, он же кладёт PNG на дроп. Я записываю рядом:
    inn, человек, должность, номер, ссылка, имя файла снимка, что ВИДНО на снимке
Последнее поле заполняется отдельным проходом — глазами, по десятку за раз.

ПОТОКИ: пробы идут в несколько заданий одновременно. Это не дельфин (там профиль один на
сессию и параллель даёт HTTP 500) — это обычный chromium, его можно звать параллельно.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(DIR, 'server', 'run_on_server.py')
SCRATCH = os.environ.get('P25_SCRATCH', '.')
VHOD = os.path.join(SCRATCH, 'PARK-SPISOK-DLYA-ZVONKA-3S.csv')
VYHOD = os.path.join(SCRATCH, 'PARK-SNIMKI-TEHKONTAKTOV-3S.jsonl')
SKOLKO = int(os.environ.get('P25_SKOLKO', '24'))
POTOKOV = int(os.environ.get('P25_POTOKOV', '4'))
TEH = re.compile(r'главн\w+ (инженер|энергетик|механик)|начальник|инженер|энергетик|механик|'
                 r'снабжен|закупк|технич|контактн\w+ лиц|ответственн', re.I)
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def chitat(put):
    out, sh = [], None
    for s in io.open(put, encoding='utf-8-sig'):
        p = s.rstrip('\n').split(';')
        if sh is None:
            sh = p
            continue
        if len(p) == len(sh):
            out.append(dict(zip(sh, p)))
    return out


def kodirovat(u):
    """Кириллица в адресе валит проверяльщик на 'ascii' codec — кодирую перед пробой."""
    try:
        p = urllib.parse.urlsplit(u)
        host = p.netloc
        if re.search(r'[^\x00-\x7F]', host):
            host = host.encode('idna').decode('ascii')
        return urllib.parse.urlunsplit((p.scheme, host,
                                        urllib.parse.quote(p.path, safe="/%:@&=+$,~!*'()"),
                                        urllib.parse.quote(p.query, safe="/%:@&=+$,?~!*'()"),
                                        ''))
    except Exception:  # noqa: BLE001
        return u


# ПЕРЕСНЯТЬ ЗАНОВО. Первые 36 снимков считаны негодной меркой (text_snippet обрезан до
# 600 знаков), и пропускать их как «уже сделанные» значит закрепить враньё. При P25_ZANOVO=1
# прежние строки не считаются сделанными, но и не теряются: они переписываются новым замером.
ZANOVO = os.environ.get('P25_ZANOVO') == '1'
uzhe = {}
if os.path.exists(VYHOD) and not ZANOVO:
    for s in io.open(VYHOD, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        uzhe[(o.get('inn'), o.get('nomer'))] = o

celi = []
for r in chitat(VHOD):
    if not TEH.search(r.get('dolzhnost') or ''):
        continue
    u = next((x for x in (r.get('ssylka_chelovek') or '').split(' | ')
              if x.startswith('http')), '')
    if not u:
        continue
    if (r['inn'], r.get('nomer')) in uzhe:
        continue
    celi.append((r, kodirovat(u)))
celi = celi[:SKOLKO]

zamok = threading.Lock()
ochered = list(celi)
gotovo, prichiny = [], collections.Counter()


def odin(r, u):
    # ВИДИМЫЙ ТЕКСТ БЕРЁТСЯ У САМОЙ СТРАНИЦЫ, а не из `text_snippet`. Замер: это поле
    # обрезано до 600 знаков, то есть по нему проверялась ШАПКА, и «глазами не видно»
    # выходило почти всегда. Мерка, которая обязана врать в одну сторону, — не мерка.
    # `eval_js` возвращает `document.body.innerText` целиком.
    args = {'url': u, 'screenshot': True, 'return_html': True, 'html_cap': 300000,
            'wait_ms': 18000, 'proxy': False, 'ignore_https_errors': True,
            'eval_js': {'return': 'document.body ? document.body.innerText : ""',
                        'after_ms': 300}}
    try:
        p = subprocess.run([sys.executable, RUNNER, 'browser_probe',
                            json.dumps(args, ensure_ascii=False)],
                           capture_output=True, timeout=420)
        s = p.stdout.decode('utf-8', 'replace')
        d = json.loads(s[s.find('{'):]).get('data') or {}
    except Exception as e:  # noqa: BLE001
        with zamok:
            prichiny['проба не выполнилась: %s' % str(e)[:30]] += 1
        return
    snimok = d.get('screenshot_drop') or ''
    html = d.get('html') or ''
    # ДВА УРОВНЯ, И ОНИ НЕ РАВНЫ. Первый заход написал «привязка подтверждается» по
    # совпадению в РАЗМЕТКЕ — а снимок показал тендер «демонтаж недостроенного здания»
    # ООО «Сибэлектро», где ни фамилии, ни номера в видимой части нет: они лежали в блоке
    # «другие тендеры компании». Разметка содержит чужое, видимый текст — то, что читает
    # человек. Поэтому меряю оба и называю их разными словами.
    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))
    vidimo = re.sub(r'\s+', ' ', str(d.get('eval_js_value')
                                     or d.get('text_snippet') or ''))
    nom = re.sub(r'\D', '', r.get('nomer') or '')[-10:]
    fam = (r.get('chelovek') or '').split(' ')[0]
    est_nom = bool(nom) and nom in re.sub(r'\D', '', t)
    est_fam = bool(fam) and len(fam) > 3 and fam.lower() in t.lower()
    vid_nom = bool(nom) and nom in re.sub(r'\D', '', vidimo)
    vid_fam = bool(fam) and len(fam) > 3 and fam.lower() in vidimo.lower()
    est_inn = r['inn'] in re.sub(r'\D', '', t)
    # ПРИЗНАК ЧУЖОГО БЛОКА: на странице названы и заказчик, и исполнитель
    dva_bloka = bool(re.search(r'исполнител|подрядчик|проектная организация', t, re.I)) and \
        bool(re.search(r'заказчик|застройщик', t, re.I))
    with zamok:
        gotovo.append({'inn': r['inn'], 'predpriyatie': (r.get('predpriyatie') or '')[:90],
                       'chelovek': r.get('chelovek', ''), 'dolzhnost': r.get('dolzhnost', ''),
                       'nomer': r.get('nomer', ''), 'ssylka': u,
                       'snimok': snimok,
                       'na_stranice_nomer': est_nom, 'na_stranice_familiya': est_fam,
                       'na_stranice_inn': est_inn,
                       'dva_bloka_zakazchik_i_ispolnitel': dva_bloka,
                       'v_vidimom_tekste_nomer': vid_nom,
                       'v_vidimom_tekste_familiya': vid_fam,
                       'vyvod_pribora': ('видно глазами: номер и фамилия в тексте страницы'
                                         if vid_nom and vid_fam else
                                         ('совпало только в РАЗМЕТКЕ — глазами не видно, '
                                          'нужен снимок' if est_nom and est_fam else
                                          ('номер есть, фамилии нет' if est_nom else
                                           ('фамилия есть, номера нет' if est_fam else
                                            'на странице нет ни номера, ни фамилии')))),
                       # видимый текст кладу в запись: по нему проверяется
                       # третий вопрос — стоит ли на той же странице НАША машина
                       'vidimyy_tekst': vidimo[:4000],
                       'glazami': ''})
        prichiny['снимок сделан' if snimok else 'снимок НЕ сделан'] += 1
        if dva_bloka:
            prichiny['ВНИМАНИЕ: на странице два блока (заказчик и исполнитель)'] += 1


def rabotnik():
    while True:
        with zamok:
            if not ochered:
                return
            r, u = ochered.pop(0)
        try:
            odin(r, u)
        except Exception as e:  # noqa: BLE001
            with zamok:
                prichiny['исключение: %s' % str(e)[:30]] += 1


nitki = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in nitki:
    n.start()
for n in nitki:
    n.join()

vse = list(uzhe.values()) + gotovo
with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in vse:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=240).read().decode('utf-8', 'replace')[:80]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:60]

print('\n\n########## ЧТО ВЫШЛО, ПО ОДНОМУ')
for o in gotovo[:12]:
    print('  %-12s %-22s %-14s %s' % (o['inn'], o['chelovek'][:22], o['nomer'],
                                      o['vyvod_pribora'][:44]))
    print('        снимок: %s' % (o['snimok'] or '—'))
print('\n########## ЧИСЛА')
print('  техконтактов в списке для снимков  %5d' % len(celi))
print('  снято за этот заход                %5d  (всего в файле %d)' % (len(gotovo), len(vse)))
sv = collections.Counter(o['vyvod_pribora'] for o in gotovo)
for k, v in sv.most_common():
    print('     %-56s %5d' % (k[:56], v))
for k, v in prichiny.most_common():
    print('     %-56s %5d' % (k[:56], v))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'снято': len(gotovo), 'всего': len(vse),
                            'исходы': dict(sv)}, ensure_ascii=False))
