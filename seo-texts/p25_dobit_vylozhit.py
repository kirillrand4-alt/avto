# -*- coding: utf-8 -*-
"""Выложить добор и посчитать ЗАКРЫТЫЕ предприятия — три условия ТЗ разом.

ОТДАЧА ПРИЁМА, РАДИ КОТОРОГО ОН ПИСАЛСЯ. Первый прогон `p25_dobit_pochti_zakrytyh`:
120 запросов, **41 подтверждён страницей собственного сайта предприятия**. Для сравнения,
слепой именной канал по местам списка платил 250 запросов за одного подтверждённого. Разница
почти стократная, и объясняется она одним: запрос `site:<домен>` спрашивает ровно там, где
ответ засчитывается, вместо того чтобы спрашивать везде и потом отсеивать.

ЧТО СЧИТАЕТСЯ ЗАКРЫТЫМ. По ТЗ нужны ТРИ вещи вместе: технический круг (1-2), личный мобильный
и первоисточник. Здесь они наконец сходятся в одном месте: круг известен из должности, номер
берётся либо из добора (если он на той же странице), либо из уже добытого обратным ходом, а
первоисточник даёт сама страница сайта.

Ни одно из трёх не додумывается: если номера нет — человек едет в файл «подтверждён, номера
нет», и это честный промежуточный результат, а не закрытие.
"""
import base64
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

