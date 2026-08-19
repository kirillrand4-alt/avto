# -*- coding: utf-8 -*-
r"""Пометить почты, непригодные для отправки: сервисы отчётности и общие порталы.

Владелец 19.08: «adygheya.gov.ru (портал администрации), eo.tensor.ru (сервис
отчётности) — подобные бы пометить в базе как негодные для отправки сами почты».

Два класса, и правила у них разные:

  СЕРВИС ОТЧЁТНОСТИ (tensor/sbis/kontur/diadoc/taxcom/astral). Такой адрес —
  ящик электронного документооборота, заведённый бухгалтерией для сдачи
  отчётности. Живого человека там нет никогда, письмо уйдёт в никуда. Метим
  ВСЕГДА, вне зависимости от компании.

  ОБЩИЙ ПОРТАЛ (домен, на котором сидят ТРИ и больше разных юрлица). Портал
  администрации или бизнес-центра: письмо попадёт не тому. Метим по факту
  множественности, а не по списку — так ловятся и те, кого мы не знаем.
  Государственному учреждению его собственный gov-домен при этом оставляем:
  если на домене одно юрлицо, это его законный адрес.

Метка ставится в emails.pometka строкой «не использовать: ...» — тем же словом,
которое уже отсеивают выборки для рассылки (см. KAK-BRAT-POCHTY-S-SAYTOV.md).

    python pometka_negodnyh.py            посчитать
    python pometka_negodnyh.py --primenit пометить
"""
import json
import os
import re
import sqlite3
import sys
import time

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
СЕРВИСЫ = re.compile(
    r'(^|\.)(tensor|sbis|kontur|kontur-extern|diadoc|taxcom|astral|astral-nalog|'
    r'edo|nalog|gosuslugi)\.', re.I)
ПОРОГ_ПОРТАЛА = 3


def разбор(применять=False):
    c = sqlite3.connect(BD, timeout=90)
    c.row_factory = sqlite3.Row
    строки = list(c.execute(
        "select inn, email, coalesce(pometka,'') pometka from emails "
        "where coalesce(email,'')<>''"))
    по_домену = {}
    for r in строки:
        д = (r['email'].split('@')[-1] or '').lower().strip('.')
        if д:
            по_домену.setdefault(д, set()).add(str(r['inn']))
    цели, свод = [], {'адресов_всего': len(строки), 'сервис_отчётности': 0,
                      'общий_портал': 0, 'уже_помечены': 0}
    примеры = {}
    for r in строки:
        если_помечен = 'не использовать' in r['pometka']
        д = (r['email'].split('@')[-1] or '').lower().strip('.')
        причина = ''
        if СЕРВИСЫ.search(д):
            причина = 'сервис отчётности/ЭДО — живого адресата нет'
        elif len(по_домену.get(д) or ()) >= ПОРОГ_ПОРТАЛА:
            причина = ('общий домен на %d юрлиц — письмо уйдёт не тому'
                       % len(по_домену[д]))
        if not причина:
            continue
        if если_помечен:
            свод['уже_помечены'] += 1
            continue
        ключ = ('сервис_отчётности' if 'сервис' in причина else 'общий_портал')
        свод[ключ] += 1
        цели.append((str(r['inn']), r['email'], r['pometka'], причина))
        примеры.setdefault(ключ, [])
        if len(примеры[ключ]) < 5:
            примеры[ключ].append({'адрес': r['email'], 'почему': причина})
    if применять and цели:
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        for инн, адрес, было, причина in цели:
            метка = (было + ' | ' if было else '') + 'не использовать: ' + причина
            c.execute('update emails set pometka=?, updated_at=? '
                      'where inn=? and email=?', (метка[:300], ts, инн, адрес))
        c.commit()
        свод['помечено'] = len(цели)
    c.close()
    свод['примеры'] = примеры
    return свод


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    и = разбор('--primenit' in sys.argv)
    прим = и.pop('примеры', {})
    print(json.dumps({'примеры': прим}, ensure_ascii=False, indent=1))
    print(json.dumps(и, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
