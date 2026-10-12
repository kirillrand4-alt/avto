# -*- coding: utf-8 -*-
# 12.10, владелец: «если будет дешевле 150$ то делаем» — замер 50: $0,0047 на компанию, на 11 167 бедных+средних ≈ $52.
# ПЕРЕСБОРКА ПАСПОРТОВ бедных (1–2 поля) и средних (3–4) с сайтом, открытым переобходом; бедные первыми; пачками по 300,
# после каждой пачки — отметка (резюм) и сводка «было/стало»; токены по моделям — в лог. Страницы — как в пробе 200:
# 12.10, владелец: «пробу паспортов на 200 делай». 100 компаний без паспорта + 100 с бедным (1–2 поля из 8), у всех
# сайт открыт серверным переобходом (логика кубика: каталог, производство, качество, экспорт…). Паспорт собирается
# site_facts.sobrat (провайдер), но страницы — СНАЧАЛА новые из папок Зенки (razobrano/gotovo, порядок кубика), потом
# прежние из кэша: в кэш приёмник кладёт не больше 2,5 МБ (старые первыми), а _stranicy берёт первые 60 тыс. знаков —
# новые страницы фактов туда не попадали. Новые факты сливаются со старыми (site_facts._sliyanie). Общий файл
# meyer7-pasport.jsonl НЕ перезаписывается; итог — meyer7-pasport-proba200.jsonl (было/стало) и сводка в логе.
import io, json, os, random, re, subprocess, sys, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'pereborka_pasportov_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                             stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(60)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                     ensure_ascii=False))
    sys.exit(0)

import pilot_konveyer as PK  # noqa: E402
os.environ.update(PK.Волны().env_шага('pilot_pasport.py'))
import pilot_pasport as PP  # noqa: E402  (транспорт к провайдеру кусками, имя файла кэша)
import kc_skrytye as KS  # noqa: E402  (индекс папок Зенки)
SF = PP.SF
ПОЛЯ = ('продукция', 'сырьё', 'мощности', 'контроль_качества', 'оборудование_линии', 'упаковка_фасовка', 'экспорт', 'масштаб')


def полей(ф):
    return sum(1 for п in ПОЛЯ if isinstance(ф, dict) and not SF._pusto(ф.get(п)))


def элементов(ф):
    return sum(len(ф.get(п)) if isinstance(ф.get(п), list) else (1 if ф.get(п) else 0) for п in ПОЛЯ) if isinstance(ф, dict) else 0


# выборка
карта = json.load(io.open(os.path.join(DIR, 'meyer7-zenno-surrogat.json'), encoding='utf-8'))
сур = {}
for кл, i in карта.items():
    сур.setdefault(i, []).append(кл)
import glob  # noqa: E402
откр = set()
for f in [os.path.join(DIR, 'meyer7-server-obhod.jsonl')] + sorted(glob.glob(os.path.join(DIR, 'meyer7-server-obhod-d*.jsonl'))):
    for s in io.open(f, encoding='utf-8', errors='replace'):
        try:
            r = json.loads(s)
        except ValueError:
            continue
        if r.get('итог') == 'открыт':
            откр.add(карта.get(r['ключ'], r['ключ']))
сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))['компании']
import sqlite3  # noqa: E402
ro = sqlite3.connect('file:%s?mode=ro' % SF.BD.replace('\\', '/'), uri=True, timeout=60)
было = {}
for inn, fj in ro.execute("select inn, facts_json from site_facts"):
    try:
        было[str(inn)] = json.loads(fj) if fj else {}
    except ValueError:
        было[str(inn)] = {}
ro.close()
СДЕЛАНО = os.path.join(DIR, 'meyer7-pereborka-pasportov-sdelano.txt')
уже = set(io.open(СДЕЛАНО, encoding='utf-8').read().split()) if os.path.exists(СДЕЛАНО) else set()
for ф_ in ('meyer7-pasport-proba200.jsonl', 'meyer7-pasport-zamer50.jsonl'):
    if os.path.exists(os.path.join(DIR, ф_)):
        уже |= {json.loads(s_)['inn'] for s_ in io.open(os.path.join(DIR, ф_), encoding='utf-8') if s_.strip()}
нет = [i for i in сп if i in откр and сп[i].get('сайт') and 1 <= полей(было.get(i) or {}) <= 2 and i not in уже]
бедн = [i for i in сп if i in откр and сп[i].get('сайт') and 3 <= полей(было.get(i) or {}) <= 4 and i not in уже]
выб = нет + бедн
print('к пересборке: бедных', len(нет), 'средних', len(бедн), '| уже сделано', len(уже), flush=True)
import gen_provider as GP  # noqa: E402
import threading  # noqa: E402
ТОК, _лок_т, _call_исх = {}, threading.Lock(), GP.call


def _call_счёт(client, messages, model='?', *a, **k):
    msg = _call_исх(client, messages, model, *a, **k)
    try:
        u = msg.usage
        with _лок_т:
            т = ТОК.setdefault(model, [0, 0, 0])
            т[0] += (u.input_tokens or 0) + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
            т[1] += u.output_tokens or 0
            т[2] += 1
    except Exception:  # noqa: BLE001
        pass
    return msg


