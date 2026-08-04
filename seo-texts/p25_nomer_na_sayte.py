# -*- coding: utf-8 -*-
"""Спросить НОМЕР там, где человек уже подтверждён его собственным сайтом.

ГДЕ МЫ СТОИМ. Приём `"ФИО" site:<домен>` подтвердил 51 человека страницей собственного сайта
предприятия — из них **14 технического круга**, и должность у них подтверждена не моим
списком, а текстом самой страницы. До закрытия предприятия по ТЗ им не хватает ровно одного:
личного мобильного, добытого на источнике, который сам проходит приёмку.

ПОЧЕМУ НЕЛЬЗЯ ВЗЯТЬ НОМЕР ИЗ ОБРАТНОГО ХОДА. Он там часто есть — и именно на этом я едва не
объявила первое закрытие. Человек подтверждён страницей А, номер добыт со страницы Б, и
страница Б приёмку не проходила. Сложение доказанного с недоказанным даёт недоказанное.
Значит номер надо спросить ЗАНОВО и именно на подтверждающем домене.

ЧЕМ ЭТОТ ЗАПРОС ОТЛИЧАЕТСЯ ОТ ПРЕДЫДУЩЕГО. Тот искал страницу с человеком, этот — страницу с
его контактами: к имени и домену добавляются слова, которыми подписывают телефон. Форм
несколько, потому что предприятия пишут по-разному, и первая же удачная останавливает перебор:
общий пул один на три сессии, лишний запрос стоит чужой работы.

ЗАСЛОН ТОТ ЖЕ И ЕЩ�ё ОДИН СВЕРХ. Страница обязана пройти строгую приёмку; номер обязан стоять
не дальше 400 знаков от фамилии; между ним и фамилией не должно быть ЧУЖОЙ фамилии — иначе
это номер соседа по списку, ровно как было с почтой Кукариной у Бергер.
"""
import collections
import csv
import importlib.util
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\_ops')
import _3s_chuzhaya_stranica as CH  # noqa: E402

POTOK_DOBIT = r'C:\sender\_ops\p25-dobit.jsonl'
POTOK = r'C:\sender\_ops\p25-nomer.jsonl'
SAYTY_FAJLY = (r'C:\sender\_ops\3s_p25_sayty_2s.csv', r'C:\sender\_ops\3s_p25_sayty_ot_1s.csv', r'C:\sender\_ops\3s_p25_sayty_iz_centro.csv',
               r'C:\sender\_ops\3s_p25_sayty_2s_002.csv',
               r'C:\sender\_ops\3s_p25_sayty_iz_poiska.csv',
               r'C:\sender\_ops\3s_p25_sayty_iz_potokov.csv',
               r'C:\sender\_ops\3s_p25_sayty.csv')
KANDIDATY = (r'C:\sender\_ops\3s_lpr_obratnyy.py', r'C:\sender\_ops\_3s_lpr_obratnyy.py')

