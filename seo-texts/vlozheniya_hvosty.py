# -*- coding: utf-8 -*-
"""Хвосты вложений ЕИС: окна, которые `vlozheniya.py --lica` отбросил пределом.

ЗАЧЕМ ОТДЕЛЬНЫЙ СКРИПТ, А НЕ ПРАВКА ПРЕДЕЛА. `shag_lica` открывает
`vlozheniya-lica.csv` на 'w' — то есть перезапуск с поднятым пределом СТЁР БЫ уже
добытых людей и заново потратил бы квоту на всё. Здесь считаются ровно окна
с 41-го и дальше, а результат ложится в свой файл; свод собирается слиянием.

Пределы `vlozheniya.py`: PREDEL_OKON=40 окон и PREDEL_ZNAKOV=40000 знаков на файл.
Документ, где должность упомянута 71 раз, — это лист согласования или протокол,
то есть как раз плотная россыпь подписей. Отброшенный хвост там и есть люди.
"""
import csv, json, os, re, sys, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G
from vlozheniya import DOLZH, cifry, OUT, RAB

TEKST = os.path.join(OUT, 'vlozheniya-tekst.jsonl')
S_OKNA, PREDEL_ZNAKOV = 40, 40000  # с какого окна начинается хвост


def okna(t):
    rangi = [(max(0, m.start() - 300), m.start() + 400) for m in DOLZH.finditer(t)]
    slito = []
    for a, b in rangi:
        if slito and a <= slito[-1][1]:
            slito[-1] = (slito[-1][0], max(slito[-1][1], b))
        else:
            slito.append((a, b))
    return slito


def sobrat():
    """Только хвосты. Возвращает список (файл, закупка, текст-хвоста, сколько окон)."""
    po_sha, rows = {}, []
    with open(TEKST, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    for r in rows:
        if r.get('tekst'):
            po_sha[r['sha256']] = r['tekst']
    for r in rows:
        if not r.get('tekst') and r.get('kopiya_ot'):
            r['tekst'] = po_sha.get(r['sha256'], '')
    vidno, zad = set(), []
    for r in rows:
        if r.get('skan_ili_pusto') or r.get('otkaz') or not r.get('tekst'):
            continue
        k = (r['zakupka'], r['sha256'])
        if k in vidno:
            continue
        vidno.add(k)
        sl = okna(r['tekst'])
        # Хвост по ОКНАМ и хвост по ЗНАКАМ — разные обрезки, и вторая срабатывает даже
        # там, где окон меньше сорока. Считаю обе, иначе часть отброшенного снова уедет.
        golova = sl[:S_OKNA]
        telo_g = '\n---\n'.join(r['tekst'][a:b] for a, b in golova)
        hvost = sl[S_OKNA:]
        dobav = ''
        if len(telo_g) > PREDEL_ZNAKOV:
            dobav = telo_g[PREDEL_ZNAKOV:]
        if not hvost and not dobav:
            continue
        telo = (dobav + ('\n---\n' if dobav and hvost else '')
                + '\n---\n'.join(r['tekst'][a:b] for a, b in hvost))
        zad.append((r['fajl'], r['zakupka'], telo[:PREDEL_ZNAKOV], len(hvost),
                    len(dobav)))
    return zad


PROMPT = """Ты читаешь куски документов закупки промышленного предприятия (техзадание,
извещение, протокол, лист согласования). Нужны люди в ТЕХНИЧЕСКИХ ролях: главный инженер,
главный механик, главный энергетик, начальник цеха или компрессорной, их заместители, инженер
ОГМ/ОГЭ/КИПиА, технический директор. Снабженец помечается отдельно и стоит ниже.

ПРАВИЛА, нарушать нельзя:
1. **Ни одного телефона и ни одной фамилии, которых нет во входном тексте.** Выдуманный
   контакт хуже пропуска: по нему позвонят чужому человеку.
2. Число из десяти цифр — не обязательно телефон. Если рядом стоит «ИНН», «ОГРН», «р/с»,
   «КПП» или это номер документа — это не телефон, не пиши его.
3. Не считай технической ролью «главный инженер проекта» и «ГИП»: это проектировщик, машину
   на площадке он не выбирает. Также не считай «механик гаража», «начальник транспортного
   цеха», «инженер по закупкам», «инженер-сметчик».
4. Если людей в тексте нет — верни пустой список. Не угадывай.

ОТВЕТ — строго JSON, без пояснений:
{"lyudi":[{"imya":"","dolzhnost":"","rol":"техническая|снабжение|неясно","telefon":"",
"pochta":"","citata":"кусок текста, где это написано, до 150 знаков"}]}

ТЕКСТ:
"""


def main():
    zad = sobrat()
    okon = sum(z[3] for z in zad)
    znakov = sum(z[4] for z in zad)
    print(f'файлов с хвостом: {len(zad)} | отброшенных окон: {okon} | '
          f'знаков сверх предела: {znakov}', file=sys.stderr)
    if '--zamer' in sys.argv or not zad:
        for f, z, t, n, d in sorted(zad, key=lambda x: -x[3])[:15]:
            print(f'  окон {n:4d}  знаков {d:6d}  {z}  {os.path.basename(f)[:60]}',
                  file=sys.stderr)
        return
    client = G.make_client()
    lock, itog = threading.Lock(), []
    sch = {'lyudey': 0, 'teh': 0, 'vydumka': 0, 'err': 0}

    def odin(z):
        fajl, zak, telo, _n, _d = z
        try:
            o = G.call(client, [{'role': 'user', 'content': PROMPT + telo}],
                       model='claude-fable-5', attempts=4)
            txt = ''.join(b.text for b in o.content if b.type == 'text')
            m = re.search(r'\{.*\}', txt, re.S)
            return fajl, zak, telo, (json.loads(m.group(0)) if m else None)
        except Exception as e:  # noqa: BLE001
            return fajl, zak, telo, {'__err': f'{type(e).__name__}: {str(e)[:80]}'}

    with ThreadPoolExecutor(max_workers=4) as pool:
        for fajl, zak, telo, res in pool.map(odin, zad):
            with lock:
                if not res or '__err' in (res or {}):
                    sch['err'] += 1
                    print(f'  сбой {os.path.basename(fajl)[:50]}: '
                          f'{(res or {}).get("__err")}', file=sys.stderr)
                    continue
                cif = cifry(telo)
                for ch in res.get('lyudi') or []:
                    t = ch.get('telefon') or ''
                    est = (not t) or (cifry(t)[-10:] and cifry(t)[-10:] in cif)
                    if t and not est:
                        sch['vydumka'] += 1
                    itog.append({**ch, 'fajl': fajl, 'zakupka': zak,
                                 'telefon_est_v_tekste': '1' if est else '',
                                 'iz_hvosta': '1'})
                    sch['lyudey'] += 1
                    if ch.get('rol') == 'техническая':
                        sch['teh'] += 1
    out = os.path.join(OUT, 'vlozheniya-lica-hvosty.csv')
    cols = ['zakupka', 'fajl', 'imya', 'dolzhnost', 'rol', 'telefon', 'pochta',
            'telefon_est_v_tekste', 'iz_hvosta', 'citata']
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(itog)
    print(f'из хвостов: людей {sch["lyudey"]}, технических {sch["teh"]}, '
          f'номеров не из текста {sch["vydumka"]}, сбоев {sch["err"]} → {out}', file=sys.stderr)


if __name__ == '__main__':
    main()
