# -*- coding: utf-8 -*-
r"""Догруз партии 935: те же условия, что при заливке 17.08, минус риски.

Два пути, и разница принципиальная:
  ТЕГ     компания уже есть в панели (под другой группой или без неё) — ей
          просто дописываем «Партия 935» в extra_json.gruppy. Новую строку не
          заводим НИКОГДА: два получателя на одну компанию = два письма в одну
          дверь, а source чужой партии менять нельзя.
  CSV     компании в панели нет вовсе — штатный импорт.

Исключаем: стоп-лист по ИНН и по домену, помеченных конкурентами, приговор
«чужой», и адреса, закреплённые в панели за ДРУГИМ ИНН (общий ящик соседа).

    python dogruz_935.py            посчитать и собрать CSV
    python dogruz_935.py --primenit проставить теги (CSV импортируется отдельно)
"""
import csv
import io
import json
import os
import sqlite3
import sys
import time

ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
SENDER = r'C:\sender\sender.db'
CSV_PATH = r'C:\sender\_tmp\partiya-935-dogruz.csv'
ГРУППА = 'Партия 935'
ИСТОЧНИК = 'партия-935'
САЙТ = "(e.source in ('own-site','zenno') or e.source like 'сайт:%')"
ЧИСТ = ("coalesce(e.pometka,'') not like '%спам-ловушк%' "
        "and coalesce(e.pometka,'') not like '%скрыт%' "
        "and coalesce(e.pometka,'') not like '%не использовать%'")


def _ранг(роль):
    р = (роль or '').lower()
    for балл, куски in ((0, ('энерг', 'механ', 'инжен', 'техдир', 'технич',
                             'производ', 'технолог', 'конструктор')),
                        (1, ('снабж', 'закуп')), (2, ('директор', 'руковод')),
                        (3, ('прода', 'коммерч'))):
        if any(к in р for к in куски):
            return балл
    return 4


