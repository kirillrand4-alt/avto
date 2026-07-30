# -*- coding: utf-8 -*-
"""Разбор свободных комментариев карточек Tender.pro: кто этот человек и техническая ли роль.

Зачем провайдер, а не регулярка. Телефон и почту берёт `tenderpro_harvest.py` — у них
регулярный формат, и площадка сама размечает номера тегом `wmi-callto`. А связка «имя —
должность — какой из двух номеров чей» лежит в свободном тексте, и вид у неё каждый раз
другой:

    «По всем тех. вопросам просьба обращаться к Артемьеву Дмитрию: моб. тел. +7(962)205-11-47,
     моб. раб. +7(920)144-58-78»
    «Куратор закупки: Корвяков К. Е., начальник ОМТС… Вопросы технического характера:
     Александр Владимирович Лосев, Заместитель главного механика, Тел. +7 963 251 30 90»

Регулярка тут либо припишет снабженцу мобильный технаря, либо наоборот. Это ровно тот случай,
когда формат НЕ регулярный, и модель уместна. Обратное правило тоже соблюдено: телефон
регуляркой, а не моделью.

Заслоны:
- в ответ разрешено писать **только те телефоны, которые есть во входном тексте**; модель
  предупреждена, что придуманный номер хуже пропуска;
- роль требуется указывать словами из текста, а не своим обобщением;
- если человека в тексте нет — обязана вернуть пустой список, а не «вероятно, снабженец».

Обрез 1500 знаков снят 30.07.2026. Провайдеру уходило `comment[:1500]`, а само поле `comment`
было к тому же обрезано сборщиком на 2 000 знаках — то есть модель видела первые 1 500 знаков
из уже усечённого текста. Замер по `tp-kartochki.csv`: комментарий упёрся в 2 000 знаков у
3 591 карточки, и у 1 772 карточек добытый регуляркой телефон в сохранённый текст не попал
вовсе. Заслон «номера нет во входном тексте» сверялся с этим же обрезанным полем, то есть
законный номер, стоявший за обрезом, мог быть записан как выдумка модели.

Теперь: комментарий уходит целиком (предел 20 000 знаков, каждый его случай считается и
печатается), заслон сверяется с полным текстом. Прогон по перевыкаченному файлу ставится
отдельными файлами (`--kart/--out/--zhurnal`), чтобы два прогона не смешались в одном CSV.

Использование:
    python3 tenderpro_lica.py [--threads 10] [--pachka 12] [--limit N]
    python3 tenderpro_lica.py --kart tp-kartochki-polnye.csv --out tp-lica-polnye.csv \
        --zhurnal tp-lica-sprosheno-polnye.txt --tolko-dlinnye
"""
import csv
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import gen_provider as G

MODEL = 'claude-fable-5'
BAZA = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BAZA, 'engineers-lens', 'centro', 'tenderpro')
KART = os.path.join(OUT, 'tp-kartochki.csv')
LICA = os.path.join(OUT, 'tp-lica.csv')
ZHURNAL = os.path.join(OUT, 'tp-lica-sprosheno.txt')
# Полные комментарии доходят до десятков тысяч знаков, а стандартный предел поля csv — 131 072.
# Без этой строки чтение падает на первой же длинной карточке.
csv.field_size_limit(10 ** 7)
# Предел на то, что уходит в один запрос. Не «на всякий случай»: пачка из 12 карточек по
# 20 000 знаков — это уже 240 000 знаков в одном вызове. Каждый случай упора считается.
PREDEL = 20000

TEL_NORM = re.compile(r'\D+')
# Признак «за прежним обрезом стоит человек или номер»: провайдер видел только первые 1 500
# знаков, значит переспрашивать стоит те карточки, где дальше есть телефон или техническое
# слово. Рубеж взят с запасом 100 знаков — имя могло лежать ровно на стыке.
RUBEZH = 1400
TEH_SLOVO = re.compile(r'тех\w*\s+(?:вопрос|характер|част)|техническ|главн\w+\s+(?:инженер|'
                       r'механик|энергетик|технолог)|гл\.?\s*(?:инженер|механик|энергетик)|'
                       r'механик|энергетик|инженер|КИПиА|ОГМ|ОГЭ|обращат|контактн\w*\s+лиц|'
                       r'ответственн', re.I)
TEL_LYUBOY = re.compile(r'(?:\+7|\b8)[\s(\-]*\d{3,5}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')


def za_rubezhom(comment):
    """Добавляет ли полный текст что-то за прежним обрезом 1 500 знаков."""
    c = comment or ''
    if len(c) <= 1500:
        return False
    hvost = c[RUBEZH:]
    return bool(TEL_LYUBOY.search(hvost) or TEH_SLOVO.search(hvost))


