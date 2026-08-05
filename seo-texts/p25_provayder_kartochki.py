# -*- coding: utf-8 -*-
"""Прочитать провайдером 1 070 карточек, где регулярка молчит. С заслоном от выдумки.

ПРАВИЛО ВЛАДЕЛЬЦА: всю тяжёлую работу — через провайдерский API. За смену я не сделала
по нему ни одного рабочего вызова: проверила связь двумя пробами и ушла чинить шаблоны.
Владелец это увидел по журналу шлюза — четыре часа простоя.

ЧТО ИМЕННО ОТДАЁТСЯ ПРОВАЙДЕРУ, И ПОЧЕМУ НЕ ВСЁ. Из 9 335 карточек площадки регулярка
разобрала 4 316, ещё 3 061 не содержат контакта вовсе. Остаются 1 644 щели, из которых
574 закрылись починкой шаблона телефона (пятизначные коды городов). Провайдеру идут
только 1 070 — там, где вёрстка нестандартная и регулярка молчит по существу, а не по
своей узости. Порядок работ: сперва починить дешёвый прибор, потом тратить платный.

ГЛАВНЫЙ ЗАСЛОН — ПРОТИВ ВЫДУМКИ, И ОН МЕХАНИЧЕСКИЙ. Модель обязана вернуть для каждого
контакта ДОСЛОВНУЮ подстроку исходного текста (`citata`). Прежде чем принять находку, я
проверяю, что эта подстрока в тексте ЕСТЬ, и что номер из неё сходится по цифрам с
номером в ответе. Не «прошу не выдумывать», а сверка с источником: доверия к своему
разбору у меня за смену поубавилось, а к чужому его и не было.

ВТОРОЙ ЗАСЛОН — ТОТ ЖЕ, ЧТО У РЕГУЛЯРКИ. Роль берётся из слов заказчика («по техническим
вопросам»), должность — из текста, номер нормализуется цифрами, мобильный отличается от
городского кодом 79, номер у двух и более людей личным не считается. Правила общие для
обоих разборов, иначе выгрузка станет разносортной.

Запуск:  python3 p25_provayder_kartochki.py [--lim N] [--pachka N] [--potokov N]
Поток `p25-provayder.jsonl`, повторный запуск продолжает с места.
"""
import collections
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G  # noqa: E402
import p25_telefon_shablon as TEL  # noqa: E402

TUT = '/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/scratchpad'
VHOD = os.path.join(TUT, 'P25-KARTY-OSTATOK-3S.jsonl')
POTOK = os.path.join(TUT, 'p25-provayder.jsonl')
MODEL = 'claude-fable-5'

PROMPT = '''Ты разбираешь текст карточки закупки российского предприятия. Задача одна:
найти ЛЮДЕЙ и их КОНТАКТЫ, если они там есть.

Верни СТРОГО json без пояснений и без markdown-ограды:
{"lyudi": [{"fio": "...", "dolzhnost": "...", "rol": "...", "telefon": "...",
            "dobavochnyy": "...", "pochta": "...", "citata": "..."}]}

Правила, нарушение любого делает находку негодной:
1. `citata` — ДОСЛОВНАЯ подстрока присланного текста, 40-200 знаков, внутри которой
   стоит и человек, и его контакт. Я проверю её наличие в тексте посимвольно. Если
   дословную подстроку привести нельзя — человека не возвращай вовсе.
2. Ничего не додумывай. Нет отчества — пиши как в тексте. Нет должности — пустая строка.
   Не выводи должность из роли и роль из должности.
3. `rol` — только если заказчик НАЗВАЛ её словами: «по техническим вопросам»,
   «по вопросам участия», «контактное лицо», «ответственный». Пиши эти слова дословно.
4. `dolzhnost` — только если она НАПИСАНА рядом с человеком («главный энергетик»).
   Должность соседа по списку этому человеку не принадлежит.
5. `telefon` — как написан в тексте, вместе с кодом города. Добавочный отдельным полем.
6. Если людей с контактами нет — верни {"lyudi": []}. Пустой ответ лучше выдуманного.

Текст карточки:
'''


def cifry(s):
    return TEL.cifry(s)


