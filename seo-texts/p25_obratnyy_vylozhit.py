# -*- coding: utf-8 -*-
"""Выложить добытое обратным ходом P25 файлом в формате приёмки 1-й сессии.

ПРАВИЛО, КОТОРОЕ ЗДЕСЬ ИСПОЛНЯЕТСЯ: кусок прошёл — файл выложен. Не «в конце прогона» и не
«когда наберётся»: вчера 156 добытых телефонов пролежали в потоке, пока владелец не спросил,
где они, и это был самый крупный незалитый кусок главной меры.

ЧТО ОТДЕЛЯЕТСЯ ОТ ЧЕГО — три файла, как и в именном канале:
    -NNN.csv                   подтверждённые первоисточником, годны к заливке;
    -ne-podtverzhdeno-NNN.csv  номер найден, но страница принадлежность не доказывает;
    -obshchie-NNN.csv          номер не личный (городской, 8-800, линия площадки).
Ни одна строка не выбрасывается: правило владельца — разделять, а не отсеивать. Городской
номер это путь к человеку через коммутатор, а выброшенные данные заново не добываются.

ВИД НОМЕРА НАЗЫВАЕТСЯ ЯВНО. `+79…` — личный мобильный, это главная мера. Всё остальное едет
со своей пометкой в отдельный файл, а не молча смешивается с личными.

ИМЯ ФАЙЛА УНИКАЛЬНОЕ НА ВЫКЛАДКУ. Файл на обменнике — почта, а не база: приёмщик читает его
раз в 25 минут, и перезапись внутри окна уносит предыдущую версию. Так уже потерялось 40
строк из моего именного файла — поймала 1-я сессия сторожем, не я.
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
import _3s_chuzhaya_stranica as CH

POTOK = r'C:\sender\_ops\p25-obratnyy.jsonl'
MARKER = r'C:\sender\_ops\3s_p25_obratnyy_vykladka.txt'
POLYA = ['inn', 'chelovek', 'dolzhnost', 'podrazdelenie', 'telefon', 'dobavochnyy',
         'pochta', 'rol',
         'ssylka', 'data_nablyudeniya', 'citata', 'chem_podtverzhdena']
DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')

SAYTY = {}
for _put in (r'C:\sender\_ops\3s_p25_sayty_2s.csv', r'C:\sender\_ops\3s_p25_sayty_iz_centro.csv', r'C:\sender\_ops\3s_p25_sayty_2s_002.csv', r'C:\sender\_ops\3s_p25_sayty_iz_potokov.csv', r'C:\sender\_ops\3s_p25_sayty_iz_poiska.csv', r'C:\sender\_ops\3s_p25_sayty.csv'):
    if os.path.exists(_put):
        for _r in csv.DictReader(open(_put, encoding='utf-8-sig'), delimiter=';'):
            _v = _r.get('ves')
            if _v and _v.isdigit() and int(_v) < 2:
                continue
            if _r.get('inn') and _r.get('sayt'):
                SAYTY.setdefault(_r['inn'], _r['sayt'])


# ВТОРОЕ ИМЯ ДЛЯ ЗАСЛОНА — УПРАВЛЯЮЩАЯ КОМПАНИЯ. У 62 предприятий из 491 исполнительный орган
# по ЕГРЮЛ — юрлицо, а не человек. Правило ТЗ «страница про предприятие на сайте владеющего
# холдинга — первоисточник» для них не могло сработать: заслон сравнивал адрес страницы только
# с именем САМОЙ площадки. Для «АККЕРМАНН ЦЕМЕНТ» страница на сайте «Уральского цемента» —
# именно тот случай, ради которого правило написано, и именно он отваливался.
UK = {}
_p = r'C:\sender\_ops\3s_p25_uk_svyaz.csv'
if os.path.exists(_p):
    for _r in csv.DictReader(open(_p, encoding='utf-8-sig'), delimiter=';'):
        if _r.get('inn') and _r.get('upravlyayushchaya'):
            UK[_r['inn']] = _r['upravlyayushchaya']


def podtverzhdaet(url, sayt, imya, inn):
    """Заслон с двумя именами: своё, потом управляющей компании. Каким сработал — в ответе."""
    est, poch = CH.stranica_podtverzhdaet(url, sayt, imya, '', strogo=True)
    if est or inn not in UK:
        return est, poch
    est2, poch2 = CH.stranica_podtverzhdaet(url, '', UK[inn], '', strogo=True)
    if est2:
        return True, poch2 + ' — по имени управляющей компании'
    return est, poch


# ДОБАВОЧНЫЙ — ОТДЕЛЬНОЙ КОЛОНКОЙ, А НЕ ПОТЕРЕЙ. Вопрос владельца: «а с добавочным если
# будет, его запишешь в базу?» Проверила честно — НЕТ, терялся: шаблон телефона ловил
# одиннадцать цифр и останавливался, а «доб. 1234» после них оставалось в цитате и никуда
# не ехало.
#
# Между тем для нашей задачи добавочный — второе по ценности после личного мобильного.
# Городской номер предприятия это коммутатор, и продавцу придётся объяснять секретарю, кого
# он ищет. Городской С ДОБАВОЧНЫМ — это прямой стол человека, звонок сразу тому, кто нужен.
# Правило владельца «разделять, а не отсеивать» здесь работает буквально: номер в своей
# колонке, добавочный в своей, вид номера назван.
#
# Читается ЗАДНИМ ЧИСЛОМ из цитаты, а не из значения: значение уже обрезано шаблоном, а
# цитата хранит текст вокруг номера целиком. Поэтому чинится без единого нового запроса и
# работает на всё, что уже добыто.
DOB = re.compile(r'(?:доб(?:ав(?:очный)?)?\.?|вн(?:утр(?:енний)?)?\.?|ext\.?|#)\s*[:№]?\s*'
                 r'(\d{2,5})\b', re.I)


def dobavochnyy(nomer, citata):
    """Добавочный, стоящий сразу за номером в тексте. Пусто честнее выдуманного."""
    if not (nomer and citata):
        return '', ''
    poz = citata.find(nomer)
    if poz < 0:
        # Значение нормализовано, в тексте оно записано иначе — ищем по последним цифрам.
        hvost = re.sub(r'\D', '', nomer)[-7:]
        m = re.search(r'\D'.join(hvost), citata) if hvost else None
        if not m:
            return '', 'номер в цитате не найден — добавочный искать негде'
        poz = m.end()
    else:
        poz += len(nomer)
    okno = citata[poz:poz + 40]
    m = DOB.search(okno)
    if not m:
        return '', 'добавочного за номером нет'
    return m.group(1), 'добавочный назван словом сразу за номером'

GOD = re.compile(r'(?<!\d)(20[0-2]\d)(?!\d)')


def vid_nomera(z):
    c = re.sub(r'\D', '', z or '')
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    if len(c) == 11 and c.startswith('79'):
        return 'личный мобильный'
    if c.startswith('7800') or c.startswith('8800'):
        return 'линия 8-800'
    if len(c) in (10, 11):
        return 'городской'
    return 'номер неразборчив'


def data(citata, url):
    m = GOD.search(citata or '')
    if m:
        return m.group(1), 'год в тексте рядом с номером'
    m = GOD.search(url or '')
    if m:
        return m.group(1), 'год в адресе страницы'
    return '', 'даты в источнике нет'


vydacha, ne_podtv, obshchie, spornye = [], [], [], []
sch = collections.Counter()
vidno = set()
for ln in open(POTOK, encoding='utf-8'):
    try:
        z = json.loads(ln)
    except Exception:
        continue
    if z.get('err'):
        sch['сбой канала — переспросится'] += 1
        continue
    for k in z.get('kontakty') or []:
        znach = str(k.get('znachenie') or '').strip()
        if not znach:
            continue
        tip = k.get('tip') or ''
        url = k.get('ssylka') or ''
        cit = (k.get('citata') or '')[:500]
        klyuch = (z['inn'], z['fio'], znach)
        if klyuch in vidno:
            sch['дубль контакта в потоке'] += 1
            continue
        vidno.add(klyuch)
        # ГОД, ПОСЧИТАННЫЙ КАНАЛОМ, СИЛЬНЕЕ ПОСЧИТАННОГО ЗДЕСЬ: там был полный текст
        # страницы, здесь только цитата в 800 знаков. Записи прежних прогонов поля не
        # несут — для них остаётся прежний разбор по цитате и адресу.
        god = (k.get('god_iz_teksta') or '').strip()
        chem_data = k.get('chem_data') or ''
        if not god:
            god2, chem2 = data(cit, url)
            if god2:
                god, chem_data = god2, chem2
            elif not chem_data:
                chem_data = chem2
        vid = vid_nomera(znach) if tip == 'телефон' else 'почта'
        dob, chem_dob = ('', '') if tip != 'телефон' else dobavochnyy(znach, k.get('citata') or '')
        if dob:
            # Городской с добавочным — это ПРЯМОЙ СТОЛ человека, а не коммутатор. Вид
            # называется отдельно, иначе он потеряется среди обычных городских.
            vid = vid + ' с добавочным'
        sch['вид: ' + vid] += 1
        est, poch = podtverzhdaet(url, SAYTY.get(z['inn'], ''),
                                  z.get('predpriyatie', ''), z['inn'])
        stroka = {
            'inn': z['inn'], 'chelovek': z['fio'],
            'dolzhnost': z.get('dolzhnost', ''), 'podrazdelenie': '',
            'telefon': znach if tip == 'телефон' else '',
            'dobavochnyy': dob,
            'pochta': znach if tip == 'почта' else '',
            'rol': vid, 'ssylka': url, 'data_nablyudeniya': god,
            'citata': cit,
            'chem_podtverzhdena': (chem_data + ' | ' + poch
                                   + (' | ' + chem_dob if dob else ''))[:220],
        }
        # СПОРНАЯ ПРИВЯЗКА — ОТДЕЛЬНЫМ ФАЙЛОМ. Канал её ВИДИТ и подписывает
        # (`uverennost`, `pochemu`), а выкладка до сих пор не спрашивала — то есть заслон
        # существовал и не использовался. Нашлось глазами по десяти строкам выложенного
        # файла, и это не единичный случай, а устройство страницы:
        #     Взыграев Сергей Юрьевич  -> Nikolay.Zaretsky@mnv.ru   (почта Зарецкого)
        #     Бергер Марина Олеговна   -> KukarinaAV@kumz.ru        (почта Кукариной)
        #     Сулимова Ольга Анатол.   -> GolovinaIF@kumz.ru        (почта Головиной)
        # На странице «контакты служб снабжения» люди идут списком, и ближайший адрес почти
        # никогда не принадлежит тому, чью фамилию мы искали. Класс тот же, что весь день:
        # близость не доказывает принадлежность. Разница в том, что здесь я его уже
        # распознала в канале — и потеряла на выходе.
        uver = k.get('uverennost') or ''
        if uver == 'спорная':
            stroka['rol'] = vid + ' | СПОРНАЯ ПРИВЯЗКА: ' + (k.get('pochemu') or '')[:90]
            stroka['chem_podtverzhdena'] = (stroka['chem_podtverzhdena']
                                            + ' | ' + (k.get('pochemu') or ''))[:220]
            spornye.append(stroka)
            sch['СПОРНАЯ ПРИВЯЗКА — отдельным файлом'] += 1
        elif not est:
            stroka['rol'] = vid + ' | источник не первоисточник'
            ne_podtv.append(stroka)
            sch['не первоисточник — отдельным файлом'] += 1
        elif vid == 'личный мобильный' or tip == 'почта' or dob:
            vydacha.append(stroka)
            sch['ВЫКЛАДЫВАЮ: ' + vid] += 1
        else:
            obshchie.append(stroka)
            sch['номер не личный — отдельным файлом: ' + vid] += 1

nomer = '001'
if os.path.exists(MARKER):
    nomer = '%03d' % (int(open(MARKER).read().strip() or 0) + 1)
open(MARKER, 'w').write(nomer)

itog = {'выкладка №': nomer, 'по_видам': dict(sch.most_common())}
for imya, dann in (('P25-OBRATNYY-3S-%s.csv' % nomer, vydacha),
                   ('P25-OBRATNYY-3S-ne-podtverzhdeno-%s.csv' % nomer, ne_podtv),
                   ('P25-OBRATNYY-3S-obshchie-%s.csv' % nomer, obshchie),
                   ('P25-OBRATNYY-3S-spornaya-privyazka-%s.csv' % nomer, spornye)):
    b = io.StringIO()
    w = csv.DictWriter(b, fieldnames=POLYA, delimiter=';', extrasaction='ignore')
    w.writeheader()
    w.writerows(dann)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(DROP + '/' + imya, data=telo, method='PUT',
                                 headers={'X-Drop-Token': TOKEN, 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            itog[imya] = '%s, строк %d, %d байт' % (r.status, len(dann), len(telo))
    except Exception as e:
        itog[imya] = 'НЕ выгружено: %s' % type(e).__name__
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False, indent=1))
'''

if __name__ == '__main__':
    dest = r'C:\sender\_ops\3s_p25_obratnyy_vylozhit.py'
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'dest': dest, 'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest, 'argv': [],
                                     'timeout': 900}, timeout=1200)
    d = r.get('data') or {}
    print((d.get('stdout_tail') or '')[-4000:])
    e = d.get('stderr_tail') or ''
    if e:
        print('--- stderr ---\n' + e[-1500:], file=sys.stderr)
