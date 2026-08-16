# -*- coding: utf-8 -*-
r"""Один домен на много компаний — это справочник, а не сайт предприятия.

Самая честная проверка на площадку из всех, что у нас есть: она не спрашивает
модель и не заглядывает в текст. У завода свой домен. Если один и тот же адрес
стоит привязкой у десятков РАЗНЫХ юрлиц — это каталог, портал или витрина, как бы
он ни назывался и что бы ни было написано на его страницах.

Так нашлись порталы, которых не было ни в каком списке: o-zavodah.ru,
agroserver.ru, «декларации-соответствия.рус», dataslon.ru — судья 16.08 ловил их
поодиночке и по одному, здесь они видны разом и целиком.

Порог. Два юрлица на домене — обычное дело: группа компаний, торговый дом и завод,
переезд юрлица. Три и больше — уже разговор, и мы смотрим их глазами, а снимаем
привязки от пяти.

    python obshchie_domeny.py [порог]     показать домены и сколько на них компаний
    python obshchie_domeny.py --snyat [порог]   снять привязки (по умолчанию от 5)
"""
import json
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL          # noqa: E402
import sverka_privyazki as SP     # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ЛОГ = os.path.join(DIR, 'obshchie_domeny.jsonl')


def собрать():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    по_домену = defaultdict(list)
    for r in c.execute("select inn, coalesce(name,'') name, coalesce(site,'') site, "
                       "coalesce(cand_site,'') cand from companies "
                       "where coalesce(site,'')<>'' or coalesce(cand_site,'')<>''"):
        for поле in ('site', 'cand'):
            u = r[поле]
            if not u:
                continue
            d = PL.домен(u)
            if d:
                по_домену[d].append({'inn': str(r['inn']), 'name': r['name'][:40],
                                     'поле': 'site' if поле == 'site' else 'cand_site'})
    c.close()
    return по_домену


def отчёт(порог=3):
    по_домену = собрать()
    из = []
    for d, сп in по_домену.items():
        инн = {x['inn'] for x in сп}
        if len(инн) >= порог:
            из.append({'домен': d, 'компаний': len(инн),
                       'в_списке_площадок': bool(PL.из_списка(d)),
                       'примеры': [x['name'] for x in сп[:4]]})
    из.sort(key=lambda x: -x['компаний'])
    return из


_ФОРМА = re.compile(r'\b(ооо|оао|зао|пао|ао|ип|нао|филиал|общество|с|ограниченной|'
                    r'ответственностью|акционерное|публичное|непубличное|компания|'
                    r'группа|завод|фирма|мхк|нак|тд|гк|управляющая|специализированный|'
                    r'застройщик|производственная|торговый|дом)\b')


# Заимствованные корни пишутся на сайтах не транслитом, а по-английски: ЕвроХим
# живёт на eurochem.ru, а не на evrohim.ru. Без этой таблицы собственный домен
# холдинга не опознаётся, и его завод теряет привязку ни за что.
_КОРНИ = (('евро', 'euro'), ('хим', 'chem'), ('тех', 'tech'), ('фарм', 'pharm'),
          ('центр', 'center'), ('сервис', 'service'), ('проект', 'project'),
          ('групп', 'group'), ('ойл', 'oil'), ('газ', 'gas'), ('нефт', 'neft'),
          ('энерго', 'energy'), ('металл', 'metal'), ('агро', 'agro'),
          ('транс', 'trans'), ('строй', 'stroy'), ('пром', 'prom'))


def _по_корням(w):
    """Написания слова, где ВСЕ заимствованные корни заменены английскими.

    Заменять по одному корню мало: «ЕвроХим» — это euro И chem сразу, а с одной
    заменой получается eurohim, которого нет ни на одном домене.
    """
    s = w
    for рус, лат in _КОРНИ:
        s = s.replace(рус, '\x01' + лат + '\x01')
    if '\x01' not in s:
        return set()
    части = s.split('\x01')
    # чётные куски — то, что осталось по-русски, их транслитерируем; нечётные уже
    # английские
    собрано = ''.join(ч if i % 2 else SP._translit(ч) for i, ч in enumerate(части))
    return {собрано} if собрано else set()