def razobrat_otvet(syroy):
    """Вынуть json из ответа. Модель иногда обрамляет его оградой — снимаем."""
    t = (syroy or '').strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t)
    m = re.search(r'\{.*\}', t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


def proverit(chelovek, tekst):
    """Механическая сверка находки с источником. Возвращает (годен, причина)."""
    c = (chelovek.get('citata') or '').strip()
    if not c:
        return False, 'цитаты нет'
    # Пробелы в тексте я схлопывала при сборе, поэтому сверяю по схлопнутому виду.
    ravno = re.sub(r'\s+', ' ', c)
    if ravno not in re.sub(r'\s+', ' ', tekst):
        return False, 'цитаты НЕТ в исходном тексте — выдумана'
    fio = (chelovek.get('fio') or '').strip()
    if not fio:
        return False, 'человек не назван'
    # ФАМИЛИЯ ВНУТРИ АДРЕСА ПОЧТЫ — ЭТО НЕ НАЗВАННЫЙ ЧЕЛОВЕК. Первая же дюжина
    # карточек дала «Igor Alimenko» с цитатой «направлять на адрес
    # Igor.Alimenko@rusal.com , тел. (81366) 94-910»: человека в тексте никто не
    # называл, модель разобрала его из local-part. Моя проверка «фамилия есть в
    # цитате» это пропускала, потому что подстрока и правда есть — внутри адреса.
    #
    # Находка настоящая и нужная: за этим адресом стоит живой человек, и телефон
    # рядом с ним. Но звать её «названным человеком» нельзя — это вывод, а не запись.
    # Поэтому не отвергаю, а РАЗДЕЛЯЮ: вид находки называется словом.
    fam = fio.split()[0]
    bez_pochty = re.sub(r'[\w.\-]+@[\w.\-]+', ' ', ravno)
    if not re.search(r'\b' + re.escape(fam) + r'\b', bez_pochty, re.I):
        if re.search(re.escape(fam), ravno, re.I):
            chelovek['imya_otkuda'] = 'выведено из адреса почты, в тексте не названо'
        else:
            return False, 'фамилии нет в собственной цитате'
    else:
        chelovek['imya_otkuda'] = 'названо в тексте карточки'
    tel = (chelovek.get('telefon') or '').strip()
    if tel:
        cif = cifry(tel)
        if len(cif) != 11:
            return False, 'номер не нормализуется в 11 цифр'
        # Номер обязан стоять В ЦИТАТЕ: иначе он взят откуда-то ещё.
        v_citate = [x['cifry'] for x in TEL.nomera(ravno)]
        if cif not in v_citate:
            return False, 'номера нет в собственной цитате'
    if not tel and not (chelovek.get('pochta') or '').strip():
        return False, 'ни телефона, ни почты'
    return True, ''


def main():
    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 10 ** 9
    pot = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 3

    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if not z.get('err'):
                gotovo.add(str(z.get('tender_id')))

    karty = []
    for ln in open(VHOD, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if str(z.get('tender_id')) not in gotovo:
            karty.append(z)
    karty = karty[:lim]
    print('к разбору %d карточек, пройдено ранее %d' % (len(karty), len(gotovo)),
          file=sys.stderr, flush=True)

    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = collections.Counter()
    klient = G.make_client()

    def odna(k):
        tekst = (k.get('tekst') or '')[:9000]
        try:
            otvet = G.call(klient, [{'role': 'user', 'content': PROMPT + tekst}],
                           model=MODEL, attempts=3)
            syroy = ' '.join(b.text for b in otvet.content if b.type == 'text')
            tokenov = (otvet.usage.input_tokens, otvet.usage.output_tokens)
        except Exception as e:  # noqa: BLE001
            return {**{x: k.get(x) for x in ('tender_id', 'company_id', 'company')},
                    'err': '%s: %s' % (type(e).__name__, str(e)[:120]), 'lyudi': []}
        d = razobrat_otvet(syroy)
        if d is None:
            return {**{x: k.get(x) for x in ('tender_id', 'company_id', 'company')},
                    'err': 'ответ не разобрался в json', 'syroy': syroy[:400], 'lyudi': []}
        godnye, otvergnutye = [], []
        for ch in (d.get('lyudi') or []):
            if not isinstance(ch, dict):
                continue
            ok, prichina = proverit(ch, tekst)
            (godnye if ok else otvergnutye).append(
                dict(ch, **({} if ok else {'otvergnut': prichina})))
        return {**{x: k.get(x) for x in ('tender_id', 'company_id', 'company')},
                'err': '', 'tokenov': tokenov, 'lyudi': godnye,
                'otvergnuto': otvergnutye}

    with ThreadPoolExecutor(max_workers=pot) as ex:
        for i, r in enumerate(ex.map(odna, karty), 1):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                f.flush()
                if r.get('err'):
                    sch['сбой: ' + r['err'][:40]] += 1
                else:
                    sch['ЛЮДЕЙ ПРИНЯТО'] += len(r['lyudi'])
                    for o in r.get('otvergnuto') or []:
                        sch['отвергнуто: ' + o.get('otvergnut', '?')] += 1
                    if not r['lyudi'] and not r.get('otvergnuto'):
                        sch['людей в карточке нет'] += 1
                if i % 25 == 0:
                    print('  %d/%d, принято %d' % (i, len(karty), sch['ЛЮДЕЙ ПРИНЯТО']),
                          file=sys.stderr, flush=True)
    f.close()
    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({'карточек спрошено': len(karty)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
