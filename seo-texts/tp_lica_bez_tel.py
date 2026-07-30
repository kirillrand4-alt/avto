# -*- coding: utf-8 -*-
"""Разбор ОТСЕЧЁННЫХ карточек Tender.pro: человек без телефона — половина работы, а не ноль.

Чем отличается от `tenderpro_lica.py`. Тот разбирал 5 260 карточек, отобранных по двум
механическим признакам: есть телефон ИЛИ есть техническое слово. Остальные 3 761 не читались.
Замер (`tp_zamer3.py`) показал, что отсечение было неверным дважды:

  * регулярка телефона в harvest не ловит номер без префикса `+7/8` («тел. (81366) 94-910»)
    и местный номер, разбитый как 3+3 или 1+2+2 («8 3439 395 360», «8(35161) 5-95-45»);
    таких карточек 339 из 3 756 с текстом;
  * сильный признак человека (отчество или «Фамилия И.О.») есть в 268 карточках, и в 75 из
    них телефона действительно нет — но названо имя, а к имени достаточно телефона приёмной.

Промпт поэтому переписан: телефон НЕ требуется, требуется имя, должность, роль и цитата.
Заслон против выдуманного номера сохранён: если модель всё-таки вернула номер, его цифры
обязаны присутствовать во входном тексте.

Использование:
    python3 tp_lica_bez_tel.py [--threads 6] [--pachka 10] [--limit N]
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
KAND = os.path.join(OUT, 'tp-otsech-kandidaty.csv')
LICA = os.path.join(OUT, 'tp-lica-bez-tel.csv')

TEL_NORM = re.compile(r'\D+')


def _env():
    key = os.environ.get('PROVIDER_API_KEY')
    if not key:
        sys.exit('нет PROVIDER_API_KEY в окружении')
    return {'PROVIDER_API_KEY': key,
            'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}


G.env = _env

PROMPT = """Ты разбираешь комментарии к карточкам промышленных закупок на площадке Tender.pro.

ЗАЧЕМ. ООО «Руспром» продаёт промышленные воздушные центробежные компрессоры и воздуходувки.
Нужен человек в ТЕХНИЧЕСКОЙ роли на предприятии: главный инженер, главный механик, главный
энергетик, главный метролог, начальник компрессорной, начальник цеха или участка, их
заместители, инженер ОГМ/ОГЭ/КИПиА/ТОиР, механик, энергетик, специалист по эксплуатации
оборудования. Снабженец (ОМТС, отдел закупок, специалист по закупкам, менеджер по снабжению,
куратор закупки) — тоже нужен, но помечается отдельно и стоит ниже.

ОСОБЕННОСТЬ ЭТОЙ ПАЧКИ: здесь ТЕЛЕФОНА ЧАЩЕ ВСЕГО НЕТ, и это нормально. Имя без номера нам
всё равно ценно: мы позвоним в приёмную предприятия и попросим к аппарату названного человека.
Поэтому НЕ пропускай человека из-за того, что рядом с ним нет телефона.

ЧТО СДЕЛАТЬ. Для каждой карточки вернуть людей, названных в комментарии, и для каждого:
- `imya` — как в тексте, порядок нормализуй в «Фамилия Имя Отчество». Если в тексте только
  «Фамилия И.О.» — так и пиши, отчество НЕ додумывай;
- `dolzhnost` — должность словами ИЗ ТЕКСТА. Если должность не названа — пустая строка.
  НЕ подставляй должность по догадке;
- `rol` — одно из: `техническая`, `снабжение`, `неясно`;
- `telefony` — список номеров ЭТОГО человека, если они в тексте есть. Если нет — пустой список;
- `pochta` — почта этого человека, если она стоит рядом с ним;
- `osnovanie` — короткая цитата ИЗ ТЕКСТА, по которой видно, кто этот человек
  (например «обращаться к», «контактное лицо конечного заказчика»).

ПРАВИЛА, нарушать нельзя:
1. **Ни одного номера и ни одной почты, которых нет во входном тексте.** Выдуманный контакт
   хуже пропуска: по нему позвонят и попадут в чужого человека.
2. **Если в карточке людей не названо — верни пустой список `lyudi`.** Не угадывай. Названия
   организаций, городов, законов и марок оборудования людьми не считаются («Деловые Линии»,
   «Налоговый Кодекс», «Крайний Север», «Atlas Copco» — это НЕ люди).
3. Должность и цитата — разные поля. В `dolzhnost` только название должности, в `osnovanie`
   только цитата. Не переписывай цитату в должность.
4. Не считай технической ролью «инженер по закупкам», «инженер отдела снабжения»,
   «инженер-сметчик», «инженер по договорам», «специалист по закупкам» — это снабжение.
5. Слова «ввод в эксплуатацию», «шеф-монтаж», «пусконаладка» описывают предмет закупки, а не
   должность человека. Роль по ним не назначай.
6. Если человек назван как контакт со стороны ОРГАНИЗАТОРА торгов или посредника, а не
   предприятия-заказчика, напиши это в `osnovanie` словом «организатор».

ОТВЕТ — строго JSON без пояснений, массив по числу карточек, в том же порядке:
[{"tender_id":"...","lyudi":[{"imya":"","dolzhnost":"","rol":"","telefony":[],"pochta":"","osnovanie":""}]}]

