# -*- coding: utf-8 -*-
"""Приговор по спорным сайтам: принадлежность и «лицо предприятия» — раздельно.

ПОЧЕМУ ПЕРВЫЙ ПРИГОВОР БЫЛ БЫ ОШИБКОЙ. Он считал решающим один признак — ИНН в
подвале — и выдал замены `viz.ru → shop.viz.ru`, `medsintez.com →
triazavirin.ru`, `lukoil-masla.ru → ru.lukoil-shop.com`. Магазин обязан
печатать реквизиты продавца по закону, заводской сайт не обязан; признак
исправно доказывал принадлежность и при этом систематически поднимал лавки над
заводами. Карточке нужен сайт, где есть «Контакты», «Производство», «Вакансии»,
телефоны служб, — а не корзина.

ТЕПЕРЬ ДВА ВОПРОСА ЗАДАЮТСЯ ПОРОЗНЬ
    принадлежит ли домен юрлицу    ИНН/ОГРН в тексте        (3 / 2 / 1 / 0)
    лицо ли это предприятия        маркеры завода и лавки   (лавка снимает лицо)

ПРАВИЛА ВЫБОРА, по убыванию силы
    1. поддомен против своего же корня — берём корень (shop.viz.ru → viz.ru);
    2. один принадлежит и не лавка, другой — нет → берём первый;
    3. оба принадлежат, один лавка → берём не-лавку, а про лавку пишем в
       происхождение: это подтверждённый актив того же юрлица, не мусор;
    4. равные — глазами. Ничья не приговор.

Запуск: python sayty_prigovor2.py [--apply]
"""
import csv, io, json, os, re, sqlite3, sys, time
from collections import Counter

P25 = r'C:\seostat\data\p25.db'
ДОКАЗ = r'C:\seostat\drop\sayty_dokazatelstvo_inn.jsonl'
ЛИЦО = r'C:\seostat\drop\sayty_lico_doma.jsonl'
ПОТОК = r'C:\seostat\drop\sayty_prigovory.jsonl'
СОСЕДКАМ = r'C:\seostat\drop\drop-storage\P25-SAYTY-RASHOZHDENIYA-1S.csv'
ГЛАЗАМИ = r'C:\seostat\drop\drop-storage\P25-SAYTY-GLAZAMI-1S.csv'
ПРИМЕНИТЬ = '--apply' in sys.argv


def ступень(з):
    if з.get('inn_nayden') or з.get('ogrn_nayden'):
        return 3
    if з.get('imya_naydeno'):
        return 2
    return 1 if з.get('stranic') else 0


def корень(д):
    ч = str(д).split('.')
    return '.'.join(ч[-3:]) if len(ч) > 2 and ч[-2] in ('com', 'co', 'org') \
        else '.'.join(ч[-2:])


# ТРЕТИЙ ПРИЗНАК: имя предприятия в самом домене.
# Двух признаков не хватило. Осталась категория «принадлежит, не лавка, а лицом
# не является»: sportogok.ru — спорткомплекс Олимпиадинского ГОКа (юридически
# Полюс Красноярск, но искать там главного энергетика бессмысленно),
# triazavirin.ru — лендинг препарата завода «Медсинтез», books96.ru — витрина
# ИПК «Лазурь». Домен, несущий ИМЯ предприятия и живой, — это лицо; домен с
# чужим именем и нашим ИНН — актив. Поэтому доказанный ИНН НЕ перебивает имя.
_ТАБ = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'}
_ФОРМА = ('ооо', 'оао', 'зао', 'пао', 'ао', 'нао', 'фгуп', 'гуп', 'муп', 'нпо',
          'нпп', 'ипк', 'пк', 'тд', 'завод', 'комбинат', 'рус', 'россия',
          'групп', 'group', 'холдинг', 'филиал', 'производственное')
_ШУМ = re.compile(r'^(?:www|new|old|ru|com|org|net|shop|site)$')


def _слова(имя):
    из = []
    for с in re.findall(r'[А-Яа-яЁёA-Za-z0-9]{2,}', str(имя or '')):
        if с.lower() in _ФОРМА:
            continue
        л = ''.join(_ТАБ.get(б, б if б.isalnum() else '') for б in с.lower())
        if len(л) >= 3:
            из.append(л)
    return из


