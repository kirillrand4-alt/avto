# -*- coding: utf-8 -*-
"""Люди из ТЕКСТА карточек Tender.pro: роль даёт сам документ, а не наша близость.

ОТКУДА ЗАДАЧА. 1-я сессия перемерила «мобильных технарей нет» по своему каналу и
получила обратное: 77 технарей с личным мобильным, из них **73 с tender.pro и 4 с
сайтов предприятий**. Мой ноль был свойством тех источников, по которым ходила я, а
не свойством задачи. Их совет: вычерпать площадку прежде расширения списка
источников — «там контакт лежит рядом с фамилией и должностью на одной карточке, и
привязка даётся самим документом».

ЧЕМ ЭТО СИЛЬНЕЕ ВСЕГО, ЧТО Я ДЕЛАЛА ДО СИХ ПОР. Везде раньше принадлежность номера
человеку я ДОКАЗЫВАЛА: близость к фамилии, отсутствие чужой фамилии между, строгая
приёмка страницы. Каждый такой довод — вывод, и на каждом я уже ошибалась. Здесь
доказывать нечего: в тексте стоит

    «По техническим вопросам: Станкевич Юрий ... тел ...»

Роль названа СЛОВАМИ ЗАКАЗЧИКА. Это первоисточник в чистом виде.

ГЛАВНОЕ РАЗЛИЧЕНИЕ, КОТОРОЕ ДАЁТ КАРТОЧКА. Она почти всегда разделяет два лица:

    «По вопросам участия в закупке обращаться: ...»   -> СНАБЖЕНЕЦ
    «По техническим вопросам: ...»                    -> ТЕХНАРЬ, круг 1-2

Разбираю текст НЕ целиком, а кусками между такими метками: контакт принадлежит той
метке, под которой стоит. Без этого оба человека слиплись бы в один, и снабженец
поехал бы к владельцу как технарь — ровно та подмена, за которую 1-я сессия
справедливо ругала мой сорт B.

ЧТО ЭТО УЖЕ ИСПРАВИЛО. В моей выкладке `8(383)-338-31-32 доб. 403` (Кучеровский,
«Геркулес-Сибирь») стоял ПРЯМЫМ СТОЛОМ, потому что во всех моих потоках на этой базе
был один человек. В карточке площадки та же база — `8(383)-338-31-32 (доб.502)` у
Малевинского. Значит это линия, а не прямой стол. Один чужой источник снял ярлык,
который два моих признака подтверждали. Отсюда правило прогона: базы номеров считать
СОВМЕСТНО по всем источникам, а не по своим.

РАЗДЕЛЯТЬ, А НЕ ОТСЕИВАТЬ. Пишу все контакты: мобильный, городской, городской с
добавочным, почту, номер без названного человека. Вид назван явно, роль названа
явно, кусок текста-основание сохранён.
"""
import collections
import csv
import io
import json
import os
import re
import sqlite3
import sys

ISHODNIK = (r'C:\sender\_ops\tp_raw.json', r'C:\sender\_ops\tp-raw.json',
            '/home/user/work/tp_raw.json')
VYHOD = r'C:\sender\_ops\P25-TP-KARTOCHKI-LYUDI-3S.csv'
POTOKI_TELEFONOV = (
    (r'C:\sender\_ops\p25-obratnyy.jsonl',     'kontakty', 'znachenie'),
    (r'C:\sender\_ops\p25-obratnyy-teh.jsonl', 'kontakty', 'znachenie'),
    (r'C:\sender\_ops\p25-dobavochnyy.jsonl',  'naydeno',  'nomer'),
    (r'C:\sender\_ops\p25-dobit.jsonl',        'naydeno',  'telefon'),
)

