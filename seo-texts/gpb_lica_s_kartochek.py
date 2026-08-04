# -*- coding: utf-8 -*-
"""Люди с карточек закупок ЭТП ГПБ. Водитель к разборщику `gpb_kartochka_kontakt.py`.

ПОЧЕМУ ЭТО ПОЯВИЛОСЬ. Опись каналов вскрыла: разборщик карточки написан, а запускался
НИ РАЗУ — в файле нет ни одного пути записи, единственный `open()` на чтение. То есть
210 151 собранная карточка лежала без дела, а мы считали канал сделанным.

СНАЧАЛА СПРОСИЛ, ПОТОМ ПИШУ. Правило, которое я нарушил утром на словаре моделей.
Проверено до строчки кода: на дропе по ЭТП ГПБ лежат только выгрузки списков
(`etpgpb-po-kompaniyam.csv`, `etpgpb-po-slovam.csv`, `etpgpb-loty-vse.csv`) — ни одного
файла с людьми. В журнале 1-й сессии «ГПБ» встречается ОДИН раз, в счётчике старого
словарного обхода; в журнале 3-й сессии — НИ РАЗУ. Дубля нет, канал наш.

ЧЕГО ЖДАТЬ, ЗАМЕРЕНО НА 99 КАРТОЧКАХ (`zamer_kontaktov.py`, выборка равномерно по разным
предприятиям): контактное лицо на 90, телефон на 91, **личный мобильный на 15 — 15 %**,
номеров, стоящих у разных людей, — НОЛЬ. Последнее отличает эту площадку от Росэлторга,
где один городской стоял сразу у трёх человек.

ОТБОР КАРТОЧЕК. Все 210 151 не обойти, да и незачем: уникальных предприятий в файле 235,
то есть на предприятие приходятся сотни карточек с повторяющимися людьми. Поэтому:
  * предприятия идут в порядке пользы — сначала те, у кого НЕТ технического человека или
    нет личного номера, потом остальные;
  * внутри предприятия карточки взвешиваются по предмету: машинные предметы вперёд
    (на Tender.pro это давало 22,0 % людей против 6,9 % на прочих);
  * действует ПРАВИЛО ОСТАНОВКИ: после N карточек подряд без новой фамилии предприятие
    закрывается. Иначе один крупный заказчик съест весь прогон.

ТРИ ИСХОДА РАЗБОРА, и путать их нельзя (за это уже платили):
    est=True  — карточка есть, поля сняты;
    est=False — карточки нет (площадка отдаёт procedure=EmptyRef при HTTP 200!);
    est=None  — РАЗОБРАТЬ НЕ УДАЛОСЬ. Это НЕ «контакта нет»: такие карточки идут в
                отдельный счётчик и подлежат перезапросу, а не считаются пустыми.

Использование:
    python3 gpb_lica_s_kartochek.py --predpriyatiy 20 --na-predpriyatie 25
    python3 gpb_lica_s_kartochek.py --parallel 6
"""
import csv
import json
import os
import re
import subprocess
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpb_kartochka_kontakt as razbor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
ISHODNIK = os.path.join(C, 'etpgpb-po-kompaniyam.csv')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
VYHOD = os.path.join(C, 'etpgpb-lica-s-kartochek.csv')
KARTA = os.path.join(C, 'etpgpb-lica-zhurnal.csv')

# --- P25 (покупатели 2025): те же карточки, другой список и другие файлы. См. пояснение
# в lica_s_kartochek.py — модуль не форкается, пути переопределяются окружением.
ISHODNIK = os.environ.get('P25_ISHODNIK', ISHODNIK)
OCHERED = os.environ.get('P25_OCHERED', OCHERED)
VYHOD = os.environ.get('P25_VYHOD', VYHOD)
KARTA = os.environ.get('P25_KARTA', KARTA)
COLS = ['inn', 'predpriyatie', 'chelovek', 'telefon', 'mobilnyy', 'pochta',
        'kontakt_zakazchika', 'telefon_zakazchika', 'pochta_zakazchika',
        'company_inn', 'nomer', 'predmet', 'ssylka']
STOP = 12            # карточек подряд без новой фамилии — закрываем предприятие

# Машинные слова вперёд: замер на Tender.pro дал 22,0 % людей против 6,9 % на прочих.
MASHINNYE = ('компрессор', 'воздуходув', 'турбо', 'нагнетател', 'центробеж', 'ремонт',
             'экспертиз', 'диагностик', 'подшипник', 'ротор', 'запчаст', 'кипиа',
             'электродвигател', 'насос', 'обслуживани')


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def mobilnyy(t):
    c = re.sub(r'\D', '', t or '')
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return len(c) == 10 and c[0] == '9'