KRUG1 = re.compile(r'главн\w*\s+(?:инженер|механик|энергетик)|техническ\w+\s+директор', re.I)
KRUG2 = re.compile(r'начальник\w*\s+(?:производств|цеха)|главн\w+\s+технолог|АСУ|КИПиА', re.I)
TEL = re.compile(r'(?:\+7|\b8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
FAM = re.compile(r'\b([А-ЯЁ][а-яё]{3,})(?=\s+[А-ЯЁ])')
FORMY = ('"%s" телефон site:%s', '"%s" контакты site:%s', '"%s" site:%s')


def lichnyy(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return len(c) == 11 and c.startswith('79')


def _serp():
    for put in KANDIDATY:
        if os.path.exists(put):
            spec = importlib.util.spec_from_file_location('lpr_obr', put)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m.serp
    raise SystemExit('модуля поиска нет')


def sayty():
    d = {}
    for p in SAYTY_FAJLY:
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
            v = (r.get('ves') or '').strip()
            if v.isdigit() and int(v) < 2:
                continue
            if r.get('inn') and r.get('sayt'):
                d.setdefault(r['inn'], r['sayt'])
    return d


def celi():
    """Подтверждённые сайтом, у кого должность стоит НА странице и она техническая."""
    out, sch = {}, collections.Counter()
    for ln in open(POTOK_DOBIT, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if z.get('err') or not z.get('naydeno'):
            continue
        d = z.get('dolzhnost') or ''
        if not (KRUG1.search(d) or KRUG2.search(d)):
            sch['подтверждён, но круг не технический'] += 1
            continue
        n = z['naydeno'][0]
        chasti = [re.escape(sl[:-2] if len(sl) > 6 else sl) + r'\w*' for sl in d.split()]
        if not re.search(r'\b' + r'[\s\-]+'.join(chasti), n.get('citata') or '', re.I):
            sch['должность не на подтверждающей странице — не цель'] += 1
            continue
        if lichnyy(n.get('telefon')):
            sch['номер уже есть на той же странице'] += 1
            continue
        k = (z['inn'], z['fio'])
        if k not in out:
            out[k] = {'inn': z['inn'], 'fio': z['fio'], 'dolzhnost': d,
                      'predpriyatie': z.get('predpriyatie', ''), 'sayt': z['sayt']}
            sch['ЦЕЛЬ: техкруг, подтверждён сайтом, номера нет'] += 1
    return out, sch


def chuzhaya_ryadom(tekst, poz, fam):
    """Ближайшая ЧУЖАЯ фамилия между номером и нашим человеком."""
    for m in FAM.finditer(tekst):
        f = m.group(1)
        if f.lower()[:6] == fam.lower()[:6]:
            continue
        if abs(m.start() - poz) <= 200:
            return f
    return ''


def main():
    serp = _serp()
    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 10 ** 9
    pot = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 4
    st = sayty()
    cel, sch = celi()
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if not z.get('err'):
                gotovo.add((z['inn'], z['fio']))
    zad = [v for k, v in cel.items() if k not in gotovo][:lim]
    print('целей %d, спрошено %d, к обходу %d' % (len(cel), len(gotovo), len(zad)),
          file=sys.stderr, flush=True)

    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    itog = collections.Counter()

    def odin(c):
        fam = c['fio'].split()[0]
        nashli, zaprosy, err = [], [], ''
        for forma in FORMY:
            q = forma % (c['fio'], c['sayt'])
            zaprosy.append(q)
            docs, e = serp(q)
            if e:
                err = e
                continue
            for d in docs:
                url = (d.get('url') or '').strip()
                tekst = ' '.join(v for k, v in d.items() if k != 'url' and isinstance(v, str))
                est, poch = CH.stranica_podtverzhdaet(url, c['sayt'], c['predpriyatie'], '',
                                                      strogo=True)
                if not est or fam.lower() not in tekst.lower():
                    continue
                poz_fam = tekst.lower().find(fam.lower())
                for m in TEL.finditer(tekst):
                    if not lichnyy(m.group(0)):
                        continue
                    rasst = abs(m.start() - poz_fam)
                    if rasst > 400:
                        continue
                    chuzh = chuzhaya_ryadom(tekst, m.start(), fam)
                    nashli.append({
                        'nomer': m.group(0), 'ssylka': url, 'pochemu_stranica': poch,
                        'znakov_do_familii': rasst, 'chuzhaya_familiya': chuzh,
                        'uverennost': 'спорная' if chuzh else 'высокая',
                        'citata': tekst[max(0, m.start() - 400):m.start() + 400]})
            if nashli:
                break     # Первая удачная форма останавливает перебор: пул общий.
        return {**c, 'zaprosy': zaprosy, 'err': err if not nashli else '',
                'naydeno': nashli}

    with ThreadPoolExecutor(max_workers=pot) as ex:
        for r in ex.map(odin, zad):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                if r['err']:
                    itog['сбой'] += 1
                elif not r['naydeno']:
                    itog['личного мобильного на сайте нет'] += 1
                elif any(x['uverennost'] == 'высокая' for x in r['naydeno']):
                    itog['НОМЕР НАЙДЕН НА САЙТЕ ПРЕДПРИЯТИЯ — ЗАКРЫТИЕ'] += 1
                else:
                    itog['номер есть, но рядом чужая фамилия — спорный'] += 1
    f.close()
    for k, v in sch.most_common():
        print('REC отбор: %s\t%d' % (k, v))
    for k, v in itog.most_common():
        print('REC прогон: %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({'спрошено': len(zad)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
