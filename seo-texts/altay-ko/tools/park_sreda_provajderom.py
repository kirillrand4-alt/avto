# -*- coding: utf-8 -*-
"""СРЕДА машины из текста заключения ЭПБ — провайдером, там где регулярка её не назвала.

ЗАЧЕМ ИМЕННО СРЕДА. Владелец продаёт компрессоры, генераторы АЗОТА и КИСЛОРОДА. Среда и
решает, наш ли это товар и что предлагать: воздушному компрессору — осушитель и ресивер,
азотной станции — мембраны, кислородной — адсорбент. В своде 31 628 фактов, и **у 19 621
среда пуста**: мой список слов ловит её, только если слово стоит прямо в объекте
(«компрессор аммиачный»), а чаще среда названа косвенно — «станция получения азота»,
«воздухоразделительная установка», холодильный контур, ГПА на природном газе.

СТРОГО ИЗ ТЕКСТА. Модель обязана вернуть «не названа», если среды в тексте нет. Догадка по
отрасли запрещена прямо: у мясокомбината бывает и аммиак, и воздух, и придуманная среда
попадёт в письмо клиенту как факт о его машине.

Цепочка моделей — `park_zapas_modeli`: слово владельца «продолжай на гемини», поэтому первым
идёт gemini-3.5-flash (проверен живым вызовом), claude-fable-5 остаётся резервом.
"""
import csv, json, os, re, sys, threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G
import park_zapas_modeli as Z

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
VHOD = os.path.join(L, 'PARK-FAKTY-2S-EPB-POLNYE.csv')
VYHOD = os.path.join(L, 'PARK-SREDA-PROVAJDER-2S.jsonl')
PACHKA = int(os.environ.get('PACHKA', '25'))
NITEY = int(os.environ.get('NITEY', '4'))
PREDEL = int(os.environ.get('PREDEL', '2000'))

PROMPT = """Ты разбираешь строки реестра заключений промышленной безопасности.
Для КАЖДОЙ строки верни JSON-объект с полями:
  n        — номер строки, как дан
  sreda    — что машина сжимает или производит, СТРОГО ИЗ ТЕКСТА, одно из:
             воздух | азот | кислород | аммиак | водород | природный газ | попутный газ |
             углекислота | гелий | хладагент | другое | не названа
             Пиши «не названа», если в тексте среды нет. НЕ УГАДЫВАЙ по отрасли предприятия:
             у мясокомбината бывает и аммиак, и воздух, и придуманная среда уйдёт клиенту
             как факт про его машину.
  chem     — короткая цитата ИЗ ЭТОЙ ЖЕ строки, по которой ты определил среду; пустая
             строка, если среда не названа
  mks      — true, если машина названа МОДУЛЬНОЙ или в блок-контейнере (МКС), иначе false
  pks      — true, если машина названа ПЕРЕДВИЖНОЙ, на шасси или прицепе (ПКС), иначе false

Отвечай ТОЛЬКО массивом JSON, без пояснений. Строки:
"""


def main():
    rows = [x for x in csv.DictReader(open(VHOD, encoding='utf-8-sig'), delimiter=';')
            if not (x.get('sreda') or '').strip()]
    gotovo = set()
    if os.path.exists(VYHOD):
        for ln in open(VYHOD, encoding='utf-8'):
            try:
                gotovo.add(json.loads(ln)['klyuch'])
            except (json.JSONDecodeError, KeyError):
                pass
    celi = [x for x in rows if (x['inn'] + '|' + x['citata'][:60]) not in gotovo][:PREDEL]
    print(f'без среды всего {len(rows)}, к разбору {len(celi)}', file=sys.stderr, flush=True)
    if not celi:
        return
    client = G.make_client()
    f = open(VYHOD, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = {'пачек': 0, 'строк': 0, 'среда названа': 0, 'МКС': 0, 'ПКС': 0, 'сбоев': 0}

    def pachka(i):
        kus = celi[i:i + PACHKA]
        tekst = '\n'.join(f"{n}. {x['citata']}" for n, x in enumerate(kus))
        try:
            # ЦЕПОЧКА МОДЕЛЕЙ, а не одна: порвался claude — идёт gemini, потом gpt.
            # Слово владельца: «по провайдеру если рвётся, можешь взять модели другие».
            otvet, chem = Z.sprosit([{'role': 'user', 'content': PROMPT + tekst}])
        except Exception as e:  # noqa: BLE001
            with lock:
                sch['сбоев'] += 1
            print(f'  сбой пачки {i}: {str(e)[:90]}', file=sys.stderr, flush=True)
            return
        m = re.search(r'\[.*\]', otvet or '', re.S)
        try:
            dannye = json.loads(m.group(0)) if m else []
        except json.JSONDecodeError:
            dannye = []
        with lock:
            sch['пачек'] += 1
            for d in dannye:
                try:
                    x = kus[int(d.get('n', -1))]
                except (ValueError, IndexError):
                    continue
                sch['строк'] += 1
                sr = (d.get('sreda') or '').strip()
                if sr and sr != 'не названа':
                    sch['среда названа'] += 1
                if d.get('mks'):
                    sch['МКС'] += 1
                if d.get('pks'):
                    sch['ПКС'] += 1
                f.write(json.dumps({'klyuch': x['inn'] + '|' + x['citata'][:60],
                                    'inn': x['inn'], 'sreda': sr,
                                    'chem': (d.get('chem') or '').strip(),
                                    'mks': bool(d.get('mks')), 'pks': bool(d.get('pks')),
                                    'ssylka': x['ssylka'], 'citata': x['citata'],
                                    'chem_dobyto': chem},
                                   ensure_ascii=False) + '\n')
            f.flush()
            if sch['пачек'] % 5 == 0:
                print(f'  {sch}', file=sys.stderr, flush=True)

    with ThreadPoolExecutor(max_workers=NITEY) as p:
        list(p.map(pachka, range(0, len(celi), PACHKA)))
    print(f'готово: {sch}', file=sys.stderr)


main()
