# -*- coding: utf-8 -*-
"""P25: выложить добытых людей файлом в формате, который принимает залив 1-й сессии.

ПОЧЕМУ ЭТО ОТДЕЛЬНЫЙ ШАГ И ПОЧЕМУ ОН ИДЁТ СРАЗУ ПОСЛЕ ПЕРВОГО ЖЕ КУСКА. Вчера у меня
156 добытых телефонов пролежали в потоке на сервере, пока владелец не спросил, где они.
Правило усвоено: кусок прошёл — файл выложен. Не «в конце прогона», не «когда наберётся».

ФОРМАТ — НЕ МОЙ, А ПРИЁМНИКА. 1-я сессия назвала точку записи и колонки:

    inn; chelovek; dolzhnost; podrazdelenie; telefon; pochta; rol; ssylka;
    data_nablyudeniya; citata

Напрямую в базу не пишет никто, включая меня: вливает один оп `vlit_lyudey_csv.py`, и три
исхода вставки живут в одном месте. Это правильно — правило, размазанное по трём сессиям,
разойдётся к вечеру.

ЧТО ВЫКЛАДЫВАЕТСЯ И ЧТО НЕТ. Только люди, у которых страница ПОДТВЕРЖДАЕТ принадлежность:
сайт предприятия, страница про него на сайте холдинга, карточка закупки или имя предприятия
в тексте. Остальные остаются в потоке и в отдельном файле «не подтверждено» — не выбрасываю,
но и в базу не отдаю: непроверенная привязка там дороже пустой клетки.

    ИСТОЧНИК ЗАПРЕЩЁН    не выкладывается вовсе (реестр проверок, аттестация, выборы)
    страница не подтверждает   отдельным файлом, с причиной по каждому
    мимо: зона не наша   отдельным файлом (экология, охрана труда — не наш круг)

РОЛЬ СТАВИТСЯ ПО ПОДРАЗДЕЛЕНИЮ, а не по слову должности — правило ТЗ. Подразделения в выдаче
чаще всего нет, и тогда поле остаётся ПУСТЫМ: угадать его по слову значит подменить правило.

Запуск: python3 p25_otdat_lyudey.py
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

SCRIPT = r'''
# -*- coding: utf-8 -*-
import collections, csv, io, json, os, re, sys, urllib.request
sys.path.insert(0, r'C:\sender\_ops')
import _3s_chuzhaya_stranica as CH

POTOK = r'C:\sender\_ops\p25-imena.jsonl'
POLYA = ['inn', 'chelovek', 'dolzhnost', 'podrazdelenie', 'telefon', 'pochta', 'rol',
         'ssylka', 'data_nablyudeniya', 'citata', 'chem_podtverzhdena']

# САЙТЫ ПРЕДПРИЯТИЙ. В p25.db колонка `sayt` пуста у всех 491, поэтому берём из своих
# файлов: добытые поиском (с признаком) и снятые с ссылок уже добытых контактов. Кандидаты
# с весом меньше 2 не берём — подтверждать сайтом, определённым по одному лишь совпадению
# домена, значит вернуть ту же ошибку с другой стороны.
SAYTY = {}
for _put in (r'C:\sender\_ops\3s_p25_sayty_2s.csv', r'C:\sender\_ops\3s_p25_sayty_iz_poiska.csv', r'C:\sender\_ops\3s_p25_sayty.csv'):
    if not os.path.exists(_put):
        continue
    for _r in csv.DictReader(open(_put, encoding='utf-8-sig'), delimiter=';'):
        _ves = _r.get('ves')
        if _ves and _ves.isdigit() and int(_ves) < 2:
            continue
        if _r.get('inn') and _r.get('sayt') and _r['inn'] not in SAYTY:
            SAYTY[_r['inn']] = _r['sayt']
print('сайтов для приёмки: %d' % len(SAYTY), file=sys.stderr)


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

# Круг по ТЗ: 1) главный инженер/механик/энергетик/техдиректор; 2) начальник производства.
KRUG1 = re.compile(r'главн\w*\s+(?:инженер|механик|энергетик)|техническ\w+\s+директор', re.I)
KRUG2 = re.compile(r'начальник\w*\s+(?:производств|цеха)|главн\w+\s+технолог|АСУ|КИПиА', re.I)
TEL = re.compile(r'(?:\+7|\b8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
# ДАТА ЛЕЖИТ И В АДРЕСЕ, А Я СМОТРЕЛ ТОЛЬКО В ЦИТАТЕ. Замечание 1-й сессии по первому же
# принятому файлу: 12 строк из 13 ушли без даты, то есть в МЕРУ УСПЕХА не пошли, — при том
# что год виден прямо в источнике:
#     tehremex.com/Сборник_докладов_СГМ_2024.pdf      → 2024 в имени файла
#     ab-solution.ru/.../news-energy2024-portrait     → 2024 в адресе
# Правило ТЗ: дата — та, НА КОТОРУЮ человек занимал должность, а не день скачивания. Год
# сборника ей отвечает.
#
# ПОРЯДОК ИСТОЧНИКОВ ДАТЫ — от надёжного к слабому, и он подписывается в `chem`, а не
# теряется: год рядом с именем сильнее года в адресе, а год в адресе сильнее года где-то на
# странице. Если на странице несколько РАЗНЫХ годов и рядом с именем нет ни одного — даты
# нет: выбрать наугад значит выдумать свежесть, а это ровно то, против чего правило.
GOD_RYADOM = re.compile(r'\b(20[0-2]\d)\b')
GOD_V_ADRESE = re.compile(r'(?<!\d)(20[0-2]\d)(?!\d)')


def data_nablyudeniya(citata, ssylka, ves_tekst=''):
    """(год, чем подтверждён). Пусто — честнее выдуманного."""
    m = GOD_RYADOM.search(citata or '')
    if m:
        return m.group(1), 'год в тексте рядом с именем и должностью'
    m = GOD_V_ADRESE.search(ssylka or '')
    if m:
        return m.group(1), 'год в адресе страницы или в имени файла'
    gody = set(GOD_RYADOM.findall(ves_tekst or ''))
    if len(gody) == 1:
        return gody.pop(), 'единственный год на странице'
    return '', ('на странице несколько разных годов — выбрать наугад значит выдумать свежесть'
                if gody else 'даты в источнике нет')
POCHTA = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')

vydacha, ne_podtv, mimo = [], [], []
sch = collections.Counter()
for ln in open(POTOK, encoding='utf-8'):
    z = json.loads(ln)
    if z.get('err'):
        sch['сбой канала — переспросится'] += 1
        continue
    for l in z.get('lyudi') or []:
        krug = l.get('krug', '')
        if krug == 'ИСТОЧНИК ЗАПРЕЩЁН':
            sch['источник запрещён — не выкладываю'] += 1
            continue
        cit = l.get('citata') or ''
        tel = TEL.search(cit)
        poch = POCHTA.search(cit)
        d = l.get('dolzhnost') or ''
        god, chem = l.get('data_iz_teksta', ''), l.get('chem_data', '')
        if god and not chem:
            # Записи прежнего канала: год есть, а чем подтверждён — не записано. Прежний
            # разбор искал год ТОЛЬКО в окне ±120 знаков вокруг имени, поэтому источник
            # известен точно, и подписать его честно можно. Пустое поле провенанса хуже:
            # оно читается как «неизвестно откуда», а мы знаем откуда.
            chem = 'год в тексте рядом с именем и должностью (канал до правки)'
        if not god:
            god, chem = data_nablyudeniya(cit, l.get('ssylka', ''), l.get('citata', ''))
        if god:
            sch['дата определена: ' + chem[:34]] += 1
        else:
            sch['даты нет: ' + chem[:34]] += 1
        stroka = {
            'inn': z['inn'], 'chelovek': l['fio'], 'dolzhnost': d,
            # ПОДРАЗДЕЛЕНИЕ ПУСТОЕ, ЕСЛИ ЕГО НЕТ В ТЕКСТЕ. Роль по ТЗ ставится по
            # подразделению; выводить его из слова должности значит подменить правило,
            # ради которого оно написано.
            'podrazdelenie': '',
            'telefon': tel.group(0) if tel else '',
            'pochta': poch.group(0) if poch else '',
            'rol': ('1 круг' if KRUG1.search(d) else '2 круг' if KRUG2.search(d) else ''),
            'ssylka': l.get('ssylka', ''),
            'data_nablyudeniya': god,
            'citata': cit[:500],
            'chem_podtverzhdena': chem,
        }
        # ПОДТВЕРЖДЁННОСТЬ ПЕРЕСЧИТЫВАЕТСЯ ЗДЕСЬ, а не берётся из потока: часть записей
        # собрана каналом до строгого режима, и доверять их отметке нельзя. Пересчёт по
        # ссылке дешёвый и не требует ни одного запроса к источнику.
        # ИМЯ ПРЕДПРИЯТИЯ И ЕГО САЙТ ПЕРЕДАЮТСЯ, А НЕ ПУСТЫЕ СТРОКИ. Это была тихая потеря
        # ровно того, ради чего заслон написан. Замер: канал по местам 111-150 засчитал
        # страницей 16 человек, а сюда доехало 7; за все прогоны — 84 против 7. Разница
        # целиком в двух пустых аргументах: без имени предприятия не может сработать
        # правило «страница про предприятие на сайте холдинга» (`sibur.ru/polief/…`), а без
        # сайта — самое сильное «хост совпал с сайтом предприятия». Я передавала пустоту и
        # читала получившийся отсев как строгость приёмки.
        est_strogo, poch_strogo = podtverzhdaet(
            l.get('ssylka', ''), SAYTY.get(z['inn'], ''), z.get('predpriyatie', ''),
            z['inn'])
        # ТРИ ИСХОДА, ОДНА РАЗВИЛКА. Прошлая правка развела их двумя вложенными условиями, и
        # ветки перепутались: «зона не наша» уходила в ПОДТВЕРЖДЁННЫЕ, а подтверждённые — в
        # «не подтверждено». Файл выкладки 002 из-за этого неверен, приёмке сказано не лить.
        # Урок тот же, что весь день ловлю у других: одна развилка на одно решение, иначе
        # ошибка не видна ни в коде, ни в счётчике — там просто «5 и 5».
        if krug == 'мимо: зона не наша':
            stroka['rol'] = 'мимо: зона не наша'
            mimo.append(stroka)
            sch['зона не наша'] += 1
        elif not est_strogo:
            stroka['rol'] = ((stroka['rol'] or '') + ' | ' + poch_strogo)[:150]
            ne_podtv.append(stroka)
            sch['не первоисточник — отдельным файлом'] += 1
        else:
            vydacha.append(stroka)
            sch['ВЫКЛАДЫВАЮ (первоисточник): ' + poch_strogo.split('(')[0][:34]] += 1
            if stroka['telefon']:
                sch['  из них с телефоном в цитате'] += 1


# ИМЯ ФАЙЛА УНИКАЛЬНОЕ НА КАЖДУЮ ВЫКЛАДКУ. Находка 1-й сессии, и она про потерю ЧУЖОЙ
# работы, а не моей. Замер их сторожа:
#     17:10  P25-LYUDI-3S.csv  9 655 байт, 53 строки — влили 13, 40 ждали очереди
#     17:19  P25-LYUDI-3S.csv  1 982 байта,  3 строки
# Я перезаписал файл целиком (строгий режим срезал 53 до 3), и 40 строк середины исчезли у
# них из-под рук. У меня самого они не пропали — лежат в «не подтверждено», — но приёмщик
# читает файл раз в 25 минут, и любая перезапись внутри окна теряет предыдущую версию.
#
# ЗАЛИВАТЬ ЧАЩЕ БЕССМЫСЛЕННО, это лечит симптом. Из двух предложенных ими вариантов беру
# ВТОРОЙ, и по их же доводу: накопительный файл всё равно требует, чтобы приёмщик успел
# прочитать до следующей записи, а уникальное имя не зависит от того, успел ли кто-то.
# Плюс сводный `-VSE` для полноты картины: он перезаписывается, но ничего не теряет —
# каждая строка уже лежит в своём нумерованном файле.
NOMER_VYKLADKI = 0
for _f in sorted(os.listdir(r'C:\sender\_ops')):
    _m = re.match(r'p25-vykladka-(\d{3})\.metka$', _f)
    if _m:
        NOMER_VYKLADKI = max(NOMER_VYKLADKI, int(_m.group(1)))
NOMER_VYKLADKI += 1
open(r'C:\sender\_ops\p25-vykladka-%03d.metka' % NOMER_VYKLADKI, 'w').close()


def vylozhit(imya, dannye):
    if not dannye:
        return 'пусто'
    b = io.StringIO()
    w = csv.DictWriter(b, delimiter=';', fieldnames=POLYA, extrasaction='ignore')
    w.writeheader(); w.writerows(dannye)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/' + imya, data=telo, method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return '%s, строк %d' % (r.status, len(dannye))
    except Exception as e:
        return 'НЕ выгружен: ' + type(e).__name__


nom = '%03d' % NOMER_VYKLADKI
itog = {'по_видам': dict(sch.most_common()), 'выкладка №': nom,
        'P25-LYUDI-3S-%s.csv' % nom: vylozhit('P25-LYUDI-3S-%s.csv' % nom, vydacha),
        'P25-LYUDI-3S-ne-podtverzhdeno-%s.csv' % nom:
            vylozhit('P25-LYUDI-3S-ne-podtverzhdeno-%s.csv' % nom, ne_podtv),
        'P25-LYUDI-3S-zona-ne-nasha-%s.csv' % nom:
            vylozhit('P25-LYUDI-3S-zona-ne-nasha-%s.csv' % nom, mimo),
        # Сводный: перезаписывается, но ничего не теряет — всё уже в нумерованных.
        'P25-LYUDI-3S-VSE.csv': vylozhit('P25-LYUDI-3S-VSE.csv', vydacha),
        'предприятий_в_выдаче': len({s['inn'] for s in vydacha})}
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def main():
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'dest': r'C:\sender\_ops\3s_p25_otdat.py',
         'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_p25_otdat.py',
                  'argv': [], 'timeout': 600}, timeout=900)
    d = r.get('data') or {}
    for s in (d.get('stdout_tail') or '').splitlines():
        if s.strip().startswith('ИТОГ '):
            print(json.dumps(json.loads(s.strip()[5:]), ensure_ascii=False, indent=1))
            return
    print('пусто:', (d.get('stderr_tail') or '')[-900:], file=sys.stderr)


if __name__ == '__main__':
    main()
