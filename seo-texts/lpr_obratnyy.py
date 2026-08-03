# -*- coding: utf-8 -*-
"""Обратный ход в песочнице: по найденному человеку добираем ЕГО контакт.

ЗАЧЕМ ЗДЕСЬ, А НЕ НА СЕРВЕРЕ. Серверный `lpr_serp back` берёт людей из таблицы `people`
панели, где `source LIKE 'поиск-ЛПР%'`. Мой поиск по должности пишет в песочницу, в панель
не пишет — значит серверный обратный ход про этих людей просто не знает и через пару
заданий упрётся в пустоту. Замер сервера: 51 человек за 417 с, 14 телефонов и 11 почт.

Здесь тот же запрос — «"Фамилия Имя Отчество" "<компания>"» — но по СВОЕМУ потоку и в
восемь потоков. Ищем страницу самого человека: профиль на отраслевом портале, программа
конференции с почтой, карточка спикера, интервью в заводской газете.

ЗАСЛОН ОТ ЧУЖОГО НОМЕРА. Номер берётся, только если в том же отрывке стоит фамилия
человека. Страница, где фамилия есть, а номер относится к приёмной соседнего абзаца, даёт
телефон не тому — на этом уже терялись контакты. Поэтому: сначала ищем фамилию, потом
номер в окне вокруг неё, и записываем расстояние между ними, чтобы человек мог судить сам.
"""
import json, os, re, sys, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

for _l in open('/home/user/work/.keys-3s.env'):
    if '=' in _l:
        _k, _v = _l.strip().split('=', 1)
        os.environ.setdefault(_k, _v)
USER, KEY = os.environ['XMLRIVER_USER'], os.environ['XMLRIVER_KEY']

VHOD = 'lpr-pesochnica.jsonl'
POTOK = 'lpr-obratnyy.jsonl'
DOC = re.compile(r'<doc>(.*?)</doc>', re.S)
URL = re.compile(r'<url>([^<]*)</url>')
ZAG = re.compile(r'<title>(.*?)</title>', re.S)
PASS = re.compile(r'<passage>(.*?)</passage>', re.S)
OSH = re.compile(r'<error[^>]*>([^<]*)')
PEREZAPROS = re.compile(r'перезапрос|повторите|не получен|timeout|таймаут', re.I)
PUSTO = re.compile(r'отсутствуют результ|ничего не найдено|нет результатов', re.I)
# Телефон. Свой третий шаблон не пишу: в `tenderpro_harvest` уже есть двухуровневый,
# переживший замер на 9 021 карточке — он умеет и пятизначный код города, и номер в скобках
# без кода страны. Мой прежний шаблон начинался с `(?:\+7|\b8)` и на записи «(8555)37-51-37»
# цеплялся за восьмёрку ВНУТРИ скобок, теряя открывающую: в поток уходило «8555)37-51-37».
def _tel_shablony():
    import ast as _a
    src = open('/home/user/avto/seo-texts/tenderpro_harvest.py', encoding='utf-8').read()
    ns = {'re': re}
    for u in _a.parse(src).body:
        imya = getattr(u, 'name', None)
        if imya is None and isinstance(u, _a.Assign):
            imya = getattr(u.targets[0], 'id', None)
        if imya in ('TEL_YASNO', 'TEL_SPORNO', 'TEL_PERED', 'TEL_SVYAZ', 'TEL_PERED_OTMENA'):
            exec(_a.get_source_segment(src, u), ns)  # noqa: S102
    return ns


_TH = _tel_shablony()
# Проверка на живой записи показала: у `TEL_YASNO` ТОТ ЖЕ дефект, что у моего шаблона —
# на «(8216) 76-20-60» он цепляется за восьмёрку ВНУТРИ скобок и отдаёт «8216) 76-20-60».
# Значит взять готовое было верным решением, а вот считать его исправным — нет. Разрешаю
# необязательную открывающую скобку перед кодом страны и перед кодом города.
TEL = re.compile(r'\(?(?:\+7|\b8)\)?[\s(\-]*\d{3,5}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b'
                 r'|\(\d{3,5}\)[\s\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
POCHTA = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
# Реквизит рядом с числом — не телефон. Тот же заслон, что в сборщике Тендер.Про.
NE_TEL = re.compile(r'(?:ИНН|ОГРН|КПП|р/с|к/с|БИК|лот|№)\D{0,4}$', re.I)
MUSOR = re.compile(r'(avito|youla|hh\.ru|superjob|rabota|zoon|yell|orgpage|list-org|'
                   r'rusprofile|checko|sbis|vk\.com/away)', re.I)


def _bez(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s or '')).strip()


