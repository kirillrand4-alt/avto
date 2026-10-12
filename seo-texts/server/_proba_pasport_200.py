# -*- coding: utf-8 -*-
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
    лог = os.path.join(DIR, 'proba_pasport200_%s.log' % time.strftime('%d%m-%H%M'))
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
нет = [i for i in сп if i in откр and сп[i].get('сайт') and полей(было.get(i) or {}) == 0]
бедн = [i for i in сп if i in откр and сп[i].get('сайт') and 1 <= полей(было.get(i) or {}) <= 2]
random.seed(1210)
выб = random.sample(нет, min(100, len(нет))) + random.sample(бедн, min(100, len(бедн)))
print('кандидатов: без паспорта', len(нет), 'бедных', len(бедн), '| в пробе', len(выб), flush=True)

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
список = [{'inn': i, 'name': сп[i].get('имя') or '', 'site': сп[i]['сайт'], 'pererazbor': True} for i in выб]
t0 = time.time()
итог = SF.sobrat(predel=len(список), spisok=список, potokov=8)
print('сбор за %.1f мин' % ((time.time() - t0) / 60), json.dumps(итог, ensure_ascii=False)[:500], flush=True)
ro = sqlite3.connect('file:%s?mode=ro' % SF.BD.replace('\\', '/'), uri=True, timeout=60)
стало = {}
for i in выб:
    р = ro.execute('select facts_json from site_facts where inn=?', (i,)).fetchone()
    try:
        стало[i] = json.loads(р[0]) if р and р[0] else {}
    except ValueError:
        стало[i] = {}
ro.close()
сч = {'группа': {}, 'всего': len(выб)}
with io.open(os.path.join(DIR, 'meyer7-pasport-proba200.jsonl'), 'w', encoding='utf-8') as f:
    for i in выб:
        гр = 'без паспорта' if i in нет else 'бедный'
        a, b = было.get(i) or {}, стало.get(i) or {}
        f.write(json.dumps({'inn': i, 'группа': гр, 'полей_было': полей(a), 'полей_стало': полей(b), 'элементов_было': элементов(a),
                            'элементов_стало': элементов(b), 'паспорт': b}, ensure_ascii=False) + '\n')
        g = сч['группа'].setdefault(гр, {'компаний': 0, 'полей_было': 0, 'полей_стало': 0, 'стал_паспорт': 0, 'стало_3+': 0,
                                          'стало_5+': 0, 'выросло': 0})
        g['компаний'] += 1
        g['полей_было'] += полей(a)
        g['полей_стало'] += полей(b)
        g['стал_паспорт'] += полей(a) == 0 and полей(b) > 0
        g['стало_3+'] += полей(b) >= 3
        g['стало_5+'] += полей(b) >= 5
        g['выросло'] += полей(b) > полей(a)
    f.flush()
    os.fsync(f.fileno())
print('===ИТОГ ПРОБЫ===', json.dumps(сч, ensure_ascii=False), flush=True)
