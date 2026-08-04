# -*- coding: utf-8 -*-
"""Вернуть в панель компании, скрытые по НЕСОВПАВШЕЙ МАРКЕ, у которых центробежность доказана текстом.

РЕШЕНИЕ ВЛАДЕЛЬЦА 04.08: «эти вернуть, 2 партии». Партии две и они вложены одна в другую:
  * 206 — центробежность доказана ТЕКСТОМ карточки (цитата закупки или заключения ЭПБ), а не
    маркой;
  * 14 из этих 206 — по тексту ещё и ВОЗДУШНЫЕ, то есть прямая цель.

ПОЧЕМУ ВОЗВРАТ ОБОСНОВАН, а не просто «начальник велел». Партия 326 скрыта с причиной «марки
в фактах не совпали со словарём воздушных центробежных — выкидываем». Словарь марок измерен:
надёжны 39 обозначений из 2 915, поле `model` панели подтверждает 102 из 307, а девять
вердиктов пришли не от компрессоров вовсе (Л-35/11-300 — риформинг, УКПГ-4 — подготовка газа).
Отсутствие марки в таком словаре означает, что марку не записали в закупке, — это отсутствие
данных, а не доказательство обратного. Скрывать по признаку, которого нет, значит терять
предприятия с живой машиной: среди скрытых «Турбовоздуходувка (турбокомпрессор) Napier –
C045/C», «Поставка нагнетателя воздуха», заключение ЭПБ на техустройство ОПО I класса.

ЧТО НЕ ВОЗВРАЩАЕТСЯ. Оставшиеся 120 из партии — те, у кого в карточке нет ни одной цитаты со
словами машины. У них доказательства нет ни в марке, ни в тексте, и возвращать их значило бы
подменить одну поспешность другой.

ОБРАТИМОСТЬ. Перед удалением каждая снимаемая строка выгружается на дроп файлом
`VAZHNOE-3s-SNYATYE-SKRYTIYA-<метка>.csv` со всеми полями (inn, kind, value, reason, username,
created_at). Восстановить можно построчно, ничего не домысливая.

Использование:
    python3 vernut_skrytye.py --pokazat        # только посчитать, ничего не менять
    python3 vernut_skrytye.py --primenit       # снять скрытия по узкому чтению
    python3 vernut_skrytye.py --primenit --shiroko   # плюс воздуходувки без слова «центробежный»
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

SCRIPT = r'''
import csv, io, json, re, sqlite3, sys

PRIMENIT = 'PRIMENIT' in sys.argv
# ШИРОКОЕ ЧТЕНИЕ включено отдельным решением владельца 04.08: «верни 74 тоже». Слово
# «воздуходувка» без «центробежный» рядом теперь считается доказательством машины — на
# опасном производственном объекте воздуходувка это промышленная машина, а не инструмент,
# и бытовое от неё отделяет отдельный отсев BYT, а не отсутствие слова «центробежный».
SHIROKO = 'SHIROKO' in sys.argv
sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))

# Партия определяется ТЕКСТОМ причины, а не временем: подпись у всех admin, и отличить
# массовое решение можно только по его формулировке.
PARTIYA = "kind='company' and coalesce(reason,'') like 'марки в фактах не совпали%'"

# ШАБЛОН МАШИНЫ — РОВНО ТОТ, ПО КОТОРОМУ СЧИТАЛИСЬ 206 И 14. Первая правка добавила сюда
# «воздуходувк» и «воздухонагнетат», и набор вырос до 305 предприятий, из них 120 воздушных.
# Владелец одобрил ДРУГИЕ числа — 206 и 14, — и молча вернуть на треть больше значило бы
# подменить его решение своим. Поэтому здесь узкий шаблон, а разница считается отдельно и
# уходит в файл на дроп как предложение, а не как сделанное.
MASHINA = re.compile(r'центробежн|турбокомпрессор|турбовоздуходувк|нагнетател', re.I)
SHIRE = re.compile(r'воздуходувк|воздухонагнетат', re.I)
VOZDUH = re.compile(r'воздух|воздушн|воздуходувк|воздухонагнетат|пневмо|дутьев', re.I)
GAZ = re.compile(r'природн\w*\s*газ|\bГПА\b|газоперекач|\bДКС\b|попутн\w*\s*газ|синтез-газ|'
                 r'азот|кислород|аммиак|водород|этилен|пропилен|сероводород', re.I)
# Бытовое и автомобильное отсекается и здесь: садовый листодув с формулировкой «воздуходувка»
# прошёл бы проверку текстом, а машиной не является.
BYT = re.compile(r'садов|листодув|ручн\w+|аккумулятор|бензинов|высоторез|триммер|газонокосил|'
                 r'кусторез|гарнитур|IVECO|КАМАЗ|MAN\b|SCANIA|ЯМЗ|\bТКР\b|МОБИЛ|STIHL|ECHO|'
                 r'HUSQVARNA|MAKITA|BOSCH|CHAMPION', re.I)

stroki = sale.execute(
    f"select rowid, inn, kind, coalesce(value,''), coalesce(reason,''), "
    f"coalesce(username,''), coalesce(created_at,'') from hidden_item where {PARTIYA}"
).fetchall()

k_vozvratu, vozdushnye, bez_dokazatelstv = [], 0, 0
shire_predlozhit = []
for rid, inn, kind, value, reason, user, kogda in stroki:
    fakty = sale.execute(
        "select coalesce(quote,''), coalesce(source,'') from f.fact where inn = ? limit 60",
        (inn,)).fetchall()
    uliki = [(q, s) for q, s in fakty if MASHINA.search(q) and not BYT.search(q)]
    shirokie = [(q, s) for q, s in fakty if SHIRE.search(q) and not BYT.search(q)]
    if SHIROKO and not uliki and shirokie:
        uliki = shirokie
    if not uliki:
        # Широкое чтение: «воздуходувка» на ОПО — тоже наша машина, но одобрения на эту
        # часть не было. Копим отдельно и НЕ снимаем.
        sh = shirokie
        if sh:
            shire_predlozhit.append({'inn': inn, 'citata': sh[0][0][:200],
                                     'istochnik': sh[0][1],
                                     'vozduh': bool(VOZDUH.search(sh[0][0])
                                                    and not GAZ.search(sh[0][0]))})
        bez_dokazatelstv += 1
        continue
    v = [u for u in uliki if VOZDUH.search(u[0]) and not GAZ.search(u[0])]
    if v:
        vozdushnye += 1
    k_vozvratu.append({'rowid': rid, 'inn': inn, 'kind': kind, 'value': value,
                       'reason': reason, 'username': user, 'created_at': kogda,
                       'partiya': ('воздух по тексту' if v else
                                   'центробежность по тексту, среда не названа'),
                       'chtenie': ('широкое: воздуходувка без слова «центробежный»'
                                   if SHIROKO and uliki is shirokie else 'узкое'),
                       'ulik': len(uliki),
                       'citata': (v[0][0] if v else uliki[0][0])[:200],
                       'istochnik': (v[0][1] if v else uliki[0][1])})

itog = {'v_partii': len(stroki), 'k_vozvratu': len(k_vozvratu),
        'iz_nih_vozdushnyh': vozdushnye,
        'ostayutsya_skrytymi_net_teksta': bez_dokazatelstv,
        'shirokoe_chtenie_predlozhit': len(shire_predlozhit),
        'shirokoe_iz_nih_vozdushnyh': sum(1 for x in shire_predlozhit if x['vozduh']),
        'primeneno': False}

if PRIMENIT and k_vozvratu:
    # СНАЧАЛА БЭКАП, ПОТОМ УДАЛЕНИЕ. Строку скрытия восстановить неоткуда, если её стереть
    # не записав: в hidden_item нет истории.
    buf = io.StringIO()
    pole = ['rowid', 'inn', 'kind', 'value', 'reason', 'username', 'created_at', 'partiya',
            'chtenie', 'ulik', 'citata', 'istochnik']
    w = csv.DictWriter(buf, fieldnames=pole, delimiter=';')
    w.writeheader()
    w.writerows(k_vozvratu)
    with open(r'C:\seostat\drop\3s-snyatye-skrytiya.csv', 'w', encoding='utf-8-sig',
              newline='') as f:
        f.write(buf.getvalue())
    itog['bekap'] = r'C:\seostat\drop\3s-snyatye-skrytiya.csv'
    sale.executemany('delete from hidden_item where rowid = ?',
                     [(z['rowid'],) for z in k_vozvratu])
    sale.commit()
    itog['primeneno'] = True
    # Предложение по широкому чтению кладём рядом с бэкапом — чтобы решение владельца
    # принималось по файлу, а не по памяти о разговоре.
    if shire_predlozhit:
        b2 = io.StringIO()
        w2 = csv.DictWriter(b2, fieldnames=['inn', 'vozduh', 'istochnik', 'citata'],
                            delimiter=';')
        w2.writeheader()
        w2.writerows(shire_predlozhit)
        with open(r'C:\seostat\drop\3s-predlozhenie-shirokoe-chtenie.csv', 'w',
                  encoding='utf-8-sig', newline='') as f2:
            f2.write(b2.getvalue())
    itog['ostalos_skrytiy_company'] = sale.execute(
        "select count(distinct inn) from hidden_item where kind='company'").fetchone()[0]
    itog['vidno_kompaniy'] = (sale.execute('select count(*) from f.company').fetchone()[0]
                              - itog['ostalos_skrytiy_company'])

for z in k_vozvratu[:400]:
    print('REC ' + json.dumps({k: z[k] for k in ('inn', 'partiya', 'ulik', 'istochnik',
                                                 'citata')}, ensure_ascii=False))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def zapustit(primenit, shiroko=False):
    dest = r'C:\sender\_ops\3s_vernut_skrytye.py'
    R.submit('enrich_contacts', {'op': 'panel_file_put',
                                 'files': [{'dest': dest,
                                            'b64': base64.b64encode(SCRIPT.encode()).decode()}]},
             timeout=300)
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': dest,
                  'argv': (['PRIMENIT'] if primenit else []) + (['SHIROKO'] if shiroko else []),
                  'timeout': 600},
                 timeout=900)
    d = r.get('data') or {}
    hvost = d.get('stdout_tail') or d.get('stderr_tail') or ''
    zapisi, itog = [], None
    for s in hvost.splitlines():
        s = s.strip()
        if s.startswith('REC '):
            try:
                zapisi.append(json.loads(s[4:]))
            except ValueError:
                pass
        elif s.startswith('ИТОГ '):
            itog = json.loads(s[5:])
    if itog is None:
        print('строки ИТОГ нет. Хвост:', hvost[-400:], file=sys.stderr)
        return None
    itog['zapisi'] = zapisi
    itog['poteryano_v_hvoste'] = itog['k_vozvratu'] - len(zapisi)
    return itog


def main():
    primenit = '--primenit' in sys.argv
    d = zapustit(primenit, '--shiroko' in sys.argv)
    if not d:
        sys.exit(1)
    print(f'в партии «марка не совпала»: {d["v_partii"]}', file=sys.stderr)
    print(f'к возврату: {d["k_vozvratu"]} (из них воздушных по тексту {d["iz_nih_vozdushnyh"]})',
          file=sys.stderr)
    print(f'остаются скрытыми, текста нет вовсе: {d["ostayutsya_skrytymi_net_teksta"]}',
          file=sys.stderr)
    print(f'ОТДЕЛЬНО, решения не было: широкое чтение («воздуходувка», '
          f'«воздухонагнетательная») дало бы ещё {d["shirokoe_chtenie_predlozhit"]} '
          f'предприятий, из них воздушных {d["shirokoe_iz_nih_vozdushnyh"]} — '
          f'не снимаю, кладу файлом', file=sys.stderr)
    if d['poteryano_v_hvoste'] > 0:
        print(f'в хвост вывода не поместилось {d["poteryano_v_hvoste"]} записей — '
              f'на решение это не влияет, снятие идёт по базе, а не по печати', file=sys.stderr)
    if d['primeneno']:
        print(f'СНЯТО. Бэкап: {d.get("bekap")}', file=sys.stderr)
        print(f'скрытых компаний осталось {d["ostalos_skrytiy_company"]}, '
              f'видно {d["vidno_kompaniy"]}', file=sys.stderr)
    else:
        print('ничего не менялось (нужен --primenit)', file=sys.stderr)


if __name__ == '__main__':
    main()
