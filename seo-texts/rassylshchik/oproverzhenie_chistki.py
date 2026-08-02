# -*- coding: utf-8 -*-
"""Попытка ОПРОВЕРГНУТЬ чистку второй сессии: не выкинуто ли живое.

Вторая сессия сама назвала слабое место — отсев построен на словах, а не на смысле, и попросила
взять строки с tip_mashiny не «центробежная» и посмотреть, не отброшен ли настоящий факт.

Я беру шире её просьбы. Тумблер «только центробежные» показывает tip_mashiny ∈ {центробежная,
центробежная по серии} — то есть скрывает НЕ ТОЛЬКО ярлыки-отказы, но и 14 706 строк
«тип не установлен», где obekt = «машина». Это не отброшенный мусор, это машина, вид которой
не разобрали. По объёму это втрое больше подозрительного «трубопровода».

Судит deepseek-v4-pro (правило владельца: свободный текст → факты). Один вопрос на строку,
ответ строкой JSON. Выборка случайная с фиксированным зерном — чтобы проверку можно было
повторить и оспорить.
"""
import collections
import csv
import json
import os
import random
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, '/home/user/work')
csv.field_size_limit(10 ** 7)

B = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
K = os.environ.get('PROVIDER_API_KEY', '')
MODEL = 'deepseek-v4-pro'

FAJL = '/home/user/work/sv2/SVOD-tri-sostoyaniya.csv'
VYBORKA = {
    'тип не установлен': 60,
    'объект — трубопровод или сооружение, машина лишь упомянута': 40,
    'вид не назван (общая формулировка)': 20,
    'поршневая или винтовая': 20,
    'центробежный насос, не компрессор': 20,
    'вихревая или роторная воздуходувка, принцип не центробежный': 15,
    'вентилятор или дымосос': 15,
}

PROMPT = """Перед тобой ТЕКСТ факта о предприятии (закупка, заключение экспертизы промбезопасности
или упоминание оборудования). Нужно определить, относится ли он к ЦЕНТРОБЕЖНОМУ КОМПРЕССОРУ
(он же турбокомпрессор, центробежная воздуходувка, турбовоздуходувка, турбокомпрессорная
установка). Продавец продаёт именно такие машины.

Считается центробежным: К-250/К-350/К-500/К-905, ЦК, ТКА, ТВ (турбовоздуходувка), ВЦ/ВЦГ,
43ВЦ, турбокомпрессор, турбовоздуходувка, центробежный компрессор, нагнетатель ГПА,
Cooper/Elliott/Atlas Copco ZH/Siemens STC и подобные турбомашины.

НЕ считается: поршневой и винтовой компрессор, роторная и вихревая воздуходувка (Roots, ВК, 2АФ,
GM-серия), центробежный НАСОС (перекачивает жидкость, а не газ), вентилятор и дымосос,
паровая турбина, садовая воздуходувка, теплообменник, трубопровод, услуга без машины.

ВАЖНО: если машина в тексте лишь УПОМЯНУТА как место работ (например ремонт здания
турбокомпрессорной станции, прокладка кабеля к компрессорной), но предметом является стройка или
услуга — это всё равно ЗАСЧИТЫВАЕТСЯ как признак того, что у предприятия ЕСТЬ такая машина;
пометь такой случай priznak="есть машина, но предмет не машина".

Текст: {tekst}
Объект по разбору: {obekt}
Чем доказано: {chem}

Ответь ОДНОЙ строкой JSON без пояснений:
{{"centrobezhnyy": "да"|"нет"|"неясно", "priznak": "короткая причина до 90 знаков"}}"""


def вызов(prompt, timeout=180):
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 300}
    req = urllib.request.Request(
        B + '/v1/chat/completions', data=json.dumps(body).encode(),
        headers={'Authorization': f'Bearer {K}', 'Content-Type': 'application/json',
                 'User-Agent': 'curl/8.5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)['choices'][0]['message']['content']


def судить(row):
    p = PROMPT.format(tekst=(row.get('tekst') or '')[:1800],
                      obekt=(row.get('obekt') or '')[:120],
                      chem=(row.get('chem_dokazano') or '')[:150])
    for _ in range(3):
        try:
            t = вызов(p)
            m = re.search(r'\{.*\}', t, re.S)
            if m:
                o = json.loads(m.group(0))
                return o.get('centrobezhnyy', 'неясно'), (o.get('priznak') or '')[:90]
        except Exception as e:  # noqa: BLE001  шлюз иногда отдаёт 5xx; молча ноль не пишем
            oshibka = f'{type(e).__name__}: {str(e)[:60]}'
    return 'сбой', locals().get('oshibka', 'разбор не удался')


def main():
    random.seed(7)
    grp = collections.defaultdict(list)
    with open(FAJL, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f, delimiter=';'):
            t = row.get('tip_mashiny', '')
            if t in VYBORKA:
                grp[t].append(row)
    zadaniya = []
    for yarlyk, n in VYBORKA.items():
        vsego = grp[yarlyk]
        proba = random.sample(vsego, min(n, len(vsego)))
        for r in proba:
            zadaniya.append((yarlyk, len(vsego), r))
    print(f'строк на суд: {len(zadaniya)}', flush=True)

    with ThreadPoolExecutor(max_workers=8) as ex:
        otvety = list(ex.map(lambda z: судить(z[2]), zadaniya))

    itog = collections.defaultdict(lambda: collections.Counter())
    zhivye = []
    for (yarlyk, vsego, row), (verdikt, prichina) in zip(zadaniya, otvety):
        itog[yarlyk][verdikt] += 1
        if verdikt == 'да':
            zhivye.append({'yarlyk': yarlyk, 'vsego_v_yarlyke': vsego, 'inn': row.get('inn'),
                           'predpriyatie': row.get('predpriyatie'), 'prichina': prichina,
                           'tekst': (row.get('tekst') or '')[:300],
                           'chem_dokazano': row.get('chem_dokazano'),
                           'ssylka': row.get('ssylka'), 'istochnik': row.get('istochnik')})
    print(f'\n{"ярлык":62} {"проба":>5} {"да":>4} {"нет":>4} {"неясно":>7} {"доля живых":>11}')
    svod = []
    for yarlyk in VYBORKA:
        c = itog[yarlyk]
        proba = sum(c.values())
        vsego = next((v for y, v, _ in zadaniya if y == yarlyk), 0)
        dolya = c['да'] / proba if proba else 0
        svod.append({'yarlyk': yarlyk, 'vsego_strok': vsego, 'proba': proba, 'da': c['да'],
                     'net': c['нет'], 'neyasno': c['неясно'], 'sboj': c['сбой'],
                     'dolya_zhivyh': round(dolya, 3), 'ocenka_poteryano': round(vsego * dolya)})
        print(f'{yarlyk[:62]:62} {proba:>5} {c["да"]:>4} {c["нет"]:>4} {c["неясно"]:>7} '
              f'{dolya:>10.0%}  ≈{round(vsego * dolya)} строк из {vsego}')
    json.dump({'svod': svod, 'zhivye': zhivye},
              open('/home/user/work/OPROVERZHENIE-chistki-2-sessii.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'\nживых найдено в пробе: {len(zhivye)}; подробности в '
          f'OPROVERZHENIE-chistki-2-sessii.json')


if __name__ == '__main__':
    main()
