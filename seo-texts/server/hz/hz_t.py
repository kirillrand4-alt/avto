# -*- coding: utf-8 -*-
# 19.10, база холодного прозвона (Кемеровская/Томская/Омская), этап 2, группа «телефоны»: у каждого номера — страница, где он
# найден, и цитата, если есть. Только уже собранное (дроп + базы сервера), ничего не качаем. Фильтр — ИНН из hz-univers.jsonl.
# Откуда: enrich.db (phone_contacts, people); kc1-kontakty-slim / meyer7-kontakty-posl (номера[], первая страница, контекст;
# номера «чей = другая» — не этой компании, отбрасываем); KLYUCH-PROVENANSA-ot-1-sessii.csv; park-snimok.db (contact_source с
# цитатой, nomer_dokaz «доказано»); PARK-VYDACHA-PREDPRIYATIYA.csv (ssylka_telefon), PARK-VYDACHA-KONTAKTY-2S.csv;
# fsa-meyer-kontakty2.jsonl (ссылка на декларацию ФСА); atlas_copco.db (kontakty_svod — только со ссылкой: это свод чужих
# источников; tenders); vygruzka-sobytiy.json;
# PARK-EIS-ORG-KONTAKTY(-1S)-3S.jsonl (карточка организации ЕИС); fsa-meyer-checko.jsonl и hz\hz-checko.jsonl (tel: карточки);
# *checko*html*.zip (tel: + canonical); в конце obzvon-index.db: phones_base («база обзвона (выгрузка)», без ссылки) и
# phones_site («сайт компании», ссылка = первый сайт из sites).
# Номер -> +7XXXXXXXXXX (8… и 10 цифр -> +7…), не-РФ (+7 6xx/7xx, иные коды) и мусор — прочь. Источник — каноническая метка по
# домену ссылки (checko / ЕИС / tender.pro / …), иначе по подписи. Одинаковые (ИНН, номер, доб, источник, ссылка) из разных
# файлов сливаются (файлы через «; »); строка без ссылки сливается в строку того же источника со ссылкой. Разные источники
# одного номера остаются отдельными строками — сборщик (hz_sborka.py) считает подтверждения.
# Выход: C:\sender\server\hz\hz-telefony-t.jsonl (атомарная замена, fsync).
import collections, csv, glob, gzip, io, json, os, re, sqlite3, time, zipfile
csv.field_size_limit(10 ** 9)
D = r'C:\seostat\drop\drop-storage'
S = r'C:\sender\server'
HZ = os.path.join(S, 'hz')
ВЫХ = os.path.join(HZ, 'hz-telefony-t.jsonl')
ДОМЕНЫ = (('checko.ru', 'checko'), ('zakupki.gov.ru', 'ЕИС'), ('tender.pro', 'tender.pro'), ('etpgpb.ru', 'ЭТП ГПБ'),
          ('fsa.gov.ru', 'декларация ФСА'), ('gosnadzor.ru', 'Ростехнадзор'), ('list-org.com', 'list-org'),
          ('rusprofile.ru', 'rusprofile'), ('monitor-pb.ru', 'monitor-pb'), ('b2b-center.ru', 'B2B-Center'),
          ('tektorg.ru', 'ТЭК-Торг'), ('roseltorg.ru', 'Росэлторг'), ('rts-tender.ru', 'РТС-тендер'), ('fabrikant.ru', 'Фабрикант'),
          ('nalog.ru', 'ЕГРЮЛ'), ('nalog.gov.ru', 'ЕГРЮЛ'), ('zachestnyibiznes.ru', 'zachestnyibiznes'), ('sbis.ru', 'СБИС'),
          ('hh.ru', 'hh.ru'), ('2gis.ru', '2ГИС'), ('vk.com', 'ВКонтакте'))
ПРИОРИТЕТ = ('сайт компании', 'ЕИС', 'tender.pro', 'ЭТП ГПБ', 'декларация ФСА', 'Ростехнадзор', 'checko')
ДОБ = re.compile(r'(?:доб\w*|вн\w*|ext\w*|\bд\.|#)\s*[.:№]?\s*(\d{1,6})', re.I)
СТАТ = collections.defaultdict(collections.Counter)


