# -*- coding: utf-8 -*-
# 22.10, владелец: «Цербер вне ФСА» (233 юрлица реестра Цербер, которых нет среди изготовителей ФСА) — «запускай оба»:
# (1) выручка ФНС 2025 (открытые данные revexp.zip, как fsa_fns_dohod) — у набора выручки не было вовсе;
# (2) пропущенный шаг дешёвой схемы: проход по всей базе (_fsa_noch.проход_базы) смотрел только кандидатов из декларации и
#     checko, без запроса xmlriver — у 171 из 233 кандидатов не было. Здесь _fsa_deshevo.одна: те же кандидаты + запрос
#     «ИНН + официальный сайт» -> ИНН на сайте (справочники/агрегаторы отсеиваются). Порядок — от большей выручки.
# (3) подтверждённые сайты (старые + новые) -> набор cerbc -> конвейер (резюм по ИНН: готовые не переделываются).
# Durable: cerb-fns-dohod.jsonl, cerb-sayt-inn.jsonl (дописываем, последняя запись по ИНН — итог), шаги конвейера — свои
# jsonl. Всё -> дроп. Лог: cerb_dobor_*.log.
import io, json, os, shutil, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'cerb_dobor_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_cerb_dobor.py'), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(40)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-700:])
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402
import _fsa_deshevo as D  # noqa: E402
import _fsa_noch as N  # noqa: E402

сп_путь = os.path.join(DIR, 'cerb-spisok.json')
if not os.path.exists(сп_путь):
    shutil.copyfile(os.path.join(ДРОП, 'cerb-spisok.json'), сп_путь)
сп_все = json.load(io.open(сп_путь, encoding='utf-8'))
сп = сп_все['компании']

# (1) выручка ФНС 2025
ФНС = os.path.join(DIR, 'cerb-fns-dohod.jsonl')
д = {}
z = zipfile.ZipFile(r'C:\sender\_ops\ak\fns\revexp.zip')
for zi in z.infolist():
    with z.open(zi) as fh:
        for ev, el in ET.iterparse(fh, events=('end',)):
            if not el.tag.endswith('Документ'):
                continue
            i = v = None
            for ch in el:
                if 'СведНП' in ch.tag:
                    i = ch.get('ИННЮЛ') or ch.get('ИННФЛ')
                elif 'ДохРасх' in ch.tag:
                    v = ch.get('СумДоход')
            if i in сп and v:
                try:
                    д[i] = float(v)
                except ValueError:
                    pass
            el.clear()
with io.open(ФНС, 'w', encoding='utf-8') as f:
    for i, v in д.items():
        f.write(json.dumps({'инн': i, 'доход_2025': v}, ensure_ascii=False) + '\n')
    f.flush()
    os.fsync(f.fileno())
for i, v in д.items():
    сп[i]['выручка'] = v
with open(сп_путь, 'w', encoding='utf-8') as f:
    json.dump(сп_все, f, ensure_ascii=False)
for ф in (ФНС, сп_путь):
    shutil.copyfile(ф, os.path.join(ДРОП, os.path.basename(ф)))
V.п('ФНС: выручка 2025 у', len(д), 'из', len(сп), '| от 1 млрд', sum(1 for v in д.values() if v >= 1e9),
    '| 120 млн–1 млрд', sum(1 for v in д.values() if 1.2e8 <= v < 1e9))

# (2) дешёвая схема с запросом xmlriver
чк = {}
for s in io.open(os.path.join(DIR, 'fsa-meyer-checko.jsonl'), encoding='utf-8', errors='replace'):
    try:
        y = json.loads(s)
    except ValueError:
        continue
    if y.get('inn') and y.get('итог') == 'ok':
        чк[y['inn']] = y
D.ВЫХ = os.path.join(DIR, 'cerb-sayt-inn.jsonl')
было = V.читать(D.ВЫХ)
очередь = sorted((сп[i] for i in сп if not (было.get(i) or {}).get('сайт') and not (было.get(i) or {}).get('запрос')),
                 key=lambda к: -(к.get('выручка') or 0))
V.п('без сайта и без запроса xmlriver:', len(очередь), '| checko есть у', sum(1 for к in очередь if к['inn'] in чк))


def одна(к):
    try:
        D.одна(к, чк)
    except Exception as e:  # noqa: BLE001
        D.записать({'inn': к['inn'], 'сайт': '', 'как': 'сбой ' + repr(e)[:100], 'проверено': [], 'запрос': False})


with ThreadPoolExecutor(8) as ex:
    list(ex.map(одна, очередь))
стало = V.читать(D.ВЫХ)
shutil.copyfile(D.ВЫХ, os.path.join(ДРОП, 'cerb-sayt-inn.jsonl'))
нов = [i for i in стало if стало[i].get('сайт') and not (было.get(i) or {}).get('сайт')]
V.п('новых сайтов', len(нов), '| всего с сайтом', sum(1 for x in стало.values() if x.get('сайт')),
    '| сайт группы?', sum(1 for x in стало.values() if x.get('сайт_группы') and not x.get('сайт')),
    '| итоги', json.dumps(dict(__import__('collections').Counter(str(x.get('как'))[:30] for x in стало.values())), ensure_ascii=False))

# (3) все подтверждённые -> cerbc -> конвейер (готовые ИНН шаги пропускают)
подтв = {i: dict(сп[i], сайт=x['сайт'], сайт_откуда='ИНН на сайте (%s): %s' % (x['как'], x.get('страница_с_инн', '')))
         for i, x in стало.items() if x.get('сайт') and i in сп}
with open(os.path.join(DIR, 'cerbc-spisok.json'), 'w', encoding='utf-8') as f:
    json.dump({'компании': подтв, 'снято': {}, 'ниже_порога': {}, 'на_решение': {}}, f, ensure_ascii=False)
V.п('cerbc: компаний', len(подтв), '— конвейер')
N.конвейер('cerbc', 'meyer')
V.п('ЦЕРБЕР ДОБОР: ГОТОВО')