def имя_в_домене(имя, д):
    слова = _слова(имя)
    for ч in [x.replace('-', '') for x in str(д).split('.') if not _ШУМ.match(x)]:
        if len(ч) < 3:
            continue
        for с in слова:
            if ч == с or (len(ч) >= 5 and с.startswith(ч)) \
                    or (len(с) >= 5 and ч.startswith(с)) \
                    or (len(ч) >= 6 and ч in с) or (len(с) >= 6 and с in ч):
                return 1
        if 3 <= len(ч) <= 6 and len(слова) >= len(ч) \
                and ч == ''.join(с[0] for с in слова[:len(ч)]):
            return 1
    return 0


опрос, лицо = {}, {}
for стр in io.open(ДОКАЗ, encoding='utf-8', errors='replace'):
    try:
        з = json.loads(стр)
    except Exception:
        continue
    опрос[(str(з.get('inn')), str(з.get('domen')))] = з
for стр in io.open(ЛИЦО, encoding='utf-8', errors='replace'):
    try:
        з = json.loads(стр)
    except Exception:
        continue
    лицо[str(з.get('domen'))] = з

# Чьё значение стоит в карточке, берём из потока залива, а НЕ из поля
# `istochnik_sayta`: приговор сам пишет туда «чеко доказал ИНН…», и проверка
# «есть ли в источнике слово чеко» после первого же прогона начнёт называть
# находки соседок моими заливами — в файле, который им же и уходит.
ЗАЛИВ = r'C:\seostat\drop\sayty_iz_cheko.jsonl'
мой_залив = {}
if os.path.exists(ЗАЛИВ):
    for стр in io.open(ЗАЛИВ, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(стр)
        except Exception:
            continue
        if str(з.get('baza') or '') in ('P25', 'p25'):
            мой_залив[str(з.get('inn'))] = str(з.get('domen') or '').lower()

цб = sqlite3.connect(P25, timeout=30)
сейчас = {}
for и, с, им, ист in цб.execute(
        "SELECT inn, COALESCE(sayt,''), COALESCE(predpriyatie,''), "
        "COALESCE(istochnik_sayta,'') FROM company"):
    сейчас[str(и)] = (str(с).strip().lower(), str(им), str(ист))

спор = {}
for (и, д), з in опрос.items():
    спор.setdefault(и, {})[д] = з

стат = Counter()
менять, глазами, отчёт = [], [], []
for и, пары in спор.items():
    наш = [д for д, з in пары.items() if з.get('nash')]
    чек = [д for д, з in пары.items() if з.get('cheko')]
    if not наш or not чек or наш[0] == чек[0]:
        continue
    дн, дч = наш[0], чек[0]
    сн, сч = ступень(пары[дн]), ступень(пары[дч])
    лн, лч = лицо.get(дн, {}), лицо.get(дч, {})
    лавка_н = 1 if лн.get('lavka', 0) > лн.get('zavod', 0) else 0
    лавка_ч = 1 if лч.get('lavka', 0) > лч.get('zavod', 0) else 0
    им = сейчас.get(и, ('', '', ''))[1]
    ист = сейчас.get(и, ('', '', ''))[2]
    чей = ('мой залив из чеко' if мой_залив.get(и) == дн
           else 'находка соседних сессий')

    победа, почему = '', ''
    if корень(дн) == корень(дч) and дн != дч:
        if дн.count('.') > дч.count('.'):
            победа, почему = дч, 'поддомен против своего же корня — беру корень'
        elif дч.count('.') > дн.count('.'):
            победа, почему = дн, 'у чеко поддомен нашего же корня — оставляю корень'
    if not победа:
        годн_н = сн - 2 * лавка_н
        годн_ч = сч - 2 * лавка_ч
        if годн_ч > годн_н:
            победа = дч
            почему = ('чеко доказал ИНН и не лавка' if сч == 3 and not лавка_ч
                      else 'у чеко признаки сильнее')
        elif годн_н > годн_ч:
            победа = дн
            почему = ('наше доказано и не лавка' if сн == 3 and not лавка_н
                      else 'наше значение сильнее')

    имя_н, имя_ч = имя_в_домене(им, дн), имя_в_домене(им, дч)
    # Условия «сн >= 1» здесь быть не должно, хотя я его сперва написал: оно
    # означало бы, что не открывшийся для нашего ходока домен проигрывает спор.
    # Но `polyus.com` молчит не потому, что чужой, а потому что не пустил нас, —
    # и это ровно то «молчание прибора», которое я сам запретил считать ответом.
    if победа == дч and имя_н and not имя_ч:
        победа = ''
        почему = ''
        стат['снято третьим признаком: наш домен несёт имя предприятия'] += 1

    з = {'inn': и, 'predpriyatie': им[:60], 'u_nas': дн, 'u_cheko': дч,
         'prinadlezhnost_nash': сн, 'prinadlezhnost_cheko': сч,
         'lavka_nash': лавка_н, 'lavka_cheko': лавка_ч,
         'imya_v_nashem': имя_н, 'imya_v_cheko': имя_ч, 'chey_nash': чей}
    if not победа:
        з['prigovor'] = 'ничья — решают глаза, не я'
        глазами.append(з)
        стат[f'{чей}: ничья, нужны глаза'] += 1
    elif победа == дч:
        з['prigovor'] = f'меняю на {дч}: {почему}'
        менять.append((и, дч, почему, лавка_н and сн == 3))
        стат[f'{чей}: побеждает карточка чеко'] += 1
    else:
        з['prigovor'] = f'оставляю {дн}: {почему}'
        стат[f'{чей}: побеждает наше значение'] += 1
    отчёт.append(з)

print('ВЕРСИЯ КОДА: 3 признака, молчание домена не проигрывает спор')
print('ПРИГОВОРЫ')
for к, v in sorted(стат.items()):
    print(f'   {к:52} {v:4}')
print()
print('ЧТО МЕНЯЕТСЯ:')
for и, д, п, _ in менять[:14]:
    им = сейчас.get(и, ('', '', ''))[1]
    print(f'   {им[:30]:30} {сейчас[и][0][:24]:24} → {д[:24]:24} {п[:34]}')
print()
print('ЛАВКИ, КОТОРЫЕ ПЕРВЫЙ ПРИГОВОР ЗАПИСАЛ БЫ В КАРТОЧКУ (теперь отклонены):')
н = 0
for з in отчёт:
    if з['lavka_cheko'] and з['prinadlezhnost_cheko'] == 3 and 'оставляю' in з['prigovor']:
        print(f"   {з['predpriyatie'][:30]:30} {з['u_cheko'][:26]:26} ← лавка с ИНН")
        н += 1
        if н >= 8:
            break

if not ПРИМЕНИТЬ:
    print()
    print(f'к замене {len(менять)} | глазами {len(глазами)} | споров {len(отчёт)}')
    print('СУХОЙ ПРОГОН')
    цб.close()
    raise SystemExit

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
for и, д, п, была_лавка in менять:
    цб.execute('UPDATE company SET sayt=?, istochnik_sayta=? WHERE inn=?',
               (д, f'проверено обходом: {п}', и))
цб.commit()
с_сайтом = цб.execute("SELECT COUNT(*) FROM company "
                      "WHERE COALESCE(sayt,'')<>''").fetchone()[0]
цб.close()

with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
    for з in отчёт:
        ф.write(json.dumps({**з, 'ts': ts}, ensure_ascii=False) + '\n')
    ф.flush()
    os.fsync(ф.fileno())

поля = ['inn', 'predpriyatie', 'u_nas', 'u_cheko', 'prinadlezhnost_nash',
        'prinadlezhnost_cheko', 'lavka_nash', 'lavka_cheko', 'imya_v_nashem',
        'imya_v_cheko', 'chey_nash', 'prigovor']
for путь, набор in ((СОСЕДКАМ, отчёт), (ГЛАЗАМИ, глазами)):
    with io.open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        п = csv.DictWriter(ф, fieldnames=поля, delimiter=';')
        п.writeheader()
        п.writerows([{к: з.get(к, '') for к in поля} for з in набор])
        ф.flush()
        os.fsync(ф.fileno())

print()
print(f'заменено                      {len(менять):5}')
print(f'ничья, отложено глазами       {len(глазами):5}')
print(f'в файле соседкам строк        {len(отчёт):5}')
print(f'сайт есть у                   {с_сайтом:5} предприятий')