КАРТОЧКИ:
"""


def pachki(rows, n):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def main():
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 6
    pachka = int(sys.argv[sys.argv.index('--pachka') + 1]) if '--pachka' in sys.argv else 10
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 10 ** 9

    rows = list(csv.DictReader(open(KAND, encoding='utf-8-sig'), delimiter=';'))[:limit]
    print(f'карточек-кандидатов: {len(rows)}', file=sys.stderr)

    gotovo = set()
    if os.path.exists(LICA):
        for r in csv.DictReader(open(LICA, encoding='utf-8-sig'), delimiter=';'):
            gotovo.add(r['tender_id'])
    rows = [r for r in rows if r['tender_id'] not in gotovo]
    print(f'к разбору: {len(rows)} (уже разобрано карточек {len(gotovo)})', file=sys.stderr)
    if not rows:
        return

    cols = ['tender_id', 'company_id', 'company', 'predmet', 'sozdan', 'imya', 'dolzhnost',
            'rol', 'telefon', 'pochta', 'osnovanie', 'telefon_est_v_tekste', 'pochta_est_v_tekste']
    novyy = not os.path.exists(LICA)
    f = open(LICA, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    lock = threading.Lock()
    sch = {'strok': 0, 'teh': 0, 'bez_tel': 0, 'vydumka_tel': 0, 'vydumka_pochta': 0, 'err': 0}
    client = G.make_client()

    def odna(gr):
        telo = PROMPT
        for r in gr:
            telo += (f'\n--- tender_id: {r["tender_id"]}\nзаказчик: {r["company"]}\n'
                     f'предмет: {r["predmet"][:160]}\nкомментарий: {r["comment"][:1800]}\n')
        try:
            out = G.call(client, [{'role': 'user', 'content': telo}], model=MODEL, attempts=5)
            txt = ''.join(b.text for b in out.content if b.type == 'text').strip()
        except Exception as e:  # noqa: BLE001
            return gr, None, f'{type(e).__name__}: {str(e)[:90]}'
        # Разбор устойчивый к «болтовне вокруг JSON» и к нескольким массивам подряд:
        # raw_decode от каждой открывающей скобки, берём самый длинный валидный массив.
        # `re.search(r'\[.*\]')` этого не умеет — на первой же пачке дал
        # «Extra data: line 115», хотя данные были целы.
        dec = json.JSONDecoder()
        luchshiy = None
        for poz in (mm.start() for mm in re.finditer(r'\[', txt)):
            try:
                val, _ = dec.raw_decode(txt, poz)
            except ValueError:
                continue
            if isinstance(val, list) and (luchshiy is None or len(val) > len(luchshiy)):
                luchshiy = val
        if luchshiy is None:
            return gr, None, f'в ответе нет валидного JSON-массива (ответ {len(txt)} знаков)'
        return gr, luchshiy, ''

    def cifry(s):
        return TEL_NORM.sub('', s or '')

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, (gr, res, err) in enumerate(pool.map(odna, list(pachki(rows, pachka))), 1):
            with lock:
                if err:
                    sch['err'] += 1
                    print(f'  сбой пачки {i}: {err}', file=sys.stderr, flush=True)
                else:
                    po_id = {str(r['tender_id']): r for r in gr}
                    for k in res or []:
                        r = po_id.get(str(k.get('tender_id') or ''))
                        if not r:
                            continue
                        vhod_cifry = cifry(r['comment'])
                        vhod_niz = (r['comment'] or '').lower()
                        for ch in k.get('lyudi') or []:
                            tels = ch.get('telefony') or ['']
                            poch = (ch.get('pochta') or '').strip()
                            p_est = '1' if (not poch or poch.lower() in vhod_niz) else ''
                            if poch and not p_est:
                                sch['vydumka_pochta'] += 1
                                poch = ''          # выдуманную почту не пишем вовсе
                            for t in tels:
                                cd = cifry(t)[-10:]
                                t_est = '1' if (not t or (cd and cd in vhod_cifry)) else ''
                                if t and not t_est:
                                    sch['vydumka_tel'] += 1
                                    t = ''         # выдуманный номер не пишем вовсе
                                if not t:
                                    sch['bez_tel'] += 1
                                w.writerow({
                                    'tender_id': r['tender_id'],
                                    'company_id': r['company_id'],
                                    'company': r['company'],
                                    'predmet': (r['predmet'] or '')[:300],
                                    'sozdan': r['sozdan'],
                                    'imya': ch.get('imya') or '',
                                    'dolzhnost': ch.get('dolzhnost') or '',
                                    'rol': ch.get('rol') or '',
                                    'telefon': t,
                                    'pochta': poch,
                                    'osnovanie': (ch.get('osnovanie') or '')[:200],
                                    'telefon_est_v_tekste': t_est if t else '',
                                    'pochta_est_v_tekste': p_est if poch else ''})
                                sch['strok'] += 1
                                if (ch.get('rol') or '') == 'техническая':
                                    sch['teh'] += 1
                if i % 5 == 0:
                    f.flush()
                    print(f'  пачек {i}: строк {sch["strok"]}, технических {sch["teh"]}, '
                          f'без телефона {sch["bez_tel"]}, выдумок тел/почта '
                          f'{sch["vydumka_tel"]}/{sch["vydumka_pochta"]}, сбоев {sch["err"]}',
                          file=sys.stderr, flush=True)
    f.close()
    print(f'готово: строк {sch["strok"]}, технических {sch["teh"]}, без телефона {sch["bez_tel"]}, '
          f'выдуманных номеров {sch["vydumka_tel"]}, выдуманных почт {sch["vydumka_pochta"]}, '
          f'сбоев пачек {sch["err"]} → {LICA}', file=sys.stderr)


if __name__ == '__main__':
    main()
