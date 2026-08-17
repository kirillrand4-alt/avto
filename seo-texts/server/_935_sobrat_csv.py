# -*- coding: utf-8 -*-
r"""Собрать CSV партии-935 (добор 6 286 компаний с почтой с сайта и паспортом).

Правила, согласованные с владельцем 17.08:
  - отбор: чистая почта С САЙТА (own-site/zenno/сайт:%, без ловушек/скрытых/
    «не использовать») И паспорт текущего формата с непустой продукцией;
  - один адрес на компанию: best_email, если он сайтовый чистый, иначе лучший
    сайтовый по роли (техLeague > снабжение > директор > продажи > общий);
  - contact_name ТОЛЬКО из imena.mozhno_po_imeni=1 и только когда адрес
    совпадает: здороваться по имени можно лишь с тем, чей это ящик;
  - НЕ трогаем получателей других групп: адрес, уже живущий в панели с другим
    source, в CSV не кладём (upsert перетёр бы source и утащил его в нашу
    группу — состав чужой партии менять молча нельзя). Считаем и докладываем.

Пишет C:\sender\_tmp\partiya-935-dobor.csv и печатает свод. Импорт — отдельно.
"""
import csv
import io
import json
import os
import sqlite3
import sys

sys.path.insert(0, r'C:\sender')
ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'
CSV_PATH = r'C:\sender\_tmp\partiya-935-dobor.csv'
ИСТОЧНИК = 'партия-935'

САЙТОВЫЕ = "(e.source in ('own-site','zenno') or e.source like 'сайт:%')"
ЧИСТЫЕ = ("coalesce(e.pometka,'') not like '%спам-ловушк%' "
          "and coalesce(e.pometka,'') not like '%скрыт%' "
          "and coalesce(e.pometka,'') not like '%не использовать%'")


