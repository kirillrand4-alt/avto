# -*- coding: utf-8 -*-
"""Пункт 37: почему панель показывает «среда не названа» у 33 589 фактов.

ЗАМЕР, а не догадка. Выгрузила из панели все факты без среды и прогнала двумя правилами:
текст самого факта и надёжный словарь марок. Итог:

    15 875  ни марки, ни слова о среде в тексте    — честная пустота, вопросов нет
    12 428  марка есть, но ненадёжная              — оставляем «не названа», см. ниже
     4 769  среда НАПИСАНА В ТЕКСТЕ САМОГО ФАКТА   — панель её просто не читает
       517  закрывается надёжной маркой

Главное здесь — не словарь. 4 769 фактов из 33 589 несут среду прямо в своём тексте
(«воздуходувка», «сжатый воздух», «природный газ»), и панель всё равно пишет «не названа».
Это не пробел в данных, а непрочитанное поле: чинить надо разбор, а не собирать источники.
Словарь марок добавляет к этому ещё 517 — вдесятеро меньше.

ПОЧЕМУ СЛОВАРЬ ТОЛЬКО НАДЁЖНЫЙ. Марка не всегда та, что записана в поле модели: из 307 марок
с вердиктом поле `model` панели подтверждает 102, а известные семейства компрессоров — 39.
Девять вердиктов пришли вообще не от компрессоров (Л-35/11-300 — риформинг, УКПГ-4 —
установка подготовки газа), а ПК-1, ПК-2 и ПК-3 с 257 упоминаниями оказались позиционными
обозначениями и раздавали «газ» по всей базе. Поэтому марка закрывает среду только если она
опознана известным семейством; остальные 12 428 остаются «не названа» — притворяться, что
мы знаем, хуже, чем признать, что нет.

ПОРЯДОК ВАЖЕН: текст факта сильнее марки. Марка говорит, чем машина бывает обычно, текст —
чем она занята в этом конкретном заключении. Если оба есть, берётся текст.

Использование:
    python3 panel_sreda.py fakty-bez-sredy.json.gz SLOVAR-MAROK-NADEZHNYE.json out.csv

Вход — выгрузка панели: список строк [id, marka, tip_mashiny, tekst, sreda, istochnik].
Выход — CSV с колонками id, marka, tip, sreda, otkuda, istochnik, tekst; `otkuda` называет
основание («текст факта» или «марка (воздух 24 из 30)»), чтобы принимающая сторона могла
проверить, а не поверить.
"""
import collections
import csv
import gzip
import json
import re
import sys

GAZ = re.compile(r'синтез-газ|синтез газ|природн\w*\s*газ|попутн\w*\s*газ|нефтян\w*\s*газ|'
                 r'\bГПА\b|газоперекачив|азот\w*|кислород\w*|аммиак|водород|этилен|пропилен|'
                 r'углекислот|сероводород|\bхлор\b|\bметан\b|циркуляционн\w*\s*газ|'
                 r'коксов\w*\s*газ|доменн\w*\s*газ|технологическ\w*\s*газ|газов\w*\s', re.I)
VOZDUH = re.compile(r'воздух|воздушн|воздуходувк|турбовоздуходувк|пневмо|дутьев', re.I)


def normalizovat_marku(m):
    """«К 250-61-5» и «К-250-61-5» — одна марка. Пробел и длинное тире приводятся к дефису."""
    return re.sub(r'[\s–]', '-', (m or '')).upper()


def sreda_iz_teksta(tekst):
    g, v = bool(GAZ.search(tekst or '')), bool(VOZDUH.search(tekst or ''))
    return 'и газ, и воздух' if g and v else 'газ' if g else 'воздух' if v else ''


def razobrat(fakty, slovar):
    slov = {normalizovat_marku(k): v for k, v in slovar.items()}
    schet = collections.Counter()
    out = []
    for fid, marka, tip, tekst, _sreda, istochnik in fakty:
        m = normalizovat_marku(marka)
        po_tekstu = sreda_iz_teksta(tekst)
        z = slov.get(m)
        if po_tekstu:
            schet['закрывается текстом самого факта'] += 1
            out.append({'id': fid, 'marka': marka, 'tip': tip, 'sreda': po_tekstu,
                        'otkuda': 'текст факта', 'istochnik': istochnik,
                        'tekst': (tekst or '')[:200]})
        elif z:
            schet['закрывается надёжной маркой'] += 1
            out.append({'id': fid, 'marka': marka, 'tip': tip, 'sreda': z['sreda'],
                        'otkuda': f'марка ({z["pochemu"]})', 'istochnik': istochnik,
                        'tekst': (tekst or '')[:200]})
        elif m:
            schet['марка есть, но ненадёжная — остаётся «не названа»'] += 1
        else:
            schet['ни марки, ни слова о среде'] += 1
    return out, schet


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    put_fakty, put_slovar, out_path = sys.argv[1:4]
    otkr = gzip.open if put_fakty.endswith('.gz') else open
    fakty = json.load(otkr(put_fakty, 'rt', encoding='utf-8'))
    slovar = json.load(open(put_slovar, encoding='utf-8'))
    out, schet = razobrat(fakty, slovar)
    for k, n in schet.most_common():
        print(f'{n:>6}  {k}', file=sys.stderr)
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, delimiter=';',
                           fieldnames=['id', 'marka', 'tip', 'sreda', 'otkuda', 'istochnik',
                                       'tekst'])
        w.writeheader()
        w.writerows(out)
    centro = [x for x in out if x['tip'] == 'центробежная']
    print(f'к простановке {len(out)} | центробежных {len(centro)}, из них воздушных '
          f'{sum(1 for x in centro if "воздух" in x["sreda"])} → {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