# МЕТКИ РОЛЕЙ. Порядок важен: «по техническим вопросам участия» должно опознаться как
# техническая метка, а не как «вопросам участия», поэтому технические стоят первыми.
METKI = (
    (r'по\s+(?:всем\s+)?тех(?:\.|ническ\w*)\s*(?:вопрос\w*|части)', 'технический вопрос'),
    (r'тех(?:\.|ническ\w*)\s*(?:вопрос\w*|специалист|консультац\w*)', 'технический вопрос'),
    (r'по\s+вопрос\w*\s+(?:участия|подачи|подключения|регистрации)', 'участие в закупке'),
    (r'по\s+(?:коммерческ\w*|организационн\w*)\s+вопрос\w*', 'коммерческий вопрос'),
    (r'ответственн\w+\s+(?:сотрудник|лицо|исполнитель)', 'ответственный по закупке'),
    (r'контактн\w+\s+лиц\w*', 'контактное лицо'),
    (r'(?:куратор|инициатор)\s+(?:закупки|тендера|процедуры)', 'куратор закупки'),
)
METKA_RE = re.compile('|'.join('(?P<m%d>%s)' % (i, p) for i, (p, _) in enumerate(METKI)),
                      re.I)

TEL = re.compile(r'(?:\+7|\b8)[\s\-(]*(\d{3,4})[\s\-)]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
DOB = re.compile(r'\(?\s*(?:доб(?:ав(?:очный)?)?\.?|вн(?:утр)?\.?|ext\.?)\s*[:№]?\s*(\d{2,5})',
                 re.I)
MAIL = re.compile(r'[\w.\-]+@[\w.\-]+\.[a-zA-Zа-яА-Я]{2,}')
# ФИО в карточках бывает трёх видов: полное с отчеством, «Фамилия Имя», «Имя Фамилия».
FIO_POLNOE = re.compile(r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,})\s+'
                        r'([А-ЯЁ][а-яё]{2,}(?:ович|евич|ьевич|овна|евна|ьевна|ична))\b')
FIO_PARA = re.compile(r'\b([А-ЯЁ][а-яё]{3,})\s+([А-ЯЁ][а-яё]{2,})\b')
# Слова, которые выглядят как фамилия, но ею не являются. Список рос по живым ошибкам:
# «Уважаемый Сергей», «Сейчас Леонид», «Узнать больше».
NE_FAMILIYA = re.compile(
    r'^(?:Уважаем\w*|Сейчас|Узнать|Просьба|Тендер|Закупк\w*|Поставк\w*|Требован\w*|Общество|'
    r'Акционерн\w*|Техническ\w*|Дополнительн\w*|Электронн\w*|Телефон|Почта|Адрес|Согласно|'
    r'Приложени\w*|Вниман\w*|Услов\w*|Работ\w*|Заказчик|Организатор|Контактн\w*|Ответственн\w*|'
    # ДОЛЖНОСТЬ — НЕ ИМЯ. «Директор Филиала» приехал в выкладку человеком с мобильным,
    # потому что оба слова с большой буквы и оба похожи на «Фамилия Имя». Должность
    # рядом с номером ценна, но записывать её в графу «человек» нельзя: продавец
    # позвонит и спросит господина Филиала.
    r'Директор\w*|Начальник\w*|Руководител\w*|Заместител\w*|Главн\w*|Инженер\w*|Менеджер\w*|'
    r'Специалист\w*|Ведущ\w*|Старш\w*|Замести\w*|Филиал\w*|Отдел\w*|Служб\w*|Департамент\w*|'
    r'Управлени\w*|Дирекци\w*|Секретар\w*|Помощник\w*)$', re.I)

# ПАДЕЖ. Карточки пишут «обращаться К КОМУ» — дательный: «Артемьеву Дмитрию»,
# «Борискиной Анне». Для списка обзвона это читается неверно, поэтому привожу к
# именительному ТОЛЬКО по бесспорным окончаниям, а исходную форму сохраняю рядом.
# Догадка тут дешевле ошибки лишь потому, что обе формы остаются в выгрузке:
# провенанс накапливается, а не заменяется.
IMENIT = ((re.compile(r'ию$'), 'ий'), (re.compile(r'ью$'), 'ий'),
          (re.compile(r'(?<=[бвгджзклмнпрстфхцчшщ])у$'), ''),
          (re.compile(r'ой$'), 'а'), (re.compile(r'(?<=нн)е$'), 'а'))


def v_imenitelnyy(imya):
    """Вернуть (именительный, изменено ли). Не уверены — оставляем как было."""
    slova, menyali = [], False
    for sl in imya.split():
        for rg, zamena in IMENIT:
            novoe, n = rg.subn(zamena, sl)
            if n:
                slova.append(novoe)
                menyali = True
                break
        else:
            slova.append(sl)
    return ' '.join(slova), menyali


