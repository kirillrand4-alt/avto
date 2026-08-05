# -*- coding: utf-8 -*-
"""Номер техническому ЛПР через поисковую выдачу xmlriver. Метод №3 из шести, наконец рабочий.

ЧТО ЭТО РАЗБЛОКИРУЕТ. Мера ТЗ стоит на нуле, и зазор измерен точно: технических людей 16,
личный мобильный — ни у одного. Прямой поиск браузером закрыт капчей, а `news_scan` отдаёт
только новости. Инструкция 3-й сессии (`INSTRUKCIYA-VSEM-panel-py-i-xmlriver-rabochaya-forma`)
снимает препятствие: свой скрипт кладётся и запускается на сервере, а там уже лежит готовый
модуль выдачи с ключами xmlriver.

ЧЕТЫРЕ КЛЮЧА, КАЖДЫЙ ИЗ КОТОРЫХ У СОСЕДКИ СТОИЛ ПРОГОНА — здесь соблюдены:
    panel_file_put   ключ `files`, внутри `dest` и `b64`   (не path, не content, не name)
    класть           в `C:\\sender\\_ops\\`, корень раннер отвергает
    panel_py         ключ `script`, аргументы `argv`        (со `args` прогон идёт СУХИМ)
    ответ            читать `rc`, а не `returncode`

СЛОВА ЗАПРОСА ДОРОЖЕ КОДА. Живой замер соседки на странице, которую она видела глазами:

    site:kirovets-ptz.com "главный инженер" телефон  →  0 номеров в снимках
    site:kirovets-ptz.com контакты доб               →  +7-812-363-46-96 доб. 114

Снимок выдачи следует за запросом: чтобы номер попал в снимок, слово «телефон» не помогает,
а «доб» помогает. Поэтому по каждому человеку идут ЧЕТЫРЕ формы запроса, и все с доменом —
подтверждённый человек стоит 21 запрос при известном домене против 250 при неизвестном.

СЧЁТЧИКИ ПЕЧАТАЮТСЯ ПОСЛЕДНИМИ. `stdout_tail` — это хвост вывода, а не начало: соседка
напечатала главное сверху и получила три строки нулей при итоге 8 957.
"""
import base64
import csv
import glob
import json
import os
import re
import sys

BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
sys.path.insert(0, os.path.join(BAZA, 'server'))
import run_on_server as R

DEST = r'C:\sender\_ops\2s_nomer_tehnaryu.py'
VYHOD = os.path.join(L, 'P25-NOMERA-TEHNARYAM.csv')