def _свой_домен(имя, домен):
    """Домен собран из названия компании? «ООО ВСК» и vsk.ru — да.

    Смотрим ВСЕ слова названия, а не одно самое длинное: у «Филиал АО МХК ЕвроХим
    Белореченские минудобрения» самое длинное слово — «белореченские», и по нему
    eurochem.ru своим не признается, хотя это ровно их домен. Короткие слова
    («ВСК») сверяем строго — целиком или началом домена, иначе три буквы совпадут
    с чем угодно.
    """
    s = _ФОРМА.sub(' ', (имя or '').lower().replace('ё', 'е'))
    слова = [w for w in re.split(r'[^a-zа-я0-9]+', s) if len(w) >= 3]
    основа = re.sub(r'[^a-z0-9]', '', домен.split('.')[0])
    if not основа or not слова:
        return False
    for w in слова:
        варианты = SP._варианты(w) | {SP._translit(w)} | _по_корням(w)
        for в in варианты:
            if not в:
                continue
            if len(в) >= 5 and (в in основа or основа in в):
                return True
            if 3 <= len(в) < 5 and (основа == в or основа.startswith(в)):
                return True
    return False


def снять(порог=3):
    """Снять привязки к общим доменам — но не у тех, чьё имя в этом домене.

    Порог трогали дважды. Сперва хотели снимать всё от пяти компаний на домене, но
    на границе 5-9 сразу нашлись настоящие холдинги: vsk.ru держит «ООО ВСК» и
    «ООО ВСК № 1», eurochem.ru — филиалы ЕвроХима. Поэтому решение принимается по
    КОМПАНИИ: если домен собран из её названия, привязка остаётся, даже когда на
    домене висят ещё десять юрлиц. «АО НАК Азот» на eurochem.ru при этом привязку
    теряет — и правильно: паспорт по сайту холдинга описывает холдинг, а не завод.
    """
    по_домену = собрать()
    цели = {d: сп for d, сп in по_домену.items()
            if len({x['inn'] for x in сп}) >= порог}
    c = sqlite3.connect(BD, timeout=60)
    итог = {'доменов': len(цели), 'снято_site': 0, 'снято_cand_site': 0,
            'паспортов_в_карантин': 0, 'оставлено_по_имени': 0}
    записи = []
    for d, сп in цели.items():
        for x in сп:
            if _свой_домен(x['name'], d):
                итог['оставлено_по_имени'] += 1
                continue
            поле = x['поле']
            n = c.execute(
                "UPDATE companies SET %s='', updated_at=? WHERE inn=? AND %s LIKE ?"
                % (поле, поле),
                (time.strftime('%Y-%m-%dT%H:%M:%S'), x['inn'], '%' + d + '%')).rowcount
            итог['снято_' + поле] += n
            итог['паспортов_в_карантин'] += c.execute(
                "UPDATE site_facts SET otkloneno_json=facts_json, facts_json='', "
                "privyazka=?, note=? WHERE inn=? AND coalesce(facts_json,'')<>''",
                ('общий домен: ' + d,
                 'паспорт собран по домену, который привязан к %d компаниям — это '
                 'справочник, а не сайт предприятия' % len({y['inn'] for y in сп}),
                 x['inn'])).rowcount
            записи.append({'inn': x['inn'], 'домен': d, 'поле': поле,
                           'компаний_на_домене': len({y['inn'] for y in сп})})
    c.commit()
    c.close()
    with open(ЛОГ, 'a', encoding='utf-8') as f:
        for з in записи:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return итог


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if a and a[0] == '--snyat':
        print(json.dumps(снять(int(a[1]) if len(a) > 1 else 3), ensure_ascii=False, indent=1))
    else:
        п = int(a[0]) if a and a[0].isdigit() else 3
        сп = отчёт(п)
        # ИТОГ ПЕЧАТАЕМ ПОСЛЕДНИМ: раннер отдаёт хвост stdout, и сводка, стоящая
        # первой, до нас не доезжает
        граница = [x for x in сп if 5 <= x['компаний'] <= 9][:20]
        print(json.dumps({'верх': сп[:8], 'граница_5_9': граница},
                         ensure_ascii=False, indent=1))
        print(json.dumps({'доменов_с_порогом_%d' % п: len(сп),
                          'компаний_на_них': sum(x['компаний'] for x in сп),
                          'из_них_уже_в_списке': sum(1 for x in сп if x['в_списке_площадок']),
                          'от_5_компаний': sum(1 for x in сп if x['компаний'] >= 5),
                          'компаний_на_них_от_5': sum(x['компаний'] for x in сп
                                                      if x['компаний'] >= 5)},
                         ensure_ascii=False, indent=1))