def п(*a):
    print(time.strftime('%d.%m %H:%M:%S'), *a, flush=True)


def хост(u):
    return re.sub(r'^https?://(www\.)?', '', (u or '').strip().lower()).split('/')[0].split(':')[0]


def ссылка_ок(u):
    u = (u or '').strip()
    return u if re.match(r'https?://', u) else ''


def источник(метка, url):
    h = хост(url) if url else ''
    for дом, имя in ДОМЕНЫ:
        if h == дом or h.endswith('.' + дом):
            return имя
    м = (метка or '').lower()
    if 'обратный ход' in м or 'поиск' in м:
        return 'веб-страница'
    if url:
        return 'сайт компании'
    if 'обзвон' in м or 'база обзвона' in м or 'iz_bazy' in м:
        return 'база обзвона (выгрузка)'
    if 'площадок' in м or 'этп' in м:
        return 'ЭТП (карточки площадок)'
    if 'чеко' in м or 'checko' in м:
        return 'checko'
    if 'tender' in м or 'тендер' in м:
        return 'tender.pro'
    if 'eis' in м or 'еис' in м or 'zakupki' in м:
        return 'ЕИС'
    if 'сайт' in м or 'own-site' in м or 'подпись' in м or 'обход' in м:
        return 'сайт компании'
    return (метка or 'прочее')[:40]


def номер(кус, д, счёт=True):
    ц = re.sub(r'\D', '', кус)
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    if len(ц) != 10:
        why = 'не 10/11 цифр' if len(ц) < 10 else 'больше 11 цифр'
    elif ц[0] not in '3489':
        why = 'не РФ (код %s)' % ц[0]
    elif len(set(ц)) < 3 or re.search(r'(\d)\1{6,}', ц):
        why = 'мусор'
    else:
        return [('+7' + ц, re.sub(r'\D', '', д)[:6])]
    if счёт:
        СТАТ['_брак'][why] += 1
    return []


def номера(s, доб='', счёт=True):
    """Строка с одним или несколькими номерами -> [(+7XXXXXXXXXX, доб)]; отбракованное считаем в СТАТ['_брак']."""
    out = []
    куски = []
    for кус in re.split(r'[,;|\n\r]+', str(s or '')):
        if not кус.strip():
            continue
        if куски and re.fullmatch(r'\s*(?:\+?7|8)?\s*(?:\(\s*\d{3,5}\s*\))?\s*', куски[-1]):
            куски[-1] += ' ' + кус
        else:
            куски.append(кус)
    for кус in куски:
        д = str(доб or '').strip()
        м = ДОБ.search(кус)
        if м:
            д = д or м.group(1)
            кус = кус[:м.start()]
        нн = re.findall(r'(?:\+?7|8)[\s\-(]*\d{3,5}[\s\-)]*\d{1,3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)', кус) \
            if len(re.sub(r'\D', '', кус)) > 11 else []
        for x in нн or [кус]:
            out += номер(x, д, счёт)
    return out