SCRIPT = r'''
# -*- coding: utf-8 -*-
import collections, csv, io, json, os, re, sys, urllib.request
sys.path.insert(0, r'C:\sender\_ops')

POTOK = r'C:\sender\_ops\p25-dobit.jsonl'
POTOK_OBR = r'C:\sender\_ops\p25-obratnyy.jsonl'
MARKER = r'C:\sender\_ops\3s_p25_dobit_vykladka.txt'
POLYA = ['inn', 'chelovek', 'dolzhnost', 'podrazdelenie', 'telefon', 'pochta', 'rol',
         'ssylka', 'data_nablyudeniya', 'citata', 'chem_podtverzhdena']
DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')
KRUG1 = re.compile(r'главн\w*\s+(?:инженер|механик|энергетик)|техническ\w+\s+директор', re.I)
KRUG2 = re.compile(r'начальник\w*\s+(?:производств|цеха)|главн\w+\s+технолог|АСУ|КИПиА', re.I)
GOD = re.compile(r'(?<!\d)(20[0-2]\d)(?!\d)')
# Надписи интерфейса, разобранные как должность: «Узнать больше», «Подробнее», «Читать».
NE_DOLZHNOST = re.compile(r'^(?:узнать|подробн|читать|смотреть|перейти|подать|далее|ещё|'
                          r'все |показать|скачать|войти|заказать)', re.I)
_KESH = {}


def _dolzh_rx(d):
    rx = _KESH.get(d)
    if rx is None:
        chasti = [re.escape(sl[:-2] if len(sl) > 6 else sl) + r'\w*' for sl in d.split()]
        rx = re.compile(r'\b' + r'[\s\-]+'.join(chasti), re.I)
        _KESH[d] = rx
    return rx


def lichnyy(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return len(c) == 11 and c.startswith('79')


# Личные мобильные, уже добытые обратным ходом, — по ключу «ИНН + ФИО». Спорные привязки
# сюда НЕ берутся: подтверждение страницы не чинит неверную привязку номера к человеку.
nomera = collections.defaultdict(list)
if os.path.exists(POTOK_OBR):
    for ln in open(POTOK_OBR, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:
            continue
        if z.get('err'):
            continue
        for k in z.get('kontakty') or []:
            if (k.get('tip') == 'телефон' and lichnyy(k.get('znachenie'))
                    and k.get('uverennost') != 'спорная'):
                nomera[(z['inn'], z['fio'])].append(k['znachenie'])

vydacha, bez_nomera = [], []
sch = collections.Counter()
zakryto = {}
vidno = set()
for ln in open(POTOK, encoding='utf-8'):
    try:
        z = json.loads(ln)
    except Exception:
        continue
    if z.get('err') or not z.get('naydeno'):
        sch['сбой' if z.get('err') else 'на сайте не найден'] += 1
        continue
    klyuch = (z['inn'], z['fio'])
    if klyuch in vidno:
        continue
    vidno.add(klyuch)
    n = z['naydeno'][0]
    dolzh = z.get('dolzhnost') or ''
    if NE_DOLZHNOST.match(dolzh.strip()):
        sch['должность — надпись интерфейса, не должность'] += 1
        dolzh = ''
    krug = '1 круг' if KRUG1.search(dolzh) else ('2 круг' if KRUG2.search(dolzh) else '')
    tel = n.get('telefon') or ''
    svoi = nomera.get(klyuch) or []
    if not lichnyy(tel) and svoi:
        # НОМЕР ИЗ ДРУГОГО МЕСТА НЕ СТАНОВИТСЯ ПОДТВЕРЖДЁННЫМ ОТ ТОГО, ЧТО ЧЕЛОВЕК
        # ПОДТВЕРЖДЁН ЗДЕСЬ. Так я едва не объявила первое закрытое предприятие: Паначев
        # подтверждён страницей закупок «Уралкалия», где стоит городской (34253) 6-20-88,
        # а мобильный +7 912 … пришёл из другого прогона, и ЕГО источник приёмку не
        # проходил. Три условия ТЗ доказываются каждое отдельно; сложение доказанного с
        # недоказанным даёт недоказанное, а выглядит как закрытие.
        tel = svoi[0]
        chem_tel = ('личный мобильный из обратного хода — ИСТОЧНИК НОМЕРА ОТДЕЛЬНЫЙ, '
                    'этой страницей он не подтверждён')
        nomer_podtverzhden = False
    elif lichnyy(tel):
        chem_tel = 'номер на той же странице сайта предприятия'
        nomer_podtverzhden = True
    else:
        chem_tel = 'номера нет'
        nomer_podtverzhden = False
    # ДОЛЖНОСТЬ ДОЛЖНА СТОЯТЬ НА ПОДТВЕРЖДАЮЩЕЙ СТРАНИЦЕ, а не приходить из моего же
    # списка целей. Проверка глазами по четырём выложенным строкам поймала ровно это:
    #     Смирнов Э. В.  у меня «технический директор», в цитате «Директор по.» (обрыв),
    #                    страница — бухгалтерская отчётность РСБУ за 2019 год;
    #     Лоскутов А. А. должность «Узнать больше» — надпись на кнопке, разобранная как
    #                    должность, страница образовательного маркетплейса.
    # Страница подтверждает, что ЧЕЛОВЕК связан с предприятием. Что он занимает нужную
    # должность, она подтверждает только если так и написано.
    tekst_str = (n.get('citata') or '')
    dolzh_na_stranice = bool(dolzh) and _dolzh_rx(dolzh).search(tekst_str) is not None
    if krug and not dolzh_na_stranice:
        krug = ''
        sch['должность есть в списке, но НЕ на подтверждающей странице'] += 1
    m = GOD.search(n.get('citata') or '') or GOD.search(n.get('ssylka') or '')
    stroka = {
        'inn': z['inn'], 'chelovek': z['fio'], 'dolzhnost': dolzh, 'podrazdelenie': '',
        'telefon': tel if lichnyy(tel) else '',
        'pochta': '', 'rol': krug or 'круг не технический',
        'ssylka': n.get('ssylka', ''),
        'data_nablyudeniya': m.group(1) if m else '',
        'citata': (n.get('citata') or '')[:500],
        'chem_podtverzhdena': ('страница на сайте предприятия (' + n.get('pochemu', '')[:60]
                               + ') | ' + chem_tel)[:220],
    }
    if lichnyy(tel):
        vydacha.append(stroka)
        sch['ВЫКЛАДЫВАЮ с личным мобильным: ' + (krug or 'не технический круг')] += 1
        # ЗАКРЫТИЕ ТРЕБУЕТ ТРЁХ ДОКАЗАННЫХ ВЕЩЕЙ, а не трёх присутствующих.
        if krug and nomer_podtverzhden:
            zakryto[z['inn']] = z['fio'] + ' — ' + dolzh
        elif krug:
            sch['техкруг и номер есть, но источник номера отдельный — НЕ закрытие'] += 1
    else:
        bez_nomera.append(stroka)
        sch['подтверждён сайтом, номера нет: ' + (krug or 'не технический круг')] += 1

nomer = '001'
if os.path.exists(MARKER):
    nomer = '%03d' % (int(open(MARKER).read().strip() or 0) + 1)
open(MARKER, 'w').write(nomer)

itog = {'выкладка №': nomer,
        'ЗАКРЫТО ПРЕДПРИЯТИЙ (техкруг + личный мобильный + первоисточник)': len(zakryto),
        'кто закрыт': zakryto}
for imya, dann in (('P25-DOBOR-3S-%s.csv' % nomer, vydacha),
                   ('P25-DOBOR-3S-bez-nomera-%s.csv' % nomer, bez_nomera)):
    b = io.StringIO()
    w = csv.DictWriter(b, fieldnames=POLYA, delimiter=';', extrasaction='ignore')
    w.writeheader()
    w.writerows(dann)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(DROP + '/' + imya, data=telo, method='PUT',
                                 headers={'X-Drop-Token': TOKEN, 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            itog[imya] = '%s, строк %d' % (r.status, len(dann))
    except Exception as e:
        itog[imya] = 'НЕ выгружено: %s' % type(e).__name__
itog['по_видам'] = dict(sch.most_common())
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False, indent=1))
'''

if __name__ == '__main__':
    dest = r'C:\sender\_ops\3s_p25_dobit_vylozhit.py'
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'dest': dest, 'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest, 'argv': [],
                                     'timeout': 900}, timeout=1200)
    d = r.get('data') or {}
    print((d.get('stdout_tail') or '')[-4000:])
    e = d.get('stderr_tail') or ''
    if e:
        print('--- stderr ---\n' + e[-1200:], file=sys.stderr)