# Скрипт, который поедет НА СЕРВЕР. Там лежат ключи xmlriver и готовый модуль выдачи.
SERVERNYY = r'''
# -*- coding: utf-8 -*-
import importlib.util, json, re, sys

spec = importlib.util.spec_from_file_location('lpr', r'C:\sender\_ops\3s_lpr_obratnyy.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

CELI = json.loads(sys.argv[sys.argv.index('--celi') + 1]) if '--celi' in sys.argv else []
# МОБИЛЬНЫЙ: 11 цифр с 7/8 и второй 9, либо 10 с первой 9. Городской ловим отдельно —
# он тоже ценен, но в главную меру не идёт.
MOB = re.compile(r'(?:\+?7|8)[\s\-()]*9\d{2}[\s\-()]*\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')
GOR = re.compile(r'(?:\+?7|8)[\s\-()]*\d{3,5}[\s\-()]*\d{2,3}[\s\-]?\d{2}[\s\-]?\d{2}')
# ИНН ИЛИ ТЕЛЕФОН — РЕШАЕТ СОСЕДНЕЕ СЛОВО, А НЕ ДЛИНА. Первая версия отвергала всё длиннее
# одиннадцати цифр, и владелец поймал: номер С ДОБАВОЧНЫМ длиннее по определению —
# «+7 (812) 326-52-73 доб. 69» это тринадцать цифр. То есть правило резало ровно то, ради
# чего в запросе и стоит слово «доб». Заодно оно отвергало «89161234567» — обычную слитную
# запись мобильного.
# Правильный признак: добавочный ОТРЕЗАЕТСЯ отдельным полем (общее правило про «доб|вн|ext»),
# а ИНН отличается не длиной, а тем, что перед ним написано «ИНН».
# Между номером и словом «доб» бывает запятая, точка с запятой или скобка: «326-52-73,
# доб. 69». Первая версия ждала только пробелы и добавочный не подхватывала — номер
# записывался без него, то есть терялось ровно то, ради чего слово «доб» стоит в запросе.
DOB = re.compile(r'[\s,;.()/–-]*(?:доб\.?|добавочный|вн\.?|ext\.?)[\s.:]*(\d{1,6})', re.I)


def razobrat_nomer(t, nachalo, konec):
    """→ (номер, добавочный) или (None, None), если это не телефон.

    `t` — весь текст, `nachalo`/`konec` — границы найденного. Смотрим ДО номера: если там
    стоит слово «ИНН», «ОГРН», «КПП», «счёт» — это реквизит, а не связь."""
    pered = t[max(0, nachalo - 24):nachalo].upper()
    if re.search(r'ИНН|ОГРН|КПП|СЧ[ЁЕ]Т|Р/С|К/С|БИК|ОКПО', pered):
        return None, None
    syroy = t[nachalo:konec]
    hvost = t[konec:konec + 24]
    m = DOB.match(hvost)
    dobav = m.group(1) if m else ''
    cifry = re.sub(r'\D', '', syroy)
    if len(cifry) == 11 and cifry[0] in '78':
        return syroy.strip(), dobav
    if len(cifry) == 10:
        return syroy.strip(), dobav
    return None, None

primery, itog, zaprosov, sboev = [], [], 0, 0
for c in CELI:
    fam = c['chelovek'].split()[0]
    formy = []
    if c.get('domen'):
        formy += ['site:%s "%s" доб' % (c['domen'], c['chelovek']),
                  'site:%s "%s" контакты доб' % (c['domen'], fam),
                  'site:%s "%s" сотовый' % (c['domen'], fam)]
    formy.append('"%s" "%s" доб' % (c['chelovek'], c.get('predpriyatie', '')[:40]))
    nashli = None
    for z in formy:
        if nashli:
            break
        docs, err = m.serp(z)
        zaprosov += 1
        if err:
            sboev += 1
            continue
        for d in (docs or []):
            t = d.get('tekst') or ''
            if fam not in t:
                continue
            nomer, dobav, vid = None, '', ''
            for kand in MOB.finditer(t):
                nomer, dobav = razobrat_nomer(t, kand.start(), kand.end())
                if nomer:
                    vid = 'личный мобильный'
                    break
            if not nomer:
                for kand in GOR.finditer(t):
                    nomer, dobav = razobrat_nomer(t, kand.start(), kand.end())
                    if nomer:
                        vid = 'городской'
                        break
            if not nomer:
                continue
            i = t.find(fam)
            nashli = {'inn': c['inn'], 'chelovek': c['chelovek'],
                      'dolzhnost': c.get('dolzhnost', ''), 'nomer': nomer,
                      'dobavochnyy': dobav,
                      'vid': vid, 'zapros': z, 'ssylka': d.get('url', ''),
                      'citata': ' '.join(t[max(0, i - 150):i + 250].split())[:400]}
            break
    if nashli:
        itog.append(nashli)
        if len(primery) < 8:
            primery.append('%s | %s%s | %s' % (
                nashli['chelovek'][:24], nashli['nomer'],
                (' доб. ' + nashli['dobavochnyy']) if nashli['dobavochnyy'] else '',
                nashli['vid']))

# ПРИМЕРЫ ПЕРВЫМИ, СЧЁТЧИКИ ПОСЛЕДНИМИ: stdout_tail это хвост.
for p in primery:
    print('  ', p)
print('НАЙДЕНО_JSON', json.dumps(itog, ensure_ascii=False))
print('целей %d, запросов %d, найдено %d, сбоев %d' % (len(CELI), zaprosov, len(itog), sboev))
'''


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def main():
    och = {r['inn']: r for r in chitat(os.path.join(L, 'P25-OCHERED.csv'))}
    posl = sorted(glob.glob(os.path.join(L, 'P25-LYUDI-2S-0*.csv')))[-1]
    lyudi = chitat(posl)
    MOB = re.compile(r'(?:\+?7|8)[\s\-()]*9\d{2}')
    sajty = {}
    for r in chitat(os.path.join(L, 'P25-SAJTY.csv')):
        if r['itog'] in ('подтверждён', 'название совпало'):
            sajty.setdefault(r['inn'], re.sub(r'^https?://', '', r['sayt']).replace('www.', ''))
    celi = []
    for x in lyudi:
        if x.get('rol') != 'техническая' or MOB.search(x.get('telefon') or ''):
            continue
        # НАЗВАНИЕ БЕРЁТСЯ ИЗ ОЧЕРЕДИ. В выкладке его нет, и первый прогон ушёл с запросами
        # вида «"ФИО" "" доб» — пустая вторая кавычка. Такой запрос не сужает ничего и уводит
        # на агрегаторы: оттуда и приехал ИНН физлица вместо телефона.
        celi.append({'inn': x['inn'], 'chelovek': x['chelovek'],
                     'dolzhnost': x.get('dolzhnost', ''),
                     'predpriyatie': och.get(x['inn'], {}).get('predpriyatie', ''),
                     'domen': sajty.get(x['inn'], '')})
    print(f'технических без мобильного: {len(celi)}, из них с известным доменом: '
          f'{sum(1 for c in celi if c["domen"])}', file=sys.stderr)
    if not celi:
        return

    R.submit('enrich_contacts',
             {'op': 'panel_file_put',
              'files': [{'dest': DEST,
                         'b64': base64.b64encode(SERVERNYY.encode('utf-8')).decode()}]},
             timeout=300)
    otvet = R.submit('enrich_contacts',
                     {'op': 'panel_py', 'script': DEST,
                      'argv': ['--celi', json.dumps(celi, ensure_ascii=False)],
                      'timeout': 1700}, timeout=1800)
    d = otvet.get('data') or {}
    hvost = d.get('stdout_tail') or ''
    print(f'rc={d.get("rc")}', file=sys.stderr)
    print(hvost[-1500:], file=sys.stderr)
    if d.get('stderr_tail'):
        print('stderr:', str(d['stderr_tail'])[-400:], file=sys.stderr)

    m = re.search(r'НАЙДЕНО_JSON (\[.*?\])\n', hvost, re.S)
    if not m:
        print('строки с находками в выводе нет', file=sys.stderr)
        return
    najdeno = json.loads(m.group(1))
    novyy = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    with open(VYHOD, 'a', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['inn', 'chelovek', 'dolzhnost', 'nomer',
                                          'dobavochnyy', 'vid', 'zapros', 'ssylka', 'citata'],
                           delimiter=';', extrasaction='ignore')
        if novyy:
            w.writeheader()
        w.writerows(najdeno)
    mob = sum(1 for x in najdeno if x['vid'] == 'личный мобильный')
    print(f'записано {len(najdeno)}, из них ЛИЧНЫХ МОБИЛЬНЫХ {mob}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
