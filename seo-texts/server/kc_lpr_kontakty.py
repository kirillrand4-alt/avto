# -*- coding: utf-8 -*-
r"""Контакты ЛПР по списку ИНН со всех баз сервера (12.11, владелец: «собери подтверждённые номера со всех баз со ссылкой на
страницу, с ФИО принимающих решение — техдиректор, инженер, закупщики и все подобные — со всей информацией о компании»).

Вход: ca\kc-lpr-inn.json (список ИНН). Источники (только чтение):
  * журналы обхода всех наборов (<набор>-kontakty.jsonl, последняя запись ok по ИНН в каждом наборе): номер/почта не чужие
    (чей != другая), есть страница-источник;
  * итоги агентов, принятые перепроверкой (<набор>-glubokiy2.jsonl, ca-lpr-agent2.jsonl);
  * enrich.db: people, phone_contacts, emails — с источником (source_url) и ролью/ФИО;
  * ЕИС: ca\ca-zakupki-chistye.jsonl (проверенные контакты закупок).
Фильтр ЛПР: роль/должность/подпись — руководство, тех. служба (инженер, механик, энергетик), производство, технолог,
снабжение/закупки; либо отметка «ЛПР = да».
Выход (дроп): kc-lpr-kontakty.jsonl (контакты), kc-lpr-kompanii.jsonl (сведения о компании). Запуск: сам в фон.
"""
import glob, io, json, os, re, sqlite3, subprocess, sys, time

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    with open(os.path.join(ПАПКА, 'kc_lpr_kontakty_%s.log' % time.strftime('%d%m-%H%M')), 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(8)
    print('===ИТОГ=== запущен')
    sys.exit(0)

ЛПР = re.compile(r'директор|руковод|генеральн|собственник|учредител|владел|президент|управляющ|техническ|техдир|главн\w* инженер|'
                 r'инженер|механик|энергетик|ОГМ|ОГЭ|КИП|производств|технолог|цех|снабж|закуп|МТО|материально|тендер|'
                 r'логист|склад|эксплуатац|ремонт|сервис|главный|начальник|заместител', re.I)
НЕ_ЛПР = re.compile(r'бухгалтер|кадр|HR|персонал|маркетинг|реклам|продаж|менеджер по продажам|секретар|юрист|охран|PR\b', re.I)


def отметка(**k):
    k['обновлено'] = time.strftime('%H:%M:%S')
    with open(os.path.join(ПАПКА, 'kc-lpr-progress.json'), 'w', encoding='utf-8') as f:
        json.dump(k, f, ensure_ascii=False)


def лпр(*тексты, отметка_лпр=''):
    т = ' '.join(str(x or '') for x in тексты)
    if str(отметка_лпр).lower() == 'да':
        return True
    return bool(ЛПР.search(т)) and not (НЕ_ЛПР.search(т) and not re.search(r'директор|инженер|снабж|закуп', т, re.I))


def main():
    нужно = set(json.load(open(os.path.join(ПАПКА, 'kc-lpr-inn.json'), encoding='utf-8')))
    out = io.open(os.path.join(ДРОП, 'kc-lpr-kontakty.jsonl'), 'w', encoding='utf-8')
    комп = {}
    сч = {'контактов': 0}

    def пиши(инн, **к):
        к['ИНН'] = инн
        out.write(json.dumps(к, ensure_ascii=False) + '\n')
        сч['контактов'] += 1
    # ---- 1. журналы обхода всех наборов ----
    журналы = sorted(set(glob.glob(os.path.join(DIR, '*-kontakty.jsonl'))) - set(glob.glob(os.path.join(DIR, '_*'))))
    рег = re.compile(r'"inn":\s*"(\d{10,12})"')
    for i, п in enumerate(журналы):
        набор = os.path.basename(п).replace('-kontakty.jsonl', '')
        посл = {}
        for s in io.open(п, encoding='utf-8', errors='replace'):
            м = рег.search(s[:200])
            if not м or м.group(1) not in нужно:
                continue
            try:
                з = json.loads(s)
            except ValueError:
                continue
            if з.get('итог') == 'ok':
                посл[з['inn']] = з
        for инн, з in посл.items():
            к = комп.setdefault(инн, {'ИНН': инн, 'наборы': []})
            к['наборы'].append(набор)
            for поле in ('сайт', 'описание', 'продукция', 'мощности'):
                if з.get(поле) and not к.get(поле):
                    к[поле] = з[поле] if поле != 'сайт' else з[поле]
            for x in з.get('номера') or []:
                if x.get('чей') == 'другая' or not (x.get('номер') or x.get('почта')):
                    continue
                стр = [u for u in (x.get('страницы') or []) if str(u).startswith('http')]
                if not стр:
                    continue
                if not лпр(x.get('роль'), x.get('должность'), x.get('фио'), отметка_лпр=x.get('лпр')):
                    continue
                пиши(инн, ФИО=x.get('фио') or '', должность=x.get('должность') or '', роль=x.get('роль') or '',
                     ЛПР=x.get('лпр') or '', телефон=x.get('номер') or '', доб=x.get('доб') or '', почта=x.get('почта') or '',
                     страница=стр[0], подтверждение='найден на странице сайта компании' + (' (обогатитель)' if x.get('_ec') else ''),
                     источник='обход: ' + набор, подпись=(x.get('контекст') or '')[-250:])
        отметка(этап='журналы', файл=i + 1, из=len(журналы), компаний=len(комп), **сч)
    # ---- 2. агенты (принятые перепроверкой) ----
    for п in glob.glob(os.path.join(DIR, '*-glubokiy2.jsonl')) + glob.glob(os.path.join(DIR, '*lpr-agent2.jsonl')):
        набор = os.path.basename(п).replace('.jsonl', '')
        for s in io.open(п, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
            except ValueError:
                continue
            инн = str(з.get('inn') or '')
            if инн not in нужно:
                continue
            for x in (з.get('номера') or []) + (з.get('почты') or []):
                if not isinstance(x, dict) or not лпр(x.get('класс'), x.get('должность'), x.get('фио')):
                    continue
                пиши(инн, ФИО=x.get('фио') or '', должность=x.get('должность') or '', роль=x.get('класс') or '', ЛПР='',
                     телефон=x.get('номер') or '', доб='', почта=x.get('почта') or '', страница=x.get('url') or '',
                     подтверждение='агент: номер/почта есть на открытой странице сайта компании, перепроверено',
                     источник='агент: ' + набор, подпись='')
    отметка(этап='агенты', компаний=len(комп), **сч)
    # ---- 3. enrich.db ----
    con = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=120)
    ин = ','.join("'%s'" % x for x in нужно)
    for инн, ч, пост, роль, тел, почта, ист, url, чья in con.execute(
            'select inn, person, post, role, phone, email, source, source_url, prinadlezhnost_inn from people where inn in (%s)' % ин):
        if (тел or почта) and url and лпр(пост, роль):
            if чья and str(чья) != str(инн):
                continue
            пиши(инн, ФИО=ч or '', должность=пост or '', роль=роль or '', ЛПР='', телефон=тел or '', доб='', почта=почта or '',
                 страница=url, подтверждение='enrich: человек со страницы-источника', источник='enrich.people: ' + (ист or ''), подпись='')
    for инн, тел, ч, роль, ист, url in con.execute(
            'select inn, phone, person, role, source, source_url from phone_contacts where inn in (%s)' % ин):
        if тел and url and (ч or роль) and лпр(роль, ч):
            пиши(инн, ФИО=ч or '', должность='', роль=роль or '', ЛПР='', телефон=тел, доб='', почта='', страница=url,
                 подтверждение='enrich: телефон со страницы-источника', источник='enrich.phone_contacts: ' + (ист or ''), подпись='')
    for инн, почта, роль, ч, ист, url, раздел in con.execute(
            'select inn, email, role, person, source, source_url, razdel from emails where inn in (%s)' % ин):
        if почта and url and лпр(роль, ч, раздел):
            пиши(инн, ФИО=ч or '', должность=раздел or '', роль=роль or '', ЛПР='', телефон='', доб='', почта=почта, страница=url,
                 подтверждение='enrich: почта со страницы-источника', источник='enrich.emails: ' + (ист or ''), подпись='')
    con.close()
    отметка(этап='enrich', компаний=len(комп), **сч)
    # ---- 4. ЕИС (проверенные) ----
    п = os.path.join(ПАПКА, 'ca-zakupki-chistye.jsonl')
    if os.path.exists(п):
        for s in io.open(п, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(s)
            except ValueError:
                continue
            if str(x.get('inn') or '') in нужно and (x.get('телефон') or x.get('почта')):
                пиши(str(x['inn']), ФИО=x.get('фио') or '', должность=x.get('должность') or 'контактное лицо закупок',
                     роль='Закупки / снабжение', ЛПР='да', телефон=x.get('телефон') or '', доб='', почта=x.get('почта') or '',
                     страница=x.get('url') or '', подтверждение='ЕИС: ' + str(x.get('вердикт') or ''), источник='закупки ЕИС', подпись='')
    out.close()
    # ---- сведения о компании: база обзвона ----
    try:
        con = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True, timeout=120)
        for инн, н, нп, рег, адр, дир, сайты in con.execute(
                'select inn, name_short, name_full, region, address, director, sites from obzvon where inn in (%s)' % ин):
            к = комп.setdefault(str(инн), {'ИНН': str(инн), 'наборы': []})
            к.update({'название (база обзвона)': н or нп or '', 'регион': рег or '', 'адрес': адр or '', 'директор (ЕГРЮЛ)': дир or ''})
            if сайты and not к.get('сайт'):
                к['сайт'] = сайты
        con.close()
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_обзвон=repr(e)[:150])
    with io.open(os.path.join(ДРОП, 'kc-lpr-kompanii.jsonl'), 'w', encoding='utf-8') as f:
        for к in комп.values():
            к['наборы'] = ', '.join(к['наборы'])
            f.write(json.dumps(к, ensure_ascii=False) + '\n')
    отметка(этап='готово', компаний_со_сведениями=len(комп), **сч)


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:  # noqa: BLE001
        отметка(этап='ошибка', ошибка=repr(e)[:400])
        raise
