# -*- coding: utf-8 -*-
# 14.10, владелец: выкачка на выходные — декларации ФСА по словарю продукции Meyer (fsa-meyer-slova.json, ~240 основ) за
# 2020+ годы. Лимит выдачи 1000 обходится окнами по дате регистрации (regDate): окно > 1000 делится пополам до дня.
# Изготовитель — юрлицо/ИП РФ (ИНН); контакты из карточки — где заявитель = изготовитель. Владелец: «пока не отсеивай тех, кого
# в базу уже закинули, в ФСА контакты дополнительные есть, просто не прогонять классификацию по ним» — отметка «уже в базе».
# Всё durable на сервере (fsync, резюм по окнам и карточкам): fsa-meyer-decl.jsonl, fsa-meyer-okna.jsonl,
# fsa-meyer-kontakty.jsonl; итог fsa-meyer-izg.jsonl + дроп. Лог: fsa_meyer_*.log.
import datetime, io, json, os, re, sqlite3, sys, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender')
import fsa_pilot_orehi as F  # noqa: E402  (вход, запрос — рабочий клиент pub.fsa.gov.ru)
ДЕКЛ = os.path.join(DIR, 'fsa-meyer-decl.jsonl')
ОКНА = os.path.join(DIR, 'fsa-meyer-okna.jsonl')
КОНТ = os.path.join(DIR, 'fsa-meyer-kontakty.jsonl')
ИТОГ = os.path.join(DIR, 'fsa-meyer-izg.jsonl')
ДРОП = r'C:\seostat\drop\drop-storage'
С_ДАТЫ = datetime.date(2020, 1, 1)
ПОЛЯ = ('id', 'declNumber', 'declDate', 'declEndDate', 'idStatus', 'applicantType', 'applicantInn', 'applicantName', 'manufacterInn',
        'manufacterName', 'manufacterOgrn', 'manufacterAddress', 'manufacterType', 'productFullName', 'productOrig',
        'productIdentificationTrademark')


def п(*a):
    print(time.strftime('%d.%m %H:%M:%S'), *a, flush=True)


