# -*- coding: utf-8 -*-
"""Принять чужой список сайтов (чеко и любой другой) и провести его через нашу проверку.

ЗАЧЕМ ОТДЕЛЬНЫЙ ПРИЁМНИК. Домен из чеко — это УТВЕРЖДЕНИЕ АГРЕГАТОРА, а не первоисточник.
Залить его прямо в `company.sayt` нельзя: приёмка 3-й сессии первым и самым сильным условием
сравнивает хост страницы с этим полем, и ошибка здесь молча подтвердит чужого человека.
Поэтому чужой список не «вливается», а проходит те же три ступени, что и мой собственный:

    вес 1  домен назван источником, ничем не подтверждён          кандидат
    вес 2  название предприятия целиком узнаётся в тексте сайта   годен
    вес 3  ИНН предприятия найден НА СТРАНИЦЕ сайта               годен, первоисточник

ЗАСЛОН СПОРНОГО ДОМЕНА (правило 3-й сессии, у меня уже сработало): домен, на который
претендуют два разных ИНН, не принадлежит ни одному. `sibur.ru` заявили пять юрлиц,
`akkermann.ru` два — это сайты групп, и в `company.sayt` они идти не должны.

ВХОД. Любой CSV с колонками, где есть ИНН и домен — имена колонок ищутся сами
(`inn`/`ИНН`, `sayt`/`sait`/`site`/`domen`/`сайт`), разделитель `;` или `,` определяется сам.
Чужой файл не обязан быть в моём формате: подстраиваться должен приёмник, а не отправитель.

Использование:
    python3 p25_prinyat_sayty.py --fajl <файл> [--metka cheko]
    затем: p25_sayt_podtverzhdenie.py, p25_karta_sayta.py, p25_lyudi_so_stranic.py
"""
import csv
import os
import re
import sys
from collections import defaultdict

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
OCHERED = os.path.join(L, 'P25-OCHERED.csv')

IMENA_INN = ('inn', 'inn_zakazchika', 'инн', 'ИНН')
IMENA_SAYT = ('sayt', 'sait', 'site', 'domen', 'domain', 'url', 'сайт', 'домен')


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat_gibko(put):
    """Разделитель и имена колонок определяются сами. Чужой файл не обязан быть моим."""
    syro = open(put, encoding='utf-8-sig').read()
    pervaya = syro.split('\n', 1)[0]
    razd = ';' if pervaya.count(';') >= pervaya.count(',') else ','
    return list(csv.DictReader(syro.splitlines(), delimiter=razd)), razd


def pole(row, imena):
    for k in row:
        if (k or '').strip().lower() in imena:
            return (row[k] or '').strip()
    return ''


def domen(s):
    s = (s or '').strip().lower()
    if not s:
        return ''
    s = re.sub(r'^https?://', '', s)
    s = s.split('/')[0].split('?')[0]
    return s.replace('www.', '')


def main():
    fajl = dovod('--fajl', '')
    metka = dovod('--metka', 'чужой список')
    if not fajl or not os.path.exists(fajl):
        sys.exit('нужен --fajl <существующий файл>')

    och = {r['inn']: r for r in csv.DictReader(
        open(OCHERED, encoding='utf-8-sig'), delimiter=';')}
    rows, razd = chitat_gibko(fajl)
    print(f'вход: {len(rows)} строк, разделитель «{razd}», '
          f'колонки {list(rows[0].keys())[:8] if rows else []}', file=sys.stderr)

    est_svoi = {}
    put_svoi = os.path.join(L, 'P25-SAJTY.csv')
    if os.path.exists(put_svoi):
        for x in csv.DictReader(open(put_svoi, encoding='utf-8-sig'), delimiter=';'):
            if x['itog'] in ('подтверждён', 'название совпало'):
                est_svoi[x['inn']] = x['sayt']

    po_domenu = defaultdict(set)
    prinyato, ne_nashi, bez_domena, uzhe_est = [], 0, 0, 0
    for r in rows:
        inn = re.sub(r'\D', '', pole(r, IMENA_INN))
        d = domen(pole(r, IMENA_SAYT))
        if inn not in och:
            ne_nashi += 1
            continue
        if not d or '.' not in d:
            bez_domena += 1
            continue
        if inn in est_svoi:
            uzhe_est += 1
            continue
        po_domenu[d].add(inn)
        prinyato.append({'inn': inn, 'predpriyatie': och[inn]['predpriyatie'],
                         'sayt': 'https://' + d, 'mesto': och[inn]['mesto'], '_domen': d})

    spornye = {d for d, v in po_domenu.items() if len(v) > 1}
    godnye = [x for x in prinyato if x['_domen'] not in spornye]
    otbrosheno = len(prinyato) - len(godnye)

    put = os.path.join(L, 'P25-SAJTY-OT-SOSEDEY.csv')
    with open(put, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['inn', 'predpriyatie', 'sayt', 'mesto'])
        for x in sorted(godnye, key=lambda y: int(y['mesto'] or 10 ** 9)):
            w.writerow([x['inn'], x['predpriyatie'], x['sayt'], x['mesto']])

    print(f'  не из очереди P25:        {ne_nashi}', file=sys.stderr)
    print(f'  без домена:               {bez_domena}', file=sys.stderr)
    print(f'  сайт уже подтверждён мной:{uzhe_est}', file=sys.stderr)
    print(f'  спорных доменов:          {len(spornye)} → отброшено строк {otbrosheno}',
          file=sys.stderr)
    for d in sorted(spornye)[:5]:
        print(f'      {d}: заявлен {len(po_domenu[d])} разными ИНН', file=sys.stderr)
    print(f'ПРИНЯТО К ПРОВЕРКЕ: {len(godnye)} предприятий ({metka})', file=sys.stderr)
    print(f'→ {put}', file=sys.stderr)
    print('дальше: p25_sayt_podtverzhdenie.py по этому файлу, потом карта и разбор людей',
          file=sys.stderr)


if __name__ == '__main__':
    main()