class Сбор:
    def __init__(self, U):
        self.U = U
        self.по_ключу = {}

    def add(self, файл, inn, тел, метка='', url='', доб='', фио='', должность='', роль='', цитата='', ист=None):
        inn = str(inn or '').strip()
        if inn not in self.U:
            return
        url = ссылка_ок(url)
        ии = ист or источник(метка, url)
        нн = номера(тел, доб)
        ст = СТАТ[файл.split('.zip:')[0] + '.zip' if '.zip:' in файл else файл]
        ст['строк'] += 1
        if должность and re.match(r'(есть только|номера нет|не-?мобильн)', должность.strip(), re.I):
            должность = ''
        м = re.search(r'общий номер:[^;|\]]*', метка or '')
        if м:
            роль = ((роль or '') + '; ' if роль else '') + м.group(0).strip()
        for t, д in нн:
            з = {'inn': inn, 'телефон': t, 'доб': д, 'фио': (фио or '').strip()[:120], 'должность': (должность or '').strip()[:150],
                 'роль': (роль or '').strip()[:150], 'источник': ии, 'ссылка': url,
                 'цитата': re.sub(r'\s+', ' ', цитата or '').strip()[:300], 'источник_файл': файл}
            к = (inn, t, д, ии, url)
            if к in self.по_ключу:
                self.слить(self.по_ключу[к], з)
            else:
                self.по_ключу[к] = з
                ст['новых номеров'] += 1

    @staticmethod
    def слить(а, б):
        for k in ('доб', 'фио', 'должность', 'роль', 'цитата'):
            if not а[k] and б[k]:
                а[k] = б[k]
        фф = а['источник_файл'].split('; ')
        if б['источник_файл'] not in фф:
            а['источник_файл'] = '; '.join(фф + [б['источник_файл']])

    def итог(self):
        со_ссылкой = collections.defaultdict(list)
        for з in self.по_ключу.values():
            if з['ссылка']:
                со_ссылкой[(з['inn'], з['телефон'], з['источник'])].append(з)
        out = []
        for з in self.по_ключу.values():
            if not з['ссылка'] and со_ссылкой.get((з['inn'], з['телефон'], з['источник'])):
                self.слить(со_ссылкой[(з['inn'], з['телефон'], з['источник'])][0], з)
                continue
            out.append(з)

        def вес(з):
            и = з['источник']
            return (з['inn'], з['телефон'], not з['ссылка'], ПРИОРИТЕТ.index(и) if и in ПРИОРИТЕТ else len(ПРИОРИТЕТ),
                    not з['цитата'], not з['фио'])
        out.sort(key=вес)
        return out


def jl(путь):
    for s in io.open(путь, encoding='utf-8', errors='replace'):
        s = s.strip()
        if s:
            try:
                yield json.loads(s)
            except ValueError:
                pass


def строки_csv(имя):
    return csv.DictReader(io.open(os.path.join(D, имя), encoding='utf-8-sig', errors='replace', newline=''), delimiter=';')


def ro(путь):
    return sqlite3.connect('file:%s?mode=ro' % путь.replace('\\', '/'), uri=True)