def дописать(путь, x):
    with io.open(путь, 'a', encoding='utf-8') as f:
        f.write(json.dumps(x, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def читать(путь):
    if not os.path.exists(путь):
        return []
    out = []
    for s in io.open(путь, encoding='utf-8', errors='replace'):
        try:
            out.append(json.loads(s))
        except ValueError:
            pass
    return out


class Сессия:
    def __init__(self):
        self.H2, self.t = F.вход(), time.time()

    def стр(self, сл, d1, d2, page, size=100):
        if time.time() - self.t > 1800:  # токен анонимного входа — обновлять
            self.H2, self.t = F.вход(), time.time()
        тело = {'size': size, 'page': page, 'filter': {'columnsSearch': [{'name': 'productFullName', 'search': сл, 'type': 0,
                                                                         'translated': False}],
                                                     'regDate': {'minDate': d1.isoformat(), 'maxDate': d2.isoformat()}},
                'columnsSort': [{'column': 'declDate', 'sort': 'DESC'}]}
        return F.запрос(self.H2, '/api/v1/rds/common/declarations/get', тело) or {}


def окно(С, сл, d1, d2, готовые, декл_ид):
    ключ = '%s|%s|%s' % (сл, d1, d2)
    if ключ in готовые:
        return
    d = С.стр(сл, d1, d2, 0, 10)
    всего = d.get('total') or 0
    if всего >= 1000 and d2 > d1:
        mid = d1 + (d2 - d1) // 2
        окно(С, сл, d1, mid, готовые, декл_ид)
        окно(С, сл, mid + datetime.timedelta(days=1), d2, готовые, декл_ид)
        дописать(ОКНА, {'ключ': ключ, 'делено': 1})
        return
    n = 0
    for page in range(10):
        it = (С.стр(сл, d1, d2, page).get('items') or []) if всего else []
        for x in it:
            if x.get('id') in декл_ид:
                continue
            декл_ид.add(x.get('id'))
            y = {k: x.get(k) for k in ПОЛЯ}
            y['слово'] = сл
            дописать(ДЕКЛ, y)
            n += 1
        if len(it) < 100:
            break
        time.sleep(0.3)
    дописать(ОКНА, {'ключ': ключ, 'всего': всего, 'новых': n, 'переполнено': всего >= 1000})
    готовые.add(ключ)


def main():
    t0 = time.time()
    слова = [x['о'] for x in json.load(io.open(os.path.join(DIR, 'fsa-meyer-slova.json'), encoding='utf-8'))]
    готовые = {x['ключ'] for x in читать(ОКНА) if 'ключ' in x}
    декл = {x['id']: x for x in читать(ДЕКЛ) if x.get('id')}
    декл_ид = set(декл)
    п('слов', len(слова), '| окон уже', len(готовые), '| деклараций уже', len(декл))
    С = Сессия()
    сегодня = datetime.date.today()
    for k, сл in enumerate(слова, 1):
        до = len(декл_ид)
        окно(С, сл, С_ДАТЫ, сегодня, готовые, декл_ид)
        п('слово %d/%d «%s»: +%d, всего %d, %.0f мин' % (k, len(слова), сл, len(декл_ид) - до, len(декл_ид), (time.time() - t0) / 60))
    # изготовители РФ
    декл = {x['id']: x for x in читать(ДЕКЛ) if x.get('id')}
    изг = {}
    for x in декл.values():
        инн = re.sub(r'\D', '', x.get('manufacterInn') or '')
        if len(инн) not in (10, 12) or 'беларус' in (x.get('manufacterAddress') or '').lower():
            continue
        z = изг.setdefault(инн, {'инн': инн, 'имя': x.get('manufacterName'), 'адрес': (x.get('manufacterAddress') or '')[:200],
                                 'деклараций': 0, 'продукция': [], 'слова': [], 'последняя': '', 'сам_заявитель': []})
        z['деклараций'] += 1
        if x['слово'] not in z['слова']:
            z['слова'].append(x['слово'])
        if len(z['продукция']) < 6 and (x.get('productFullName') or '')[:120] not in z['продукция']:
            z['продукция'].append((x.get('productFullName') or '')[:120])
        z['последняя'] = max(z['последняя'], x.get('declDate') or '')
        if re.sub(r'\D', '', x.get('applicantInn') or '') == инн:
            z['сам_заявитель'].append((x.get('declDate') or '', x['id']))
    п('изготовителей РФ', len(изг), '| сами заявители', sum(1 for z in изг.values() if z['сам_заявитель']))
    # контакты карточки — ВСЕМ (и тем, кто уже в базе)
    конт = {x['инн']: x for x in читать(КОНТ) if x.get('инн')}
    for j, (инн, z) in enumerate(sorted(изг.items(), key=lambda kv: -kv[1]['деклараций']), 1):
        if инн in конт or not z['сам_заявитель']:
            continue
        ид = max(z['сам_заявитель'])[1]
        d = F.запрос(С.H2, '/api/v1/rds/common/declarations/%s' % ид)
        if d is None:
            С.H2, С.t = F.вход(), time.time()
            continue
        т = json.dumps(d, ensure_ascii=False)
        x = {'инн': инн, 'id': ид, 'почты': sorted(set(m.lower() for m in re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', т)))[:6],
             'телефоны': sorted(set(re.sub(r'[^\d+]', '', m) for m in re.findall(r'"value"\s*:\s*"(\+?[78][\d\s()\-]{9,18})"', т)))[:6]}
        конт[инн] = x
        дописать(КОНТ, x)
        if j % 200 == 0:
            п('карточек', len(конт))
        time.sleep(0.3)
    # отметки: уже в базе Meyer / база обзвона / активная сделка (не отсеиваем — владелец)
    сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))
    раздел = {}
    for р in ('компании', 'снято', 'ниже_порога', 'на_решение', 'ждут_оквэд'):
        for i in (сп.get(р) or {}):
            раздел.setdefault(i, р)
    for x in читать(os.path.join(DIR, 'meyer7-inn-sayt.jsonl')):
        раздел.setdefault(x.get('инн'), 'компании (ИНН по сайту)')
    сд = {}
    for s in io.open(os.path.join(ДРОП, 'meyer7-sdelki-aktivnye.tsv'), encoding='utf-8').read().splitlines()[1:]:
        ч = s.split('\t')
        if ч and ч[0].isdigit():
            сд[ч[0]] = ч[1] if len(ч) > 1 else ''
    обз = {}
    c = sqlite3.connect(r'file:C:\sender\obzvon-index.db?mode=ro', uri=True, timeout=120)
    for i, выр, окв, рег in c.execute('select inn, revenue_rub, okved_main, region from obzvon'):
        if str(i) in изг:
            обз[str(i)] = (выр or 0, окв or '', рег or '')
    c.close()
    with io.open(ИТОГ, 'w', encoding='utf-8') as f:
        for инн, z in изг.items():
            к = конт.get(инн) or {}
            о = обз.get(инн)
            z2 = dict(z, сам_заявитель=len(z['сам_заявитель']), почты=к.get('почты', []), телефоны=к.get('телефоны', []),
                      в_базе_meyer=раздел.get(инн, ''), в_базе_обзвона=bool(о), выручка=(о or (0,))[0], оквэд=(о or ('', ''))[1],
                      регион=(о or ('', '', ''))[2], сделка_meyer=сд.get(инн, ''))
            z2['классифицировать'] = not z2['в_базе_meyer'] and not z2['сделка_meyer']
            f.write(json.dumps(z2, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    for пп in (ИТОГ, КОНТ, ОКНА):
        import shutil
        shutil.copyfile(пп, os.path.join(ДРОП, os.path.basename(пп)))
    п('===ИТОГ===', json.dumps({'деклараций': len(декл), 'изготовителей': len(изг), 'с_контактами': sum(1 for к in конт.values()
                                                                                                    if к.get('почты') or к.get('телефоны')),
                                'уже_в_базе': sum(1 for i in изг if i in раздел), 'новых': sum(1 for i in изг if i not in раздел)},
                               ensure_ascii=False), 'за %.1f ч' % ((time.time() - t0) / 3600))


if __name__ == '__main__':
    os.chdir(DIR)
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'fsa_meyer_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'fsa_meyer_vykachka.py'), '--vnutri'], cwd=DIR,
                                 creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                                 close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        time.sleep(40)
        print('===ИТОГ===')
        print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог),
                          'хвост': open(лог, encoding='utf-8', errors='replace').read()[-800:]}, ensure_ascii=False))
        sys.exit(0)
    main()
