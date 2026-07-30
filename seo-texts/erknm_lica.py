# -*- coding: utf-8 -*-
"""Люди из текстов ЕРКНМ: предостережения Ростехнадзора называют технических работников поимённо.

Откуда взялось. Линза по водоканалам предложила искать имена в актах проверок. По водоканалам
наша выгрузка ЕРКНМ пуста (0 строк из 37 809 — выгрузка собиралась под промышленные предприятия),
и там идея не сработала. Но при проверке этой гипотезы обнаружилось другое: **в самих текстах
ЕРКНМ по заводам люди названы поимённо и с должностью**:

    «согласно данным Единого портала тестирования главный энергетик-руководитель программ
     энергообеспечения Казаков Алексей Григорьевич не прошёл проверку знаний…»
    «заместитель главного механика Латыпов Артур Индусович не прошёл проверку знаний
     требований промышленной безопасности…»

Механический замер: 131 строка, где рядом стоят ФИО и техническая должность, 25 предприятий,
из них 24 есть в нашей сводке и **23 с доказанным состоянием по машине**. То есть это люди в
нужной роли на предприятиях, где машина точно есть.

Разбор отдан провайдеру, а не регулярке: текст свободный, должность бывает в родительном падеже
(«аттестации главного инженера Николаева И.И.»), и надо отличать работника предприятия от
инспектора надзора. Правило прежнее: свободный текст — модели, ровный формат — шаблону.

ВАЖНО про повод звонка. Человек назван потому, что НЕ ПРОШЁЛ проверку знаний или проходит
аттестацию. Ссылаться на это в разговоре нельзя: это его личная неприятность с надзором.
Отсюда берём только «кто занимает роль», повод для звонка — из состояния машины.

Использование:
    python3 erknm_lica.py [--pachka 12] [--threads 6]
"""
import csv
import glob
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import gen_provider as G

csv.field_size_limit(10 ** 7)
MODEL = 'claude-fable-5'
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
VYHOD = os.path.join(C, 'erknm-lica.csv')

G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                 'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}

FIO = re.compile(r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:ович|евич|ьевич|овна|евна|ична)')
TEH = re.compile(r'главн\w+\s+(?:инженер|механик|энергетик|технолог)|зам\w*\s+главн\w+\s+\w+|'
                 r'начальник\s+(?:цеха|участка|отдела|службы|компрессорн|котельн|энерго)', re.I)

PROMPT = """Это тексты предостережений и решений Ростехнадзора из реестра контрольных мероприятий.
В них называют работников предприятий поимённо, с должностью.

ЗАЧЕМ. ООО «Руспром» продаёт воздушные центробежные компрессоры и воздуходувки. Нужны имена
людей в ТЕХНИЧЕСКИХ ролях предприятия: главный инженер, главный механик, главный энергетик,
главный технолог, их заместители, начальник цеха, участка, компрессорной, энергослужбы.

ЧТО ВЕРНУТЬ по каждому НАЗВАННОМУ человеку: `imya` (как в тексте, приведи к «Фамилия Имя
Отчество»), `dolzhnost` (дословно, но в именительном падеже), `rol` (`техническая`,
`руководство`, `надзор`, `неясно`), `chej` (`предприятие` или `надзорный орган`).

ПРАВИЛА, нарушать нельзя:
1. **Ни одного имени, которого нет в тексте.** Не достраивай отчества и инициалы.
2. **Отдели работника предприятия от инспектора.** Сотрудник территориального управления
   Ростехнадзора, член аттестационной комиссии, государственный инспектор — это `надзорный
   орган`, он нам не нужен, но верни его с таким признаком, а не выбрасывай молча.
3. Должность бери из текста. Если должность не названа — оставь поле пустым, роль `неясно`.
4. Если людей нет — пустой список и заполненное `pochemu`.

ОТВЕТ — строго JSON, массив по числу поданных записей:
[{"id":"<id записи>","lyudi":[{"imya":"","dolzhnost":"","rol":"","chej":""}],"pochemu":""}]"""