def serp(q, popytok=5):
    url = (f'https://xmlriver.com/search/xml?user={USER}&key={KEY}'
           f'&query={urllib.parse.quote(q)}')
    for p in range(popytok):
        try:
            b = urllib.request.urlopen(
                urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}),
                timeout=60).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return [], f'{type(e).__name__}: {str(e)[:60]}'
            time.sleep(2 * (p + 1))
            continue
        m = OSH.search(b)
        if m:
            t = _bez(m.group(1))
            if PEREZAPROS.search(t) and p < popytok - 1:
                time.sleep(3 * (p + 1))
                continue
            # «Отсутствуют результаты» — ЧЕСТНЫЙ НОЛЬ, а не отказ прибора. Я считала его
            # сбоем, и 47 запросов трижды переспрашивались впустую, а в итоге ложились в
            # отчёт как «сбоев 47» — то есть выглядели потерянными, хотя выдача честно
            # сказала «ничего нет». Правило В8 работает в обе стороны: ноль бывает и
            # настоящим, и путать эти два случая одинаково вредно.
            if PUSTO.search(t):
                return [], ''
            return [], f'xmlriver: {t[:80]}'
        out = []
        for d in DOC.findall(b):
            u = URL.search(d)
            z = ZAG.search(d)
            out.append({'url': u.group(1) if u else '',
                        'tekst': _bez(z.group(1) if z else '') + ' ' +
                                 ' '.join(_bez(x) for x in PASS.findall(d))})
        return out, ''
    return [], 'не дошло'


# ЧУЖАЯ ФАМИЛИЯ МЕЖДУ ЧЕЛОВЕКОМ И КОНТАКТОМ. Разбор четырёх находок показал, что одной
# близости мало: Пиджакову Д.А. приписан телефон в 51 знаке, а в цитате прямо видно
# «Генеральный директор ООО «ЛУКОЙЛ-УНП» — Иванов Алексей Юрьевич. Телефон: (…)» — номер
# Иванова. На странице руководства фамилии и номера идут вперемешку, и расстояние не
# доказывает ничего. Лапаеву Е.М. так же приписалась почта RosihinaOV@nknh.ru.
# НО ПРОСТО УЖЕСТОЧИТЬ НЕЛЬЗЯ: у Гнояной и Лапаева заслон отработал верно, и потерять их
# ради чистоты — хуже. Поэтому контакт НЕ ВЫБРАСЫВАЕТСЯ, а получает степень уверенности,
# и чужая фамилия называется прямо, чтобы человек мог рассудить сам.
# `[а-яё]{2,}` перед окончанием отчества — жадная ловушка: она съедала «Юрьевич» целиком,
# и «Иванов Алексей Юрьевич» не опознавался как фамилия ВООБЩЕ. Проверка на живом примере
# это и показала, до того как я объявила починку работающей.
FAMILIYA = re.compile(r'\b[А-ЯЁ][а-яё\-]{3,}(?=\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]*'
                      r'(?:ович|евич|ьевич|овна|евна|ьевна|ична|инична)\b'
                      r'|\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.)')


# Транслитерация фамилии для сверки с адресом почты. Полная таблица не нужна: сверяем
# первые пять-шесть букв, а на них расхождения школ транслитерации почти не сказываются.
_TRANS = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i',
          'й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t',
          'у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'',
          'э':'e','ю':'yu','я':'ya'}
# Именной адрес: фамилия и инициалы либо фамилия с точкой/подчёркиванием — ivanovii, lapaevem,
# petrov.ai. Общий ящик (info, sales, zakupki) под этот вид не подходит и спорным не считается.
IMENNOY_ADRES = re.compile(r'^[a-z]{4,}[._-]?[a-z]{1,3}\d{0,3}$', re.I)


def _translit(s):
    return ''.join(_TRANS.get(c, c) for c in s.lower())