def main():
    t0 = time.time()
    U = {x['inn'] for x in jl(os.path.join(HZ, 'hz-univers.jsonl')) if x.get('inn')}
    С = Сбор(U)
    п('вселенная', len(U))

    e = ro(r'C:\sender\enrich.db')
    for inn, тел, чел, роль, ист, url in e.execute('select inn, phone, person, role, source, source_url from phone_contacts'):
        if inn in U:
            м = re.search(r'добавочный (\d+)', ист or '')
            С.add('enrich.db:phone_contacts', inn, тел, ист, url, доб=м.group(1) if м else '', фио=чел, роль=роль)
    for inn, чел, долж, роль, тел, ист, url in e.execute("select inn, person, post, role, phone, source, source_url from people "
                                                          "where phone is not null and phone != ''"):
        if inn in U:
            м = re.search(r'добавочный (\d+)', ист or '')
            С.add('enrich.db:people', inn, тел, ист, url, доб=м.group(1) if м else '', фио=чел, должность=долж, роль=роль)
    п('enrich готов', len(С.по_ключу))

    for имя in ('kc1-kontakty-slim.jsonl', 'meyer7-kontakty-posl.jsonl'):
        for s in io.open(os.path.join(D, имя), encoding='utf-8', errors='replace'):
            if s[9:21].split('"')[0] not in U:
                continue
            try:
                o = json.loads(s)
            except ValueError:
                continue
            for x in o.get('номера') or []:
                if x.get('чей') == 'другая':
                    СТАТ[имя]['чужой номер (чей=другая)'] += 1
                    continue
                стр = [u for u in (x.get('страницы') or []) if ссылка_ок(u)]
                С.add(имя, o.get('inn'), x.get('номер'), 'сайт компании (обход)', стр[0] if стр else '', доб=x.get('доб'),
                      фио=x.get('фио'), должность=x.get('должность'), роль=x.get('роль'), цитата=x.get('контекст'))
        п(имя, len(С.по_ключу))

    for r in строки_csv('KLYUCH-PROVENANSA-ot-1-sessii.csv'):
        if r.get('inn') in U and 'телеф' in (r.get('tip') or ''):
            тел = r.get('znachenie') if номера(r.get('znachenie'), счёт=False) else r.get('nomer_10cifr_ili_pochta')
            С.add('KLYUCH-PROVENANSA-ot-1-sessii.csv', r['inn'], тел, r.get('istochnik'), r.get('ssylka_na_istochnik'),
                  должность=r.get('dolzhnost'), роль=r.get('rol'))

    p = ro(os.path.join(D, 'park-snimok.db'))
    for inn, з, чел, долж, ист, url, цит in p.execute("select inn, znachenie, person, dolzhnost, istochnik, source_url, quote "
                                                       "from contact_source where vid = 'telefon'"):
        С.add('park-snimok.db:contact_source', inn, з, ист, url, фио=чел, должность=долж, цитата=цит)
    for inn, з, чел, долж, url, цит in p.execute('select inn, nomer, chelovek, dolzhnost, ssylka, citata from nomer_dokaz '
                                                 'where dokazano = 1'):
        С.add('park-snimok.db:nomer_dokaz', inn, з, 'доказано снимком', url, фио=чел, должность=долж, цитата=цит)
    п('park-snimok готов', len(С.по_ключу))

    for r in строки_csv('PARK-VYDACHA-PREDPRIYATIYA.csv'):
        if r.get('inn') in U and r.get('telefon'):
            С.add('PARK-VYDACHA-PREDPRIYATIYA.csv', r['inn'], r['telefon'], r.get('vid_nomera'), r.get('ssylka_telefon'),
                  фио=r.get('chelovek'), должность=r.get('dolzhnost'), роль=r.get('vid_nomera'))
    for r in строки_csv('PARK-VYDACHA-KONTAKTY-2S.csv'):
        if r.get('inn') in U and 'телефон' in (r.get('vid') or ''):
            С.add('PARK-VYDACHA-KONTAKTY-2S.csv', r['inn'], r.get('znachenie'), r.get('istochnik'), r.get('ssylka'),
                  фио=r.get('chelovek'), должность=r.get('dolzhnost'), роль=r.get('rol'), цитата=r.get('citata'))

    for o in jl(os.path.join(D, 'fsa-meyer-kontakty2.jsonl')):
        if str(o.get('инн')) in U and o.get('id'):
            for t in o.get('телефоны') or []:
                С.add('fsa-meyer-kontakty2.jsonl', str(o['инн']), t, ист='декларация ФСА',
                      url='https://pub.fsa.gov.ru/rds/declaration/view/%s/common' % o['id'], роль='заявитель декларации')

    a = ro(os.path.join(D, 'atlas_copco.db'))
    for inn, чел, долж, роль, тел, ист, url in a.execute("select inn, person, post, rol, phone, istochnik, source_url "
                                                          "from kontakty_svod where phone is not null and phone != ''"):
        if ссылка_ок(url):
            С.add('atlas_copco.db:kontakty_svod', inn, тел, ист, url, фио=чел, должность=долж, роль=роль)
    for пл, ном, inn, фио, тел, назв in a.execute("select platform, reg_number, inn, fio, phone, title from tenders "
                                                   "where phone is not null and phone != ''"):
        м = re.match(r'tp_(\d+)$', ном or '')
        С.add('atlas_copco.db:tenders', inn, тел, пл, 'https://www.tender.pro/#/tender/%s' % м.group(1) if м and 'tender' in (пл or '') else '',
              фио=фио, роль='контакт закупки', цитата=('закупка %s: %s' % (ном, назв or ''))[:300])

    о = json.load(io.open(os.path.join(D, 'vygruzka-sobytiy.json'), encoding='utf-8'))
    for inn, сп in (о.get('телефоны') or {}).items():
        for x in сп:
            С.add('vygruzka-sobytiy.json', inn, x.get('phone'), x.get('src'), '', роль=x.get('role'))
    del о

    for имя in ('PARK-EIS-ORG-KONTAKTY-3S.jsonl', 'PARK-EIS-ORG-KONTAKTY-1S-3S.jsonl'):
        for o in jl(os.path.join(D, имя)):
            if o.get('telefon'):
                уу = re.findall(r'https?://[^\s|;,]+', o.get('istochniki') or '')
                С.add(имя, o.get('inn'), o['telefon'], 'ЕИС', уу[0] if уу else '', ист='ЕИС', фио=o.get('chelovek'),
                      должность=o.get('dolzhnost'), роль=o.get('vid_nomera'))

    for путь in (os.path.join(S, 'fsa-meyer-checko.jsonl'), os.path.join(HZ, 'hz-checko.jsonl')):
        if os.path.exists(путь):
            for o in jl(путь):
                if o.get('итог') == 'ok' and ссылка_ок(o.get('ссылка')):
                    for t in o.get('телефоны') or []:
                        С.add(os.path.basename(путь), o.get('inn'), t, ист='checko', url=o['ссылка'], цитата='телефон на карточке checko')

    for zп in sorted(glob.glob(os.path.join(D, '*checko*html*.zip'))):
        z = zipfile.ZipFile(zп)
        for nm in z.namelist():
            inn = os.path.basename(nm).split('.')[0].split('-')[0]
            if inn not in U:
                continue
            try:
                h = gzip.decompress(z.read(nm)).decode('utf-8', 'replace')
            except Exception:  # noqa: BLE001
                СТАТ[os.path.basename(zп)]['не разобран'] += 1
                continue
            м = re.search(r'<link rel="canonical" href="([^"]+)"', h)
            if not м or not re.search(r'/(company|entrepreneur)/', м.group(1)):
                continue
            url = м.group(1).rstrip('/') + ('/contacts' if '-kontakty' in nm else '')
            for t in sorted(set(re.findall(r'href="tel:(\+?\d{10,12})"', h))):
                С.add('%s:%s' % (os.path.basename(zп), os.path.basename(nm)), inn, t, ист='checko', url=url,
                      цитата='телефон на %s checko' % ('странице контактов' if '-kontakty' in nm else 'карточке'))
    п('checko готов', len(С.по_ключу))

    o = ro(r'C:\sender\obzvon-index.db')
    for inn, пб, пс, сайты in o.execute('select inn, phones_base, phones_site, sites from obzvon'):
        if inn not in U:
            continue
        if пб:
            С.add('obzvon-index.db:phones_base', inn, пб, ист='база обзвона (выгрузка)')
        if пс:
            сс = [x.strip() for x in re.split(r'[|,;\s]+', сайты or '') if x.strip()]
            сайт = сс[0] if сс else ''
            if сайт and not re.match(r'https?://', сайт):
                сайт = 'http://' + сайт
            С.add('obzvon-index.db:phones_site', inn, пс, ист='сайт компании', url=сайт)

    out = С.итог()
    tmp = ВЫХ + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        for з in out:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ВЫХ)
    по_ист = collections.Counter(з['источник'] for з in out)
    сводка = {'записей': len(out), 'ИНН': len({з['inn'] for з in out}), 'пар ИНН+номер': len({(з['inn'], з['телефон']) for з in out}),
              'со ссылкой': sum(1 for з in out if з['ссылка']), 'ИНН с номером со ссылкой': len({з['inn'] for з in out if з['ссылка']}),
              'с цитатой': sum(1 for з in out if з['цитата']), 'мобильных': sum(1 for з in out if з['телефон'].startswith('+79')),
              'по источникам': по_ист.most_common(),
              'по файлам': {k: dict(v) for k, v in СТАТ.items()}, 'сек': round(time.time() - t0)}
    print('===ИТОГ===')
    print(json.dumps(сводка, ensure_ascii=False))


if __name__ == '__main__':
    main()