def _env():
    key = os.environ.get('PROVIDER_API_KEY')
    if not key:
        sys.exit('нет PROVIDER_API_KEY в окружении')
    return {'PROVIDER_API_KEY': key,
            'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}


G.env = _env

PROMPT = """Ты разбираешь комментарии к карточкам промышленных закупок на площадке Tender.pro.

ЗАЧЕМ. ООО «Руспром» продаёт промышленные воздушные компрессоры и воздуходувки. Нужен человек,
который отвечает за оборудование: главный инженер, главный механик, главный энергетик,
начальник цеха или компрессорной, их заместители, инженер ОГМ/ОГЭ/КИПиА. Снабженец (ОМТС,
отдел закупок, специалист по закупкам, менеджер по снабжению) тоже нужен, но помечается
отдельно и стоит ниже.

ЧТО СДЕЛАТЬ. Для каждой карточки вернуть людей, названных в комментарии, и для каждого:
- `imya` — как написано в тексте (можно нормализовать порядок «Фамилия Имя Отчество»);
- `dolzhnost` — словами ИЗ ТЕКСТА. Если должность не названа, оставь пустой строкой;
- `rol` — одно из: `техническая`, `снабжение`, `неясно`;
- `telefony` — список номеров ЭТОГО человека;
- `pochta` — почта этого человека, если она стоит рядом с ним;
- `osnovanie` — короткая цитата из текста, по которой ты решил, что номер принадлежит именно
  ему (например «по тех. вопросам обращаться к»).

ПРАВИЛА, нарушать нельзя:
1. **Ни одного номера, которого нет во входном тексте.** Выдуманный телефон хуже пропуска:
   по нему позвонят и попадут в чужого человека.
2. **Если в карточке людей не названо — верни пустой список `lyudi`.** Не угадывай.
3. Если в тексте два человека и два номера, а чей чей — не сказано, поставь `rol` тому, у кого
   роль названа, а телефоны раздели только при явном указании; иначе положи оба номера тому,
   рядом с чьим именем они стоят, и напиши это в `osnovanie`.
4. Не считай технической ролью «инженер по закупкам», «инженер отдела снабжения»,
   «инженер-сметчик», «инженер по договорам» — это снабжение.
5. Телефон вида 8-800 и номер, подписанный как приёмная/секретарь/факс, помечай в
   `osnovanie` словом «приёмная».

ОТВЕТ — строго JSON без пояснений, массив по числу карточек, в том же порядке:
[{"tender_id":"...","lyudi":[{"imya":"","dolzhnost":"","rol":"","telefony":[],"pochta":"","osnovanie":""}]}]

КАРТОЧКИ:
"""


def pachki(rows, n):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def main():
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 10
    pachka = int(sys.argv[sys.argv.index('--pachka') + 1]) if '--pachka' in sys.argv else 12
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 10 ** 9
    kart = os.path.join(OUT, sys.argv[sys.argv.index('--kart') + 1]) \
        if '--kart' in sys.argv else KART
    lica = os.path.join(OUT, sys.argv[sys.argv.index('--out') + 1]) \
        if '--out' in sys.argv else LICA
    zhurnal = os.path.join(OUT, sys.argv[sys.argv.index('--zhurnal') + 1]) \
        if '--zhurnal' in sys.argv else ZHURNAL
    tolko_dlinnye = '--tolko-dlinnye' in sys.argv

    rows = []
    for r in csv.DictReader(open(kart, encoding='utf-8-sig'), delimiter=';'):
        tel = (r.get('telefony_razmetka') or '') + (r.get('telefony_tekst') or '')
        # Смысл фильтра: без телефона в комментарии человек не даёт нам ничего нового,
        # а карточек девять тысяч. Техническое слово без телефона тоже берём — там бывает
        # ФИО с должностью, а номер потом ищется по фамилии.
        if tel or r.get('est_teh'):
            rows.append(r)
    print(f'карточек с телефоном или техническим словом: {len(rows)}', file=sys.stderr)
    if tolko_dlinnye:
        # Переспрашиваем только то, что прежний обрез 1 500 знаков реально скрыл. Остальные
        # карточки провайдер уже видел целиком — платить за них второй раз не за что.
        vsego = len(rows)
        rows = [r for r in rows if za_rubezhom(r.get('comment'))]
        print(f'из них скрывали человека или номер за прежним обрезом 1500: {len(rows)} '
              f'(остальные {vsego - len(rows)} провайдер видел целиком)', file=sys.stderr)
    rows = rows[:limit]

    # Журнал «эту карточку уже спрашивали» ведётся ОТДЕЛЬНО от результата, и это не мелочь.
    # Дедуп по `tp-lica.csv` пропускает только те карточки, где кто-то нашёлся: карточка,
    # честно разобранная и не давшая людей, следов не оставляет и на повторном прогоне
    # спрашивается заново. После починки регулярки телефонов в разбор попало 3 611 карточек,
    # из которых по-настоящему новых было 260, а остальные 3 300 уже спрашивались и вернули
    # пусто — это прямая трата баланса владельца на уже сделанную работу.
    gotovo = set()
    if os.path.exists(zhurnal):
        gotovo |= {l.strip() for l in open(zhurnal, encoding='utf-8') if l.strip()}
    if os.path.exists(lica):
        for r in csv.DictReader(open(lica, encoding='utf-8-sig'), delimiter=';'):
            gotovo.add(r['tender_id'])
    rows = [r for r in rows if r['tender_id'] not in gotovo]
    print(f'к разбору: {len(rows)} (уже разобрано {len(gotovo)})', file=sys.stderr)

    cols = ['tender_id', 'company_id', 'company', 'inn', 'predmet', 'sozdan', 'imya',
            'dolzhnost', 'rol', 'telefon', 'pochta', 'osnovanie', 'telefon_est_v_tekste']
    novyy = not os.path.exists(lica)
    f = open(lica, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    lock = threading.Lock()
    sch = {'lyudey': 0, 'teh': 0, 'vydumka': 0, 'err': 0, 'upor': 0}
    client = G.make_client()

    def odna(gr):
        telo = PROMPT
        for r in gr:
            com = r['comment'] or ''
            if len(com) > PREDEL:
                with lock:
                    sch['upor'] += 1
                com = com[:PREDEL]
            telo += (f'\n--- tender_id: {r["tender_id"]}\nпредмет: {r["predmet"][:200]}\n'
                     f'комментарий: {com}\n')
        try:
            out = G.call(client, [{'role': 'user', 'content': telo}], model=MODEL, attempts=5)
            txt = ''.join(b.text for b in out.content if b.type == 'text').strip()
        except Exception as e:  # noqa: BLE001
            return gr, None, f'{type(e).__name__}: {str(e)[:80]}'
        m = re.search(r'\[.*\]', txt, re.S)
        if not m:
            return gr, None, 'в ответе нет JSON-массива'
        try:
            return gr, json.loads(m.group(0)), ''
        except Exception as e:  # noqa: BLE001
            return gr, None, f'JSON не разобран: {str(e)[:60]}'

    def cifry(s):
        return TEL_NORM.sub('', s or '')[-10:]

    zh = open(zhurnal, 'a', encoding='utf-8')
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, (gr, res, err) in enumerate(pool.map(odna, list(pachki(rows, pachka))), 1):
            with lock:
                if not err:
                    for r0 in gr:
                        zh.write(r0['tender_id'] + '\n')
                    zh.flush()
                if err:
                    sch['err'] += 1
                else:
                    po_id = {r['tender_id']: r for r in gr}
                    for k in res or []:
                        r = po_id.get(str(k.get('tender_id') or ''))
                        if not r:
                            continue
                        # Заслон против выдуманного номера: цифры телефона обязаны
                        # присутствовать во входном тексте карточки. Сверка идёт с ПОЛНЫМ
                        # комментарием — пока он обрезался на 2 000 знаках, законный номер
                        # из-за обреза записывался как выдумка модели.
                        vhod_cifry = TEL_NORM.sub('', r['comment'] or '')
                        for ch in k.get('lyudi') or []:
                            tels = ch.get('telefony') or ['']
                            for t in tels:
                                est = '1' if (not t or cifry(t) and cifry(t) in
                                              vhod_cifry) else ''
                                if t and not est:
                                    sch['vydumka'] += 1
                                w.writerow({'tender_id': r['tender_id'],
                                            'company_id': r['company_id'],
                                            'company': r['company'], 'inn': '',
                                            'predmet': r['predmet'][:300], 'sozdan': r['sozdan'],
                                            'imya': ch.get('imya') or '',
                                            'dolzhnost': ch.get('dolzhnost') or '',
                                            'rol': ch.get('rol') or '',
                                            'telefon': t, 'pochta': ch.get('pochta') or '',
                                            'osnovanie': (ch.get('osnovanie') or '')[:200],
                                            'telefon_est_v_tekste': est})
                                sch['lyudey'] += 1
                                if (ch.get('rol') or '') == 'техническая':
                                    sch['teh'] += 1
                if i % 20 == 0:
                    f.flush()
                    print(f'  пачек {i}: строк {sch["lyudey"]}, технических {sch["teh"]}, '
                          f'номеров не из текста {sch["vydumka"]}, сбоев {sch["err"]}',
                          file=sys.stderr, flush=True)
    zh.close()
    f.close()
    print(f'готово: строк {sch["lyudey"]}, технических {sch["teh"]}, номеров не из текста '
          f'{sch["vydumka"]}, сбоев пачек {sch["err"]} → {lica}', file=sys.stderr)
    if sch['upor']:
        print(f'внимание: комментарий упёрся в предел {PREDEL} знаков у {sch["upor"]} карточек',
              file=sys.stderr)


if __name__ == '__main__':
    main()