# Буква в букву транслитерация не сходится, и это поймал контроль: «Гнояная» по моей
# таблице даёт `gnoyanaya`, а в её собственном адресе стоит `gnoianaia` — я→ia против я→ya.
# Живые адреса пишут по десятку разных школ. Поэтому сверяем СОГЛАСНЫЙ СКЕЛЕТ: у «Гнояная»
# и `gnoianaia` он одинаков (gnn), у «Лапаев» и `RosihinaOV` разный (lpv против rshn).
_GLASNYE = set('aeiouy')


def _skelet(s):
    return ''.join(c for c in s.lower() if c.isalpha() and c not in _GLASNYE)


def _fam_v_adrese(fam, adres):
    """Фамилия человека в адресе почты: по русскому написанию, по латинице, по скелету."""
    lok = adres.split('@')[0].lower()
    if fam.lower()[:5] in lok:
        return True
    # Скелет сравниваем в ДВУХ вариантах написания «ц»: `kuznecov` и `kuznetsov` — один и
    # тот же Кузнецов, но во втором лишняя `t` ломает совпадение подстрокой. Контрольный
    # набор из семи адресов поймал ровно этот случай.
    sk_adr = _skelet(lok).replace('ts', 'c')
    for var in (_translit(fam), _translit(fam).replace('c', 'ts')):
        sk = _skelet(var).replace('ts', 'c')
        # Три согласных — минимум, иначе «Ли» совпадёт с чем угодно.
        if len(sk) >= 3 and sk[:4] in sk_adr:
            return True
    return False


def _blizhayshaya_familiya(tekst, poz_kontakta, svoya):
    """Чья фамилия БЛИЖЕ всего к контакту. Пусто — ближайшая наша.

    Проверка «нет ли чужой фамилии МЕЖДУ человеком и контактом» не годится, и это показал
    живой случай: «Генеральный директор — Иванов Алексей Юрьевич. Телефон: (8216) 76-20-60.
    Главный инженер Пиджаков Дмитрий Александрович». Фамилия Иванова стоит ПЕРЕД телефоном,
    Пиджакова — ПОСЛЕ, между телефоном и Пиджаковым чужих нет, и номер спокойно уезжал
    Пиджакову. Правильный вопрос другой: чья фамилия ближе. У Иванова 34 знака, у Пиджакова
    32 — то есть даже это не решает окончательно, но НАЗВАТЬ соперника обязано.
    """
    rjadom = []
    for m in FAMILIYA.finditer(tekst):
        f = m.group(0)
        if f.lower()[:6] == svoya.lower()[:6]:
            continue
        d = abs(m.start() - poz_kontakta)
        if d <= 400:
            rjadom.append((d, f))
    return min(rjadom)[1] if rjadom else ''


def kontakty_ryadom(tekst, fio):
    """Контакты около фамилии со степенью уверенности. Ничего не отбрасывается."""
    fam = fio.split()[0]
    if len(fam) < 4:
        return []
    poz = [m.start() for m in re.finditer(re.escape(fam), tekst)]
    if not poz:
        return []
    nizkiy_fam = fam.lower()
    out = []
    for rx, tip in ((TEL, 'телефон'), (POCHTA, 'почта')):
        for m in rx.finditer(tekst):
            if tip == 'телефон' and NE_TEL.search(tekst[max(0, m.start() - 12):m.start()]):
                continue
            blizh = min(poz, key=lambda p: abs(m.start() - p))
            d = abs(m.start() - blizh)
            if d > 400:
                continue
            chuzhaya = _blizhayshaya_familiya(tekst, m.start(), fam)
            # Почта, содержащая фамилию, — доказательство сильнее любого расстояния:
            # LapaevEM@nknh.ru принадлежит Лапаеву, кто бы ни стоял рядом в тексте.
            v_adrese = (tip == 'почта' and _fam_v_adrese(fam, m.group(0)))
            # ИМЕННАЯ ПОЧТА ЧУЖОГО ЧЕЛОВЕКА — отдельная ловушка, которую расстояние не ловит.
            # Лапаеву Е.М. приписался `RosihinaOV@nknh.ru` в 29 знаках от фамилии: адрес
            # именной, но не его. Русскую фамилию рядом шаблон бы увидел, а латинскую в
            # адресе — нет. Правило: адрес выглядит именным (фамилия + инициалы), но нашей
            # фамилии в нём нет — значит он чужой, и это надо сказать.
            chuzhoy_adres = (tip == 'почта' and not v_adrese
                             and IMENNOY_ADRES.match(m.group(0).split('@')[0]))
            if v_adrese:
                uver, pochemu = 'высокая', 'фамилия человека стоит в самом адресе почты'
            elif chuzhoy_adres:
                uver = 'спорная'
                pochemu = ('адрес именной, но фамилии нашего человека в нём нет — '
                           'похоже, это почта другого сотрудника')
            elif chuzhaya:
                uver = 'спорная'
                pochemu = (f'рядом стоит и чужая фамилия ({chuzhaya}) — контакт может быть её; '
                           f'до нашей {d} знаков')
            elif d <= 120:
                uver, pochemu = 'высокая', f'вплотную к фамилии, {d} знаков, чужих между нет'
            else:
                uver, pochemu = 'средняя', f'{d} знаков до фамилии, чужих между нет'
            out.append({'znachenie': m.group(0).strip(), 'tip': tip,
                        'znakov_do_familii': d, 'uverennost': uver,
                        'pochemu': pochemu, 'chuzhaya_familiya': chuzhaya,
                        # ОКНО ±120/+80 БЫЛО СЛИШКОМ УЗКИМ, и это вскрылось на суде: у 151
                        # случая «не видно» из 279 фамилии человека в отрывке НЕ БЫЛО ВОВСЕ —
                        # модель физически не могла сказать, чей контакт, ей не показали имя.
                        # Она ответила честно, виновата постановка. Окно расширено до
                        # ±400/+400: в него влезает и заголовок должности перед человеком, и
                        # соседняя фамилия, по которой видно, что контакт чужой.
                        'citata': tekst[max(0, m.start() - 400):m.start() + 400]})
    return out