def cifry(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return c


def vid_nomera(syroy, hvost):
    """Вид номера называется явно. Мобильный ценнее всего, добавочный — прямой стол."""
    c = cifry(syroy)
    if len(c) != 11:
        return '', 'не номер'
    md = DOB.search(hvost[:40])
    if c.startswith('79'):
        # У мобильного добавочного не бывает: если рядом стоит «доб», он относится к
        # соседнему городскому. Это я уже один раз приклеила по ошибке.
        return c, 'МОБИЛЬНЫЙ ЛИЧНЫЙ'
    return c, ('городской с добавочным %s' % md.group(1)) if md else 'городской'


def imena_v_kuske(t):
    """ВСЕ люди куска с их местами, а не первый попавшийся.

    Первый заход брал одно имя на кусок — и в карточке, где под одной меткой стоят
    четверо со своими номерами, все четыре номера достались бы первому. Это та же
    подмена, что «ближайшая фамилия»: под меткой может быть список, а не человек.
    """
    out, zanyato = [], []
    for m in FIO_POLNOE.finditer(t):
        out.append((m.start(), m.end(), m.group(0), 'ФИО с отчеством'))
        zanyato.append((m.start(), m.end()))
    for m in FIO_PARA.finditer(t):
        if any(m.start() < k and m.end() > n for n, k in zanyato):
            continue
        a, b = m.group(1), m.group(2)
        if NE_FAMILIYA.match(a) or NE_FAMILIYA.match(b):
            continue
        out.append((m.start(), m.end(), m.group(0), 'фамилия и имя'))
    return sorted(out)


def chey_kontakt(imena, poz):
    """Чей это контакт: ближайшее имя ПЕРЕД ним, иначе ближайшее после.

    Возвращает и расстояние — чтобы видно было, на чём держится привязка, а не только
    её итог. «Рядом» само по себе ничего не доказывает; расстояние хотя бы измеримо.
    """
    do = [x for x in imena if x[1] <= poz]
    if do:
        n, k, imya, kak = do[-1]
        return imya, kak, poz - k, 'имя стоит перед контактом'
    posle = [x for x in imena if x[0] > poz]
    if posle:
        n, k, imya, kak = posle[0]
        return imya, kak, n - poz, 'имя стоит после контакта'
    return '', '', -1, 'имени в куске нет'


def kuski(t):
    """Текст карточки, порезанный по меткам ролей. Кусок принадлежит своей метке."""
    met = [(m.start(), METKI[int(m.lastgroup[1:])][1], m.group(0))
           for m in METKA_RE.finditer(t)]
    if not met:
        yield 0, 'роль не названа', '', t
        return
    if met[0][0] > 0:
        yield 0, 'роль не названа', '', t[:met[0][0]]
    for i, (poz, rol, slova) in enumerate(met):
        kon = met[i + 1][0] if i + 1 < len(met) else len(t)
        yield poz, rol, slova, t[poz:kon]


def bazy_iz_potokov():
    """Кто ещё стоит на тех же базовых номерах — по МОИМ потокам."""
    d = collections.defaultdict(set)
    for put, spisok, pole in POTOKI_TELEFONOV:
        if not os.path.exists(put):
            continue
        for ln in open(put, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if z.get('err'):
                continue
            kto = (z.get('fio') or z.get('chelovek') or '').strip().lower()
            for n in (z.get(spisok) or []):
                if not isinstance(n, dict) or (n.get('tip') or 'телефон') != 'телефон':
                    continue
                syroy = n.get(pole)
                for nom in (syroy if isinstance(syroy, list) else [syroy]):
                    c = cifry(nom)
                    if len(c) == 11:
                        d[c].add(n.get('chelovek', '').strip().lower() or kto)
    return d


def s_dropa(imya):
    """Скачать с обменника. Выгрузку площадки собрал сосед — беру готовое, а не заново."""
    import urllib.request
    url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    if not (url and tok):
        return None
    rq = urllib.request.Request(url.rstrip('/') + '/' + imya)
    rq.add_header('X-Drop-Token', tok)
    return json.loads(urllib.request.urlopen(rq, timeout=300).read().decode('utf-8'))


def nashi_inn():
    """ИНН 491 покупателя P25. Без этого не отличить наших от чужих в общей выгрузке."""
    try:
        b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
        return {i for (i,) in b.execute('select inn from company')}
    except Exception:  # noqa: BLE001
        return set()


def main():
    put = next((p for p in ISHODNIK if os.path.exists(p)), '')
    d = json.load(open(put, encoding='utf-8')) if put else s_dropa('tp_raw.json')
    if not d:
        print('ИТОГ ' + json.dumps({'ошибка': 'tp_raw.json нет ни на диске, ни на дропе'},
                                   ensure_ascii=False))
        return
    nashi = nashi_inn()
    kart = d.get('карточки') or []
    svoi_bazy = bazy_iz_potokov()

    sch = collections.Counter()
    stroki, lyudi_na_baze = [], collections.defaultdict(set)
    syrye = []
    for k in kart:
        t = re.sub(r'\s+', ' ', (k.get('comment') or ''))
        if not t:
            sch['карточка без текста'] += 1
            continue
        for poz, rol, slova, kusok in kuski(t):
            imena = imena_v_kuske(kusok)
            nashli = False
            for m in TEL.finditer(kusok):
                c, vid = vid_nomera(m.group(0), kusok[m.end():])
                if not c:
                    continue
                nashli = True
                chel, kak, rasst, poryadok = chey_kontakt(imena, m.start())
                if chel:
                    lyudi_na_baze[c].add(chel.lower())
                syrye.append({'k': k, 'rol': rol, 'slova': slova, 'chel': chel, 'kak': kak,
                              'rasst': rasst, 'poryadok': poryadok,
                              'znach': m.group(0), 'c': c, 'vid': vid, 'kusok': kusok,
                              'poz': m.start()})
            for m in MAIL.finditer(kusok):
                nashli = True
                chel, kak, rasst, poryadok = chey_kontakt(imena, m.start())
                syrye.append({'k': k, 'rol': rol, 'slova': slova, 'chel': chel, 'kak': kak,
                              'rasst': rasst, 'poryadok': poryadok,
                              'znach': m.group(0), 'c': '', 'vid': 'почта', 'kusok': kusok,
                              'poz': m.start()})
            if not nashli:
                for _n, _k, imya, kak in imena:
                    syrye.append({'k': k, 'rol': rol, 'slova': slova, 'chel': imya,
                                  'kak': kak, 'rasst': 0, 'poryadok': 'контакта в куске нет',
                                  'znach': '', 'c': '', 'vid': 'человек без контакта',
                                  'kusok': kusok, 'poz': 0})

    vidano = set()
    for s in syrye:
        k = s['k']
        c = s['c']
        # База считается СОВМЕСТНО: мои потоки плюс сами карточки. Чужой источник
        # снимает ярлык, который два моих признака подтверждали.
        vsego_lyudey = len(lyudi_na_baze.get(c, set()) |
                           {x for x in svoi_bazy.get(c, set()) if x})
        vid = s['vid']
        # ПРАВИЛО 1-Й СЕССИИ, И ОНО КАСАЕТСЯ МОБИЛЬНЫХ В ПЕРВУЮ ОЧЕРЕДЬ: личный номер
        # по определению один на человека. В карточках ИНН 6155008444 номер
        # +7 989 715-39-54 стоял у ЧЕТВЕРЫХ — это общий номер отдела, а не мобильный
        # каждого из них. Первый заход исключал мобильные из этой проверки, потому что
        # я думала про добавочные, и тем самым снимал заслон именно там, где он нужнее
        # всего. Пометка, а не удаление: номер настоящий, неверен ярлык «личный».
        if c and vsego_lyudey >= 2:
            vid += ' — ОБЩИЙ, на нём %d человек' % vsego_lyudey
        # Ключ склейки — ЦИФРЫ номера, а не написание. Бойко Татьяна Сергеевна стояла
        # четырьмя строками: 8 960 914 27 27 / 8-960-914-27-27 / 8 (960) 914-27-27 —
        # один номер, три написания. Тот же урок, что я час назад записала в разбор
        # добавочных, и он снова понадобился в соседнем файле.
        klyuch = (k['inn'], s['chel'].lower(), c or s['znach'].lower(), s['rol'])
        if klyuch in vidano:
            continue
        vidano.add(klyuch)
        imenit, menyali = v_imenitelnyy(s['chel'])
        tehnicheskiy = s['rol'] == 'технический вопрос'
        sch['роль: ' + s['rol']] += 1
        if s['vid'] == 'МОБИЛЬНЫЙ ЛИЧНЫЙ' and s['chel']:
            if vsego_lyudey >= 2:
                sch['мобильный, но общий на нескольких — не личный'] += 1
            else:
                sch['ЛИЧНЫЙ МОБИЛЬНЫЙ С НАЗВАННЫМ ЧЕЛОВЕКОМ'] += 1
                if tehnicheskiy:
                    sch['  и роль ТЕХНИЧЕСКАЯ по тексту карточки'] += 1
        stroki.append({
            # Название берётся из карточки, а пусто — из поля «организатор» той же
            # карточки: у части карточек `company` пустое, и предприятие тогда
            # оказывалось безымянным в выгрузке, хотя имя стояло рядом.
            'inn': k['inn'],
            'nash_pokupatel_p25': 'да' if k['inn'] in nashi else '',
            'predpriyatie': k.get('company') or k.get('организатор') or '',
            'chelovek': imenit, 'chelovek_v_kartochke': s['chel'],
            'padezh_popravlen': 'да' if menyali else '',
            'kak_naydeno_imya': s['kak'],
            'znakov_do_imeni': s['rasst'], 'poryadok_imeni': s['poryadok'],
            'rol_po_kartochke': s['rol'], 'slova_roli': s['slova'],
            'tehnicheskiy_krug': 'да' if tehnicheskiy else '',
            'znachenie': s['znach'], 'vid': vid, 'nomer_ciframi': c,
            'lyudey_na_baze': vsego_lyudey or '',
            'ssylka': k.get('url', ''), 'tender_id': k.get('tender_id', ''),
            'data_kartochki': k.get('дата', ''), 'svezhest': k.get('свежесть', ''),
            'predmet': (k.get('предмет') or '')[:200],
            'osnovanie': s['kusok'][:400],
        })

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(stroki[0].keys()), delimiter=';',
                       extrasaction='ignore')
    w.writeheader()
    w.writerows(stroki)
    open(VYHOD, 'w', encoding='utf-8-sig', newline='').write(buf.getvalue())

    otvet = ''
    url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    if url and tok:
        import urllib.request
        rq = urllib.request.Request(url.rstrip('/') + '/' + os.path.basename(VYHOD),
                                    data=buf.getvalue().encode('utf-8-sig'), method='PUT')
        rq.add_header('X-Drop-Token', tok)
        try:
            otvet = urllib.request.urlopen(rq, timeout=180).status
        except Exception as e:  # noqa: BLE001
            otvet = 'сбой: %s' % e

    for s in stroki:
        if s['tehnicheskiy_krug'] and s['vid'] == 'МОБИЛЬНЫЙ ЛИЧНЫЙ' and s['chelovek']:
            print('ТЕХ+МОБ %s | %s | %s | %s' % (
                s['inn'], s['predpriyatie'][:34], s['chelovek'], s['znachenie']))
    for kk, v in sch.most_common():
        print('REC %s\t%d' % (kk, v))
    inn_vseh = {s['inn'] for s in stroki}
    teh_mob = [s for s in stroki if s['tehnicheskiy_krug'] and s['chelovek']
               and s['vid'] == 'МОБИЛЬНЫЙ ЛИЧНЫЙ']
    print('ИТОГ ' + json.dumps({
        'карточек': len(kart), 'строк контактов': len(stroki),
        'предприятий': len(inn_vseh), 'из них наши покупатели P25': len(inn_vseh & nashi),
        'ТЕХНАРЬ+ЛИЧНЫЙ МОБИЛЬНЫЙ': len(teh_mob),
        '  на наших предприятиях': len([s for s in teh_mob if s['nash_pokupatel_p25']]),
        '  предприятий закрыто по букве ТЗ': len({s['inn'] for s in teh_mob
                                                  if s['nash_pokupatel_p25']}),
        'файл': os.path.basename(VYHOD), 'дроп': otvet}, ensure_ascii=False))


if __name__ == '__main__':
    main()