def zapisi():
    out = []
    for p in glob.glob(os.path.join(C, 'dop', 'erknm-*.csv')):
        for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
            t = re.sub(r'\s+', ' ', r.get('tekst') or '')
            if FIO.search(t) and TEH.search(t):
                out.append({'id': r.get('erpid') or '', 'inn': r.get('inn') or '',
                            'zakazchik': r.get('zakazchik') or '', 'data': r.get('data_nachala') or '',
                            'nadzor': r.get('vid_nadzora') or '', 'tekst': t})
    # один и тот же текст встречается в обеих выгрузках
    vidno = {}
    for x in out:
        vidno.setdefault((x['inn'], x['tekst'][:200]), x)
    return list(vidno.values())


def main():
    pachka = int(sys.argv[sys.argv.index('--pachka') + 1]) if '--pachka' in sys.argv else 12
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 6
    zap = zapisi()
    print(f'записей ЕРКНМ с ФИО и технической должностью: {len(zap)}, '
          f'предприятий: {len({z["inn"] for z in zap})}', file=sys.stderr)
    pachki = [zap[i:i + pachka] for i in range(0, len(zap), pachka)]
    client = G.make_client()
    lock = threading.Lock()
    itog, sch = [], {'lyudej': 0, 'teh': 0, 'nadzor': 0, 'sboev': 0}

    def odna(gr):
        telo = PROMPT + '\n\nЗАПИСИ:\n' + '\n\n'.join(
            f'id={z["id"]}\nпредприятие={z["zakazchik"]}\nтекст: {z["tekst"][:4000]}' for z in gr)
        try:
            o = G.call(client, [{'role': 'user', 'content': telo}], model=MODEL, attempts=4)
            txt = ''.join(b.text for b in o.content if b.type == 'text')
            m = re.search(r'\[.*\]', txt, re.S)
            return gr, (json.loads(m.group(0)) if m else []), ''
        except Exception as e:  # noqa: BLE001
            return gr, [], f'{type(e).__name__}: {e}'

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, (gr, res, err) in enumerate(pool.map(odna, pachki), 1):
            with lock:
                if err:
                    sch['sboev'] += 1
                    print(f'  СБОЙ пачки {i}: {err[:110]}', file=sys.stderr)
                    continue
                po_id = {z['id']: z for z in gr}
                for x in res:
                    z = po_id.get(str(x.get('id') or ''))
                    if not z:
                        continue
                    for c in x.get('lyudi') or []:
                        imya = (c.get('imya') or '').strip()
                        # заслон против выдумки: фамилия обязана встречаться во входном тексте
                        if not imya or imya.split()[0] not in z['tekst']:
                            continue
                        sch['lyudej'] += 1
                        if c.get('chej') == 'надзорный орган':
                            sch['nadzor'] += 1
                        elif c.get('rol') == 'техническая':
                            sch['teh'] += 1
                        itog.append({'inn': z['inn'], 'predpriyatie': z['zakazchik'],
                                     'imya': imya, 'dolzhnost': (c.get('dolzhnost') or '').strip(),
                                     'rol': c.get('rol') or '', 'chej': c.get('chej') or '',
                                     'data': z['data'], 'vid_nadzora': z['nadzor'],
                                     'erpid': z['id'], 'osnovanie': z['tekst'][:300]})
                print(f'  пачек {i}/{len(pachki)}: людей {sch["lyudej"]}, технических {sch["teh"]}, '
                      f'надзор {sch["nadzor"]}', file=sys.stderr, flush=True)

    cols = ['inn', 'predpriyatie', 'imya', 'dolzhnost', 'rol', 'chej', 'data', 'vid_nadzora',
            'erpid', 'osnovanie']
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in itog:
            w.writerow(r)
    pr = list(csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';'))
    lyudi = {(r['inn'], ' '.join(r['imya'].lower().split()[:2])) for r in pr}
    teh = {(r['inn'], ' '.join(r['imya'].lower().split()[:2])) for r in pr
           if r['rol'] == 'техническая' and r['chej'] == 'предприятие'}
    print(f'\nИЗ ФАЙЛА: строк {len(pr)}, людей {len(lyudi)}, '
          f'технических работников предприятий {len(teh)}, предприятий {len({r["inn"] for r in pr})}',
          file=sys.stderr)
    print(f'сбоев пачек: {sch["sboev"]}', file=sys.stderr)
    print(f'→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