def lyudi_iz_csv(put):
    """Люди из чужого CSV: колонки inn, predpriyatie, fio, dolzhnost.

    ЗАЧЕМ ВТОРОЙ ВХОД. Канал был замкнут на свой поток `lpr-pesochnica.jsonl`, то есть умел
    добирать номера только тем людям, которых нашёл сам. Между тем именно чужие списки —
    самое ценное здесь: 2-я сессия перед уходом оставила 1 517 человек, у которых имя есть,
    а телефона нет. Это ровно наше узкое место, и переписывать их в свой формат руками
    значит терять провенанс.

    Фильтр тот же, что и у своего входа: только полные ФИО. «Иванов И.И.» в кавычках находит
    однофамильцев по всей стране, и заслон по фамилии на такой выдаче бесполезен.
    """
    import csv as _csv
    _csv.field_size_limit(10 ** 7)
    out, bez_fio = {}, 0
    for r in _csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'):
        fio = (r.get('fio') or '').strip()
        inn = (r.get('inn') or '').strip()
        # Полное ФИО — три слова, среднее с отчественным окончанием.
        if not (inn and fio) or len(fio.split()) < 3 or not re.search(
                r'(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична|инична)\b', fio):
            bez_fio += 1
            continue
        k = (inn, fio)
        if k not in out:
            out[k] = {'inn': inn, 'predpriyatie': (r.get('predpriyatie') or '').strip(),
                      'fio': fio, 'dolzhnost': (r.get('dolzhnost') or '').strip()}
    print(f'из {put}: полных ФИО {len(out)}, пропущено (инициалы или нет ИНН) {bez_fio}',
          file=sys.stderr)
    return out


def main():
    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 10 ** 9
    pot = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 8
    if '--vhod-csv' in sys.argv:
        # Чужой список идёт в СВОЙ поток: смешивать провенанс нельзя, иначе завтра не
        # ответить, чей человек и откуда взялся.
        globals()['POTOK'] = (sys.argv[sys.argv.index('--potok') + 1] if '--potok' in sys.argv
                              else 'lpr-obratnyy-chuzhoy.jsonl')
        lyudi = lyudi_iz_csv(sys.argv[sys.argv.index('--vhod-csv') + 1])
        return _gnat(lyudi, lim, pot)
    lyudi = {}
    for ln in open(VHOD, encoding='utf-8'):
        if not ln.strip():
            continue
        z = json.loads(ln)
        for ch in z.get('lyudi') or []:
            # Инициалы вместо имени запросу не помогают: «Иванов И.И.» находит однофамильцев
            # по всей стране. Берём только полные ФИО.
            if ch.get('vid_imeni') != 'полное ФИО':
                continue
            k = (z['inn'], ch['fio'])
            if k not in lyudi:
                lyudi[k] = {'inn': z['inn'], 'predpriyatie': z['predpriyatie'],
                            'fio': ch['fio'], 'dolzhnost': ch['dolzhnost']}
    return _gnat(lyudi, lim, pot)