GP.call = _call_счёт
ЦЕНА = {'gpt-5.6-luna': (0.1, 6), 'gpt-6-luna': (0.05, 5), 'claude-haiku-4-5': (0.5, 5), 'claude-haiku-5-5': (0.05, 5)}


def стоимость():
    return sum((вх * ЦЕНА.get(м, (0.1, 6))[0] + вых * ЦЕНА.get(м, (0.1, 6))[0] * ЦЕНА.get(м, (0.1, 6))[1]) * 2 / 1e6
               for м, (вх, вых, n) in ТОК.items())


# страницы: новые (папки Зенки) первыми, потом кэш
ключи = set(выб) | {кл for i in выб for кл in сур.get(i, [])}
инд = KS.индекс_разобрано(ключи)
_стр_кэш, _сыр_кэш = SF._stranicy, SF._syrye_stranicy


def _новые(inn):
    out = []
    for кл in [inn] + сур.get(inn, []):
        out += [(x['url'], x['html']) for x in KS.страницы_разобрано(кл, инд)]
    return out


def _сырые(inn):
    """[(url, html)]: новые страницы переобхода (папки Зенки, порядок кубика) первыми, потом прежние из кэша."""
    сырые = _новые(inn)
    были = {u for u, _ in сырые}
    return сырые + [(u, h) for u, h in PP._сыр_исх(PP._имя_кэша(inn)) if u not in были]


def стр_вместе(inn, predel_znakov=60000):
    """То же, что site_facts._stranicy, но по объединённому списку (без подмены общей папки кэша — потоки)."""
    out, vsego = [], 0
    for u, h in _сырые(inn):
        if not h:
            continue
        t = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', h[:600000], flags=re.S | re.I)
        t = SF._ssylki_v_tekst(t, u or '')
        t = re.sub(r'<[^>]+>', ' ', t)
        for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"'), ('&laquo;', '«'), ('&raquo;', '»'), ('&mdash;', '-')):
            t = t.replace(a, b)
        t = re.sub(r'\s+', ' ', t).strip()
        if len(t) < 200:
            continue
        kusok = t[:8000]
        if vsego + len(kusok) > predel_znakov:
            break
        vsego += len(kusok)
        out.append((u or '', kusok))
    return out


SF._stranicy = lambda inn, *a, **k: стр_вместе(inn, *a, **k)
SF._syrye_stranicy = lambda inn: _сырые(inn)
ПАЧКА = 300
сч = {'компаний': 0, 'полей_было': 0, 'полей_стало': 0, 'выросло': 0, 'стало_3+': 0, 'стало_5+': 0, 'было_3+': 0, 'было_5+': 0}
t0 = time.time()
for k in range(0, len(выб), ПАЧКА):
    пачка = выб[k:k + ПАЧКА]
    список = [{'inn': i, 'name': сп[i].get('имя') or '', 'site': сп[i]['сайт'], 'pererazbor': True} for i in пачка]
    итог = SF.sobrat(predel=len(список), spisok=список, potokov=int(os.environ.get('PASPORT_POTOKOV', '32')))
    ro = sqlite3.connect('file:%s?mode=ro' % SF.BD.replace('\\', '/'), uri=True, timeout=60)
    with io.open(СДЕЛАНО, 'a', encoding='utf-8') as f_сд:
        for i in пачка:
            р = ro.execute('select facts_json from site_facts where inn=?', (i,)).fetchone()
            try:
                b = json.loads(р[0]) if р and р[0] else {}
            except ValueError:
                b = {}
            a = было.get(i) or {}
            сч['компаний'] += 1
            сч['полей_было'] += полей(a)
            сч['полей_стало'] += полей(b)
            сч['выросло'] += полей(b) > полей(a)
            сч['было_3+'] += полей(a) >= 3
            сч['стало_3+'] += полей(b) >= 3
            сч['было_5+'] += полей(a) >= 5
            сч['стало_5+'] += полей(b) >= 5
            if (итог or {}).get('отложено_до_оживания_провайдера', 0) == 0 or полей(b) != полей(a):
                f_сд.write(i + '\n')
        f_сд.flush()
        os.fsync(f_сд.fileno())
    ro.close()
    print(time.strftime('%H:%M:%S'), 'пачка %d-%d из %d' % (k, k + len(пачка), len(выб)), json.dumps(итог, ensure_ascii=False)[:200],
          '| итого', json.dumps(сч, ensure_ascii=False), '| $%.2f' % стоимость(), '| %.0f мин' % ((time.time() - t0) / 60), flush=True)
for м, (вх, вых, n) in ТОК.items():
    print('модель', м, 'вызовов', n, 'вход', вх, 'выход', вых, flush=True)
print('===ИТОГ ПЕРЕСБОРКИ===', json.dumps(сч, ensure_ascii=False), '$%.2f' % стоимость(), flush=True)
