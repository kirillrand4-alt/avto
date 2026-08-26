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
import re
import sqlite3
import sys
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (_DIR, os.path.dirname(_DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import enrich_db as _EDB  # noqa: E402

ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
SENDER = r'C:\sender\sender.db'
CSV_PATH = r'C:\sender\_tmp\partiya-935-dogruz.csv'
ГРУППА = 'Партия 935'
# Вторая метка, а не вторая партия: компания едет в той же группе, но письмо
# по ней нельзя строить на «что вы выпускаете» — продукции в паспорте нет.
# Метка нужна той сессии, что генерирует письма: второй абзац придётся брать
# из энергохозяйства, оборудования или новости.
ГРУППА_БЕЗ_ПРОДУКЦИИ = 'Без продукции'
ИСТОЧНИК = 'партия-935'
САЙТ = "(e.source in ('own-site','zenno') or e.source like 'сайт:%')"
ЧИСТ = ("coalesce(e.pometka,'') not like '%спам-ловушк%' "
        "and coalesce(e.pometka,'') not like '%скрыт%' "
        "and coalesce(e.pometka,'') not like '%не использовать%'")


def _nashi_domeny():
    """Домены НАШИХ ящиков рассылки: писать самим себе нельзя.

    Замер 21.08 нашёл пять таких получателей в панели, и одному из них письмо
    уже уходило — вернулось к нам ответом и завелось лидом «ПАО Химпром».
    Берём их из живых отправок, а не списком в коде.
    """
    try:
        sys.path.insert(0, r'C:\sender\sender')
        import lid_ssylka as _LS
        return set(_LS.nashi_domeny() or ())
    except Exception:  # noqa: BLE001
        return set()


НАШИ_ДОМЕНЫ = _nashi_domeny()


def _ранг(роль):
    р = (роль or '').lower()
    for балл, куски in ((0, ('энерг', 'механ', 'инжен', 'техдир', 'технич',
                             'производ', 'технолог', 'конструктор')),
                        (1, ('снабж', 'закуп')), (2, ('директор', 'руковод')),
                        (3, ('прода', 'коммерч'))):
        if any(к in р for к in куски):
            return балл
    return 4


# Материал, на котором письмо СТРОИТСЯ: цех, оборудование, компрессорная,
# газы, мощности. «Новости», «масштаб» и «география» сюда НЕ входят — по ним
# второй абзац не написать, а пропускают они внутрь кого угодно: замер 20.08
# показал, что на одних мягких полях в догруз просились «Газпром
# газораспределение Тамбов» и «Екатеринбурггаз» (104 такие компании).
ПОЛЯ_МАТЕРИАЛА = ('оборудование_линии', 'энергохозяйство', 'газы', 'мощности',
                  'сырьё', 'упаковка_фасовка', 'контроль_качества', 'расширение')
# Школа, детсад и администрация района сжатый воздух не покупают ни при каком
# паспорте. Больницы оставляем осознанно: кислородная станция и медицинский
# воздух — настоящая цель компрессорного направления.
_ВЛАСТЬ = re.compile(r'АДМИНИСТРАЦИЯ|СОВЕТ ДЕПУТАТОВ|СЕЛЬСОВЕТ|ГОРОДСКОЙ ОКРУГ|'
                     r'МУНИЦИПАЛЬНОГО РАЙОНА|УПРАВЛЕНИЕ ДЕЛАМИ|КОМИТЕТ ПО ', re.I)
_ШКОЛА = re.compile(r'\bШКОЛА|ЛИЦЕЙ|ГИМНАЗИЯ|ДЕТСКИЙ САД|УНИВЕРСИТЕТ|КОЛЛЕДЖ|'
                    r'ТЕХНИКУМ', re.I)


def bez_produkcii():
    """ИНН с полным паспортом, где «продукция» пуста, но материал для письма есть.

    Признак полноты у нас — непустая «продукция», и 20.08 замер показал цену
    этого признака: из 12 414 паспортов у 2 843 продукция пуста, но у 404 из
    них заполнено другое. Это торговля и услуги: выпускать нечего, а
    компрессорная и станочный парк есть. Владелец 20.08: «400 тоже залей».
    Берём 300 с твёрдым материалом минус 11 школ и администраций; 2 439
    паспортов, пустых целиком, не берём — там писать не о чем.
    """
    c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    имена = {str(r[0]): (r[1] or '', r[2] or '') for r in c.execute(
        "select inn, coalesce(nullif(short_name,''),name,''), coalesce(okved,'') "
        'from companies')}
    инн = set()
    for i, f in c.execute("select inn, facts_json from site_facts "
                          "where coalesce(facts_json,'')<>'' and coalesce(format,0)>=2"):
        try:
            д = json.loads(f)
        except Exception:  # noqa: BLE001
            continue
        if д.get('продукция'):
            continue
        if not any(д.get(п) for п in ПОЛЯ_МАТЕРИАЛА):
            continue
        нм, ок = имена.get(str(i), ('', ''))
        if ок.startswith(('84', '85')) or _ВЛАСТЬ.search(нм) or _ШКОЛА.search(нм):
            continue
        инн.add(str(i))
    c.close()
    return инн


def _pochty_obzvona(nuzhny):
    """Адреса из базы обзвона: emails_base и emails_site, через « | ».

    Владелец 24.08: «загрузи все паспорта полные со всеми почтами которые
    есть». Правило «только адрес, снятый с сайта компании» отсекало не мусор,
    а целые компании: у 7061 из 15 887 полных паспортов адреса в обогащении нет
    вовсе, зато у 4456 из них он лежит в базе обзвона — то есть письмо писать
    есть о чём и есть куда, просто мы туда не смотрели.
    """
    путь = os.environ.get('OBZVON_DB', r'C:\sender\obzvon-index.db')
    если = {}
    if not os.path.exists(путь):
        return если
    try:
        o = sqlite3.connect('file:%s?mode=ro' % путь.replace('\\', '/'), uri=True,
                            timeout=60)
        for инн, б, с in o.execute(
                "select inn, coalesce(emails_base,''), coalesce(emails_site,'') "
                'from obzvon'):
            и = str(инн)
            if и not in nuzhny:
                continue
            сп = []
            for кусок in (str(б), str(с)):
                for а in re.split(r'[|,;\s]+', кусок.strip(' []')):
                    а = а.strip().strip('"\'').lower()
                    if '@' in а and '.' in а.split('@')[-1]:
                        сп.append((а, ''))
            if сп:
                если[и] = сп
        o.close()
    except Exception:  # noqa: BLE001 - базы может не быть, это не повод падать
        return если
    return если


def собрать(inny=None, gruppa=None, vse_pochty=False):
    """inny — готовый список ИНН вместо условия «продукция непустая».

    vse_pochty — брать адрес из ЛЮБОГО источника, а не только снятый с сайта
    компании, и добирать недостающие из базы обзвона. Остальные заслоны на
    месте: стоп-листы, конкуренты, приговор «чужой сайт», адрес, закреплённый
    за другим ИНН, и наши собственные ящики рассылки.
    """
    c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    паспорт = ('and exists(select 1 from site_facts f where f.inn=k.inn '
               'and coalesce(f.format,0)>=2 '
               'and f.facts_json like \'%"продукция": ["%\')'
               if inny is None else '')
    # Условие по адресу собираем СТРОКОЙ, без вложенного %-форматирования:
    # в САЙТ и ЧИСТ сами живут проценты («%спам-ловушк%»), и второй проход
    # форматирования их ломает.
    есть_адрес = ('1=1' if vse_pochty else
                  'exists(select 1 from emails e where e.inn=k.inn and '
                  + САЙТ + ' and ' + ЧИСТ + ')')
    компании = {str(r['inn']): dict(r) for r in c.execute(
        "select k.inn, coalesce(nullif(k.short_name,''),k.name,'') name, "
        "coalesce(k.okved,'') okved, coalesce(k.region,'') region, "
        "coalesce(k.division,'') division, k.pxr pxr, k.priority_total pt, "
        "k.priority_max pm, coalesce(k.best_email,'') best, "
        "coalesce(k.is_competitor,0) konk from companies k where "
        + есть_адрес + ' ' + паспорт)
        if inny is None or str(r['inn']) in inny}
    адреса = {}
    отбор = ('where ' + ЧИСТ) if vse_pochty else (
        'where ' + САЙТ + ' and ' + ЧИСТ)
    for r in c.execute("select e.inn, lower(e.email) em, coalesce(e.role,'') role "
                       'from emails e ' + отбор):
        адреса.setdefault(str(r['inn']), []).append((r['em'], r['role']))
    if vse_pochty:
        # добираем тех, у кого в обогащении адреса нет вовсе
        нет_адреса = {и for и in компании if not адреса.get(и)}
        for и, сп in _pochty_obzvona(нет_адреса).items():
            адреса[и] = сп
    имена = {}
    for r in c.execute("select inn, lower(email) em, person, coalesce(post,'') post "
                       "from imena where mozhno_po_imeni=1 and coalesce(email,'')<>''"):
        к = (str(r['inn']), r['em'])
        if к not in имена or (r['post'] and not имена[к][1]):
            имена[к] = (r['person'], r['post'])
    # Конкурент, видимый в собственном паспорте. Флаг is_competitor его не ловит:
    # ОКВЭД может быть любой, а провайдер-судья по сайту проходит не по всем. 26.08
    # так ушло письмо производителю поршневых компрессоров (ИНН 6679054575) — в его
    # паспорте они перечислены в «продукции», а загрузка смотрела только на флаг.
    # Читаем потоком и держим в памяти только попадания: facts_json тяжёлые.
    конк_паспорт = {}
    for r in c.execute("select inn, coalesce(facts_json,'') fj from site_facts "
                       "where coalesce(facts_json,'')<>''"):
        инн = str(r['inn'])
        if инн not in компании:
            continue
        да, признаки = _EDB.konkurent_po_pasportu(r['fj'])
        if да:
            конк_паспорт[инн] = признаки
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
        if (gruppa or ГРУППА) in r['ex']:
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
        if инн in конк_паспорт:
            отсеять('конкурент по паспорту (%s)' % ', '.join(конк_паспорт[инн]))
            continue
        канд = [(а, р) for а, р in (адреса.get(инн) or [])
                if а.split('@')[-1] not in НАШИ_ДОМЕНЫ]
        if not канд:
            отсеять('нет адреса' if vse_pochty else 'нет чистого адреса с сайта')
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


def применить(inny=None, gruppy=None, gruppa=None, vse_pochty=False):
    """gruppy — какие группы дописать; gruppa — по какой считать «уже заведён»."""
    gruppy = list(gruppy or [ГРУППА])
    свод, теги, строки = собрать(inny, gruppa or ГРУППА, vse_pochty)
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
            нехватает = [g for g in gruppy if g not in гр]
            if not нехватает:
                continue
            d['gruppy'] = гр + нехватает
            s.execute('update recipients set extra_json=?, updated_at=? where id=?',
                      (json.dumps(d, ensure_ascii=False), ts, rid))
            проставлено += 1
    s.close()
    свод['тегов_проставлено'] = проставлено
    return свод


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    без = '--bez-produkcii' in sys.argv
    inny = bez_produkcii() if без else None
    гр = [ГРУППА, ГРУППА_БЕЗ_ПРОДУКЦИИ] if без else [ГРУППА]
    # «уже заведён» для второй партии считаем по МЕТКЕ, а не по «Партии 935»:
    # часть этих компаний в партии уже лежит, и метку им всё равно надо ставить
    пометка = ГРУППА_БЕЗ_ПРОДУКЦИИ if без else ГРУППА
    if '--primenit' in sys.argv:
        print(json.dumps(применить(inny, гр, пометка), ensure_ascii=False, indent=1))
    else:
        свод, теги, строки = собрать(inny, пометка)
        свод['пример_csv'] = строки[:2]
        свод['тегов_поставили_бы'] = len(теги)
        print(json.dumps(свод, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