def familiya(imya):
    ch = re.sub(r'[^А-ЯЁа-яё ]', ' ', imya or '').split()
    return ch[0].lower() if ch else ''


def vzyat(url, tayminaut=420):
    zad = {'url': url, 'screenshot': False, 'proxy': '', 'return_html': True,
           'html_cap': 1400000, 'wait_ms': 9000}
    try:
        p = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                            json.dumps(zad, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=tayminaut)
    except subprocess.TimeoutExpired:
        return None, f'раннер не ответил за {tayminaut} с'
    try:
        d = json.loads(p.stdout[p.stdout.index('{'):]).get('data') or {}
    except (ValueError, json.JSONDecodeError):
        return None, (p.stdout or p.stderr or 'пусто')[-150:]
    h = d.get('html') or ''
    if not h:
        return None, f"тело пусто | error={str(d.get('error'))[:90]}"
    return h, ''


def ves(r):
    t = (r.get('predmet') or '').lower()
    return 0 if any(s in t for s in MASHINNYE) else 1


def main():
    predpriyatiy = dovod('--predpriyatiy', 10 ** 9)
    na_predpriyatie = dovod('--na-predpriyatie', 30)
    parallel = dovod('--parallel', 5)
    # Предел раннера: сверх 30 воркеров задачи не работают, а ждут.
    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)

    kartochki = chitat(ISHODNIK)
    if len(kartochki) < 1000:
        sys.exit(f'ОСТАНОВКА: в {ISHODNIK} всего {len(kartochki)} строк — обход не прошёл.')
    och = {r['inn']: r for r in chitat(OCHERED)}

    po_inn = defaultdict(list)
    for r in kartochki:
        if r.get('ssylka') and r.get('inn'):
            po_inn[r['inn']].append(r)

    # ПОРЯДОК ЗАДАЁТ ПАНЕЛЬ, А НЕ Я. Раньше я считал «пользу» сам по своей очереди: сначала
    # предприятия без технического человека. Это разумно, но это МОЙ взгляд на важность,
    # а продавец открывает панель, отсортированную ИХ приоритетом. 04.08 соседи отдали свои
    # группы: «добыть контакт» 542 (повод сильный, звонить некому) и «звонить сегодня» 158.
    # Из них моими карточками покрыто 292, и вот они идут первыми.
    # «Добыть контакт» ВПЕРЕДИ «звонить сегодня» намеренно: у вторых телефон уже есть,
    # а у первых повод есть, а звонить некому — то есть мой канал там и нужен.
    prior = {}
    put_p = os.path.join(C, 'PRIORITET-ot-sosedey.csv')
    for r in chitat(put_p):
        try:
            ball = float(r.get('score') or 0)
        except ValueError:
            ball = 0.0
        prior[r['inn']] = (0 if (r.get('gruppa') or '') == 'добыть контакт' else 1, -ball)
    if prior:
        print(f'  порядок задан соседями: {len(prior)} предприятий из их групп',
              file=sys.stderr)

    def polza(inn):
        o = och.get(inn) or {}
        # ОЧЕРЕДЬ P25 САМА НАЗЫВАЕТ ПОРЯДОК и отменяет оба правила ниже. Колонка `mesto` —
        # место по сумме покупок, единственная сортировка, заданная владельцем для покупателей.
        # Проверка идёт ДО `prior` намеренно: список приоритетов соседей собран под центробежку,
        # и предприятие, попавшее в оба списка, увело бы порядок P25 к чужой задаче — молча,
        # потому что оба ключа выглядят одинаково осмысленно.
        if o.get('mesto'):
            return (0, int(o['mesto']), 0, 0)
        if inn in prior:
            return (0,) + prior[inn] + (0,)
        net_teh = 0 if (o.get('lyudej_tehnicheskih') or '0') in ('', '0') else 1
        net_nom = 0 if (o.get('lyudej_s_telefonom') or '0') in ('', '0') else 1
        return (1, net_teh, net_nom, -len(po_inn[inn]))

    celi = sorted(po_inn, key=polza)
    # ЗАПИСЬ СО СБОЕМ — НЕ «ПРОЙДЕНО». Дефект найден 3-й сессией у себя 04.08 и проверен
    # здесь: её резюм считал записи с ошибкой пройденными, и 150 человек, по которым прибор
    # ответил «нет свободных каналов», навсегда остались бы в отчёте как «прошли, контактов
    # нет». Ложный ноль, закреплённый резюмом. У меня та же дыра: журнал писался и тогда,
    # когда все карточки предприятия не снялись. Теперь предприятие считается пройденным,
    # только если хоть одна карточка ДЕЙСТВИТЕЛЬНО разобрана.
    proydeno = {r['inn'] for r in chitat(KARTA)
                if str(r.get('pochemu') or '').startswith('обойдено')
                or int(str(r.get('lyudej') or 0) or 0) > 0}
    so_sboem = {r['inn'] for r in chitat(KARTA)} - proydeno
    if so_sboem:
        print(f'  в журнале {len(so_sboem)} предприятий со сбоем — будут переспрошены',
              file=sys.stderr)
    celi = [i for i in celi if i not in proydeno][:predpriyatiy]
    print(f'[ЭТП ГПБ, лица] карточек в файле {len(kartochki)}, предприятий {len(po_inn)}, '
          f'к обходу {len(celi)} (пройдено {len(proydeno)})', file=sys.stderr)
    if not celi:
        return

    novyy_v = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    novyy_k = not os.path.exists(KARTA) or os.path.getsize(KARTA) == 0
    fv = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    fk = open(KARTA, 'a', encoding='utf-8-sig', newline='')
    wk = csv.DictWriter(fk, fieldnames=['inn', 'predpriyatie', 'kartochek_vzyato',
                                        'lyudej', 's_mobilnym', 'ne_razobrano', 'pochemu'],
                        delimiter=';', extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'предприятий': 0, 'карточек': 0, 'людей': 0, 'с мобильным': 0,
           'карточки нет': 0, 'НЕ РАЗОБРАНО': 0, 'сбоев съёма': 0}
    lock = threading.Lock()

    def odno(inn):
        spisok = sorted(po_inn[inn], key=ves)[:na_predpriyatie]
        vidennye, lyudi, bez_novyh = set(), [], 0
        vzyato = ne_razobrano = net_kartochki = sboev = 0
        for r in spisok:
            if bez_novyh >= STOP:
                break
            h, err = vzyat(r['ssylka'])
            vzyato += 1
            if h is None:
                sboev += 1
                continue
            d = razbor.razobrat(h)
            if d.get('est') is None:
                # НЕ «контакта нет»: разобрать не удалось, подлежит перезапросу
                ne_razobrano += 1
                continue
            if d.get('est') is False:
                net_kartochki += 1
                continue
            fio = (d.get('contact_person') or '').strip()
            if not fio:
                fio = (razbor.razobrat_dom(h) or '').strip()
            if not fio:
                bez_novyh += 1
                continue
            f = familiya(fio)
            if f in vidennye:
                bez_novyh += 1
                continue
            vidennye.add(f)
            bez_novyh = 0
            lyudi.append({'chelovek': fio,
                          'telefon': (d.get('contact_phone') or '').strip(),
                          'pochta': (d.get('contact_email') or '').strip(),
                          'kontakt_zakazchika': (d.get('customer_contact') or '').strip(),
                          'telefon_zakazchika': (d.get('customer_phone') or '').strip(),
                          'pochta_zakazchika': (d.get('customer_email') or '').strip(),
                          'company_inn': (d.get('company_inn') or '').strip(),
                          'nomer': r.get('nomer') or '', 'predmet': r.get('predmet') or '',
                          'ssylka': r['ssylka']})
        return inn, lyudi, vzyato, ne_razobrano, net_kartochki, sboev

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for nomer, (inn, lyudi, vzyato, ne_raz, net_k, sboev) in enumerate(
                pool.map(odno, celi), 1):
            with lock:
                sch['предприятий'] += 1
                sch['карточек'] += vzyato
                sch['НЕ РАЗОБРАНО'] += ne_raz
                sch['карточки нет'] += net_k
                sch['сбоев съёма'] += sboev
                imya = (och.get(inn) or {}).get('predpriyatie') or ''
                s_mob = 0
                for x in lyudi:
                    mob = mobilnyy(x['telefon'])
                    if mob:
                        s_mob += 1
                    sch['людей'] += 1
                    wv.writerow(dict(x, inn=inn, predpriyatie=imya,
                                     mobilnyy='да' if mob else ''))
                sch['с мобильным'] += s_mob
                wk.writerow({'inn': inn, 'predpriyatie': imya, 'kartochek_vzyato': vzyato,
                             'lyudej': len(lyudi), 's_mobilnym': s_mob,
                             'ne_razobrano': ne_raz,
                             'pochemu': (f'{ne_raz} карточек не разобрано — перезапросить'
                                         if ne_raz else 'обойдено')})
                fv.flush()
                fk.flush()
                if nomer % 5 == 0 or lyudi:
                    print(f'  [гпб-лица] {nomer}/{len(celi)}: {sch}',
                          file=sys.stderr, flush=True)

    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}\n→ {KARTA}', file=sys.stderr)
    if sch['НЕ РАЗОБРАНО']:
        print(f'ВНИМАНИЕ: {sch["НЕ РАЗОБРАНО"]} карточек НЕ РАЗОБРАНЫ — это не «контакта '
              'нет», их надо перезапросить', file=sys.stderr)


if __name__ == '__main__':
    main()