def собрать():
    c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    компании = {str(r['inn']): dict(r) for r in c.execute(
        "select k.inn, coalesce(nullif(k.short_name,''),k.name,'') name, "
        "coalesce(k.okved,'') okved, coalesce(k.region,'') region, "
        "coalesce(k.division,'') division, k.pxr pxr, k.priority_total pt, "
        "k.priority_max pm, coalesce(k.best_email,'') best, "
        "coalesce(k.is_competitor,0) konk from companies k "
        'where exists(select 1 from emails e where e.inn=k.inn and %s and %s) '
        'and exists(select 1 from site_facts f where f.inn=k.inn '
        'and coalesce(f.format,0)>=2 and f.facts_json like \'%%"продукция": ["%%\')'
        % (САЙТ, ЧИСТ))}
    адреса = {}
    for r in c.execute('select e.inn, lower(e.email) em, coalesce(e.role,\'\') role '
                       'from emails e where %s and %s' % (САЙТ, ЧИСТ)):
        адреса.setdefault(str(r['inn']), []).append((r['em'], r['role']))
    имена = {}
    for r in c.execute("select inn, lower(email) em, person, coalesce(post,'') post "
                       "from imena where mozhno_po_imeni=1 and coalesce(email,'')<>''"):
        к = (str(r['inn']), r['em'])
        if к not in имена or (r['post'] and not имена[к][1]):
            имена[к] = (r['person'], r['post'])
    чужие = set()
    try:
        чужие = {str(r[0]) for r in c.execute(
            "select inn from prigovor_domenov where verdikt='чужой'")}
    except Exception:  # noqa: BLE001
        pass
    c.close()

    s = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
    s.row_factory = sqlite3.Row
    в_группе, по_инн, чей_адрес = set(), {}, {}
    for r in s.execute("select id, coalesce(inn,'') inn, lower(coalesce(email,'')) em, "
                       "coalesce(extra_json,'') ex from recipients"):
        инн = ''.join(ch for ch in r['inn'] if ch.isdigit())
        if r['em']:
            чей_адрес[r['em']] = инн
        if инн:
            по_инн.setdefault(инн, []).append(r['id'])
        if ГРУППА in r['ex']:
            в_группе.add(инн)
    стоп_инн = {''.join(ch for ch in str(r[0]) if ch.isdigit())
                for r in s.execute("select value from suppression where scope='inn'")}
    стоп_дом = {str(r[0]).lower() for r in s.execute(
        "select value from suppression where scope='domain'")}
    s.close()

    свод = {'проходят_условия': len(компании), 'уже_в_группе': 0, 'к_догрузу': 0,
            'отсев': {}, 'тегом': 0, 'в_csv': 0, 'с_именем': 0}
    теги, строки = [], []
    for инн, к in sorted(компании.items()):
        if инн in в_группе:
            свод['уже_в_группе'] += 1
            continue

        def отсеять(п):
            свод['отсев'][п] = свод['отсев'].get(п, 0) + 1

        if инн in чужие:
            отсеять('приговор «чужой сайт»')
            continue
        if инн in стоп_инн:
            отсеять('стоп-лист по ИНН')
            continue
        if str(к['konk']).strip().lower() in ('1', 'true', 'да'):
            отсеять('помечена конкурентом')
            continue
        канд = адреса.get(инн) or []
        if not канд:
            отсеять('нет чистого адреса с сайта')
            continue
        b = (к['best'] or '').lower()
        выбор = b if any(e == b for e, _ in канд) else sorted(
            канд, key=lambda p: (_ранг(p[1]), p[0]))[0][0]
        if выбор.split('@')[-1] in стоп_дом:
            отсеять('домен в стоп-листе')
            continue
        хозяин = чей_адрес.get(выбор)
        if хозяин and хозяин != инн:
            отсеять('адрес закреплён за другим ИНН')
            continue
        свод['к_догрузу'] += 1
        if по_инн.get(инн):
            теги.extend(по_инн[инн])          # компания уже в панели — только тег
            свод['тегом'] += 1
            continue
        имя = имена.get((инн, выбор))
        див = {'КЦ': 'kc'}.get(к['division'], к['division'])
        строки.append({'email': выбор, 'inn': инн, 'company_name': к['name'][:200],
                       'okved': к['okved'], 'segment': див if див in ('kc', 'meyer') else '',
                       'contact_name': (имя[0] if имя else ''), 'source': ИСТОЧНИК,
                       'region': к['region'],
                       'pxr': '' if к['pxr'] is None else к['pxr'],
                       'priority_total': '' if к['pt'] is None else к['pt'],
                       'priority_max': '' if к['pm'] is None else к['pm']})
        свод['в_csv'] += 1
        if имя:
            свод['с_именем'] += 1
    return свод, теги, строки


def применить():
    свод, теги, строки = собрать()
    if строки:
        os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
        with io.open(CSV_PATH, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(строки[0].keys()), delimiter=';')
            w.writeheader()
            w.writerows(строки)
        свод['csv'] = CSV_PATH
    s = sqlite3.connect(SENDER, timeout=90)
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    проставлено = 0
    with s:
        for rid in теги:
            r = s.execute('select coalesce(extra_json,\'\') from recipients where id=?',
                          (rid,)).fetchone()
            try:
                d = json.loads(r[0]) if (r[0] or '').strip() else {}
                if not isinstance(d, dict):
                    d = {}
            except Exception:  # noqa: BLE001
                d = {}
            гр = [g for g in (d.get('gruppy') or []) if str(g).strip()]
            if ГРУППА in гр:
                continue
            d['gruppy'] = гр + [ГРУППА]
            s.execute('update recipients set extra_json=?, updated_at=? where id=?',
                      (json.dumps(d, ensure_ascii=False), ts, rid))
            проставлено += 1
    s.close()
    свод['тегов_проставлено'] = проставлено
    return свод


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if '--primenit' in sys.argv:
        print(json.dumps(применить(), ensure_ascii=False, indent=1))
    else:
        свод, теги, строки = собрать()
        свод['пример_csv'] = строки[:2]
        print(json.dumps(свод, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