def _ранг_роли(роль):
    р = (роль or '').lower()
    for балл, куски in ((0, ('энерг', 'механ', 'инжен', 'техдир', 'технич',
                             'производ', 'технолог', 'конструктор')),
                        (1, ('снабж', 'закуп')), (2, ('директор', 'руковод')),
                        (3, ('прода', 'коммерч'))):
        if any(к in р for к in куски):
            return балл
    return 4


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    # компании отбора
    компании = {str(r['inn']): dict(r) for r in c.execute(
        "select k.inn, coalesce(nullif(k.short_name,''), k.name,'') name, "
        "coalesce(k.okved,'') okved, coalesce(k.region,'') region, "
        "coalesce(k.division,'') division, k.pxr pxr, "
        "coalesce(nullif(k.site,''), nullif(k.cand_site,''), '') site, "
        "k.priority_total pt, k.priority_max pm, coalesce(k.best_email,'') best "
        "from companies k "
        "where exists (select 1 from emails e where e.inn=k.inn and %s and %s) "
        "and exists (select 1 from site_facts f where f.inn=k.inn "
        " and coalesce(f.format,0)>=2 and f.facts_json like '%%\"продукция\": [\"%%')"
        % (САЙТОВЫЕ, ЧИСТЫЕ))}
    # сайтовые чистые адреса
    адреса = {}
    for r in c.execute("select e.inn, e.email, coalesce(e.role,'') role from emails e "
                       'where %s and %s' % (САЙТОВЫЕ, ЧИСТЫЕ)):
        адреса.setdefault(str(r['inn']), []).append((r['email'].lower(), r['role']))
    # надёжные имена: только mozhno_po_imeni=1
    имена = {}
    for r in c.execute("select inn, email, person, coalesce(post,'') post from imena "
                       "where mozhno_po_imeni=1 and coalesce(email,'')<>''"):
        к = (str(r['inn']), r['email'].lower())
        if к not in имена or (r['post'] and not имена[к][1]):
            имена[к] = (r['person'], r['post'])
    c.close()

    s = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
    чейадрес = {r[0].lower(): (r[1] or '') for r in s.execute(
        'select email, source from recipients')}
    s.close()

    свод = {'отбор_компаний': len(компании), 'в_csv': 0, 'уже_в_935': 0,
            'занят_другой_группой': 0, 'по_чужим_группам': {},
            'с_именем': 0, 'best_email_подошёл': 0, 'адрес_по_роли': 0,
            'заполнено': {}, 'division': {}}
    строки = []
    for inn, к in sorted(компании.items()):
        канд = адреса.get(inn) or []
        if not канд:
            continue
        выбор = None
        if к['best'] and any(e == к['best'].lower() for e, _ in канд):
            выбор = к['best'].lower()
            свод['best_email_подошёл'] += 1
        else:
            канд.sort(key=lambda p: (_ранг_роли(p[1]), p[0]))
            выбор = канд[0][0]
            свод['адрес_по_роли'] += 1
        хозяин = чейадрес.get(выбор)
        if хозяин == ИСТОЧНИК:
            свод['уже_в_935'] += 1
        elif хозяин is not None:
            свод['занят_другой_группой'] += 1
            г = хозяин or '(пусто)'
            свод['по_чужим_группам'][г] = свод['по_чужим_группам'].get(г, 0) + 1
            continue
        имя = имена.get((inn, выбор))
        # segment пишем ТОЛЬКО однозначный: панель мапит его в направление
        # (division_from_segment), и 'kc+meyer' она сводит к meyer — для
        # двойных компаний это ложь, пусть решает карточка компании
        див = {'КЦ': 'kc'}.get(к['division'], к['division'])
        if див not in ('kc', 'meyer'):
            див = ''
        строка = {'email': выбор, 'inn': inn, 'company_name': к['name'][:200],
                  'okved': к['okved'], 'segment': див,
                  'contact_name': (имя[0] if имя else ''), 'source': ИСТОЧНИК,
                  'region': к['region'],
                  'pxr': ('' if к['pxr'] is None else к['pxr']),
                  'priority_total': ('' if к['pt'] is None else к['pt']),
                  'priority_max': ('' if к['pm'] is None else к['pm'])}
        строки.append(строка)
        свод['в_csv'] += 1
        if имя:
            свод['с_именем'] += 1
        свод['division'][к['division'] or '(пусто)'] = \
            свод['division'].get(к['division'] or '(пусто)', 0) + 1
        for п, з in строка.items():
            if з != '':
                свод['заполнено'][п] = свод['заполнено'].get(п, 0) + 1

    # ОДНА ПОЧТА — НЕСКОЛЬКО КОМПАНИЙ (сверка после первого импорта: 71 адрес,
    # avrora92@list.ru у двух фирм, info@tm-r.ru у ТМ-РЕСУРС и ТМ-РЕСУРС.УРАЛ).
    # UNIQUE(email) в панели терпит только одну — победителя выбираем осознанно:
    # чей домен сайта совпадает с доменом ящика, затем больший pxr, затем ИНН.
    def _дом(s):
        s = (s or '').lower()
        s = s.split('//')[-1].split('/')[0].split('@')[-1]
        return s[4:] if s.startswith('www.') else s

    по_почте = {}
    for стр in строки:
        по_почте.setdefault(стр['email'], []).append(стр)
    выжившие, свод['общий_ящик_выбыло'] = [], 0
    свод['общий_ящик_примеры'] = []
    for почта, группа in по_почте.items():
        if len(группа) > 1:
            дом_я = _дом(почта)
            группа.sort(key=lambda s: (
                0 if _дом(компании[s['inn']]['site']) == дом_я else 1,
                -(компании[s['inn']]['pxr'] or 0), s['inn']))
            свод['общий_ящик_выбыло'] += len(группа) - 1
            if len(свод['общий_ящик_примеры']) < 5:
                свод['общий_ящик_примеры'].append(
                    {'ящик': почта,
                     'взяли': группа[0]['company_name'][:40],
                     'выбыли': [g['company_name'][:40] for g in группа[1:]]})
        выжившие.append(группа[0])
    строки = sorted(выжившие, key=lambda s: s['inn'])
    свод['в_csv'] = len(строки)

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with io.open(CSV_PATH, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(строки[0].keys()), delimiter=';')
        w.writeheader()
        w.writerows(строки)
    свод['файл'] = CSV_PATH
    свод['пример'] = строки[:2]
    # заодно проверяем, поймёт ли панель наш segment как направление
    try:
        from sender.company_card import division_from_segment
        свод['segment_распознан'] = {v: division_from_segment(v)
                                     for v in ('kc', 'meyer', 'kc+meyer',
                                               'металлообработка')}
    except Exception as e:  # noqa: BLE001
        свод['segment_распознан'] = 'не проверить: %s' % e
    print(json.dumps(свод, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