def _gnat(lyudi, lim, pot):
    """Общий прогон: свой поток и чужой CSV идут по одному и тому же пути."""
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
                gotovo.add((z['inn'], z['fio']))
            except Exception:  # noqa: BLE001
                pass
    zad = [v for k, v in lyudi.items() if k not in gotovo][:lim]
    print(f'людей с полным ФИО {len(lyudi)}, уже спрошено {len(gotovo)}, '
          f'к обходу {len(zad)}, потоков {pot}', file=sys.stderr, flush=True)

    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = {'n': 0, 'sboev': 0, 's_tel': 0, 'tel': 0, 'pocht': 0}

    def odin(c):
        # Имя для запроса. Три вещи убивали выдачу наглухо, и все три видны в упавших
        # запросах: приписка «(ИНН …)» прямо в названии, полная форма собственности
        # («ЕКАТЕРИНБУРГСКОЕ МУНИЦИПАЛЬНОЕ УНИТАРНОЕ ПРЕДПРИЯТИЕ ВОДОПРОВОДНО-…») и
        # кавычки внутри кавычек. В кавычках такая строка не находится никогда.
        imya = re.sub(r'\((?:ИНН|инн)[^)]*\)', ' ', c['predpriyatie'])
        imya = re.sub(r'^\s*(ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ|'
                      r'(?:ПУБЛИЧНОЕ |ОТКРЫТОЕ |ЗАКРЫТОЕ |НЕПУБЛИЧНОЕ )?АКЦИОНЕРНОЕ ОБЩЕСТВО|'
                      r'(?:ФЕДЕРАЛЬНОЕ |МУНИЦИПАЛЬНОЕ |ГОСУДАРСТВЕННОЕ )*'
                      r'(?:БЮДЖЕТНОЕ |УНИТАРНОЕ |КАЗЁННОЕ |КАЗЕННОЕ )*'
                      r'(?:ПРЕДПРИЯТИЕ|УЧРЕЖДЕНИЕ)|'
                      r'ООО|АО|ПАО|ЗАО|ОАО|НАО|ГУП|МУП|ФГУП)\s+', '',
                      c['predpriyatie'] if False else imya, flags=re.I)
        imya = re.sub(r'["«»]', ' ', imya)
        imya = re.sub(r'\s+', ' ', imya).strip()
        # Слишком длинное имя в кавычках тоже не находится: берём первые четыре слова.
        ch = imya.split()
        if len(ch) > 4:
            imya = ' '.join(ch[:4])
        q = f'"{c["fio"]}" "{imya}"'
        docs, err = serp(q)
        naydeno = []
        for d in docs:
            if MUSOR.search(d['url']):
                continue
            for k in kontakty_ryadom(d['tekst'], c['fio']):
                naydeno.append({**k, 'ssylka': d['url']})
        return {**c, 'zapros': q, 'err': err, 'stranic': len(docs), 'kontakty': naydeno}

    with ThreadPoolExecutor(max_workers=pot) as ex:
        for r in ex.map(odin, zad):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                sch['n'] += 1
                sch['sboev'] += 1 if r['err'] else 0
                t = sum(1 for k in r['kontakty'] if k['tip'] == 'телефон')
                p = sum(1 for k in r['kontakty'] if k['tip'] == 'почта')
                sch['tel'] += t
                sch['pocht'] += p
                sch['s_tel'] += 1 if t else 0
                if sch['n'] % 50 == 0:
                    f.flush()
                    os.fsync(f.fileno())
                    print(f"  {sch['n']}/{len(zad)} человек, с телефоном {sch['s_tel']}, "
                          f"телефонов {sch['tel']}, почт {sch['pocht']}, "
                          f"сбоев {sch['sboev']}", file=sys.stderr, flush=True)
    f.flush()
    f.close()
    print(f"готово: людей {sch['n']}, У СКОЛЬКИХ НАШЁЛСЯ ТЕЛЕФОН {sch['s_tel']}, "
          f"телефонов {sch['tel']}, почт {sch['pocht']}, СБОЕВ {sch['sboev']} "
          f"(сбой это не ноль) → {POTOK}", file=sys.stderr)


if __name__ == '__main__':
    main()
