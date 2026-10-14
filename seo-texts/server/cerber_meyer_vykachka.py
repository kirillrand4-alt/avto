# -*- coding: utf-8 -*-
# 14.10, владелец: выкачка на выходные — публичный «Реестр предприятий Таможенного союза» Цербера (ВетИС, cerberus.vetrf.ru,
# certified/pub): аттестованные предприятия РФ по пищевым и кормовым видам (мясо, птица, молоко, корма, жир, яйцо, мёд, кишсырьё,
# «производство подконтрольной продукции»). Рыба не нужна (владелец 08.10) — виды гидробионтов не берём.
# Таблица отдаётся POST JSON (itemPerPageCount — весь вид за раз). ИНН в реестре нет: юрлицо + юр. адрес -> DaData (suggest/party,
# регион должен совпасть). Отметки «уже в базе Meyer»/сделка — не отсев (владелец). Durable: cerber-meyer.jsonl (fsync, резюм по
# виду) + cerber-meyer-inn.jsonl; дроп. Лог: cerber_meyer_*.log.
import html as H, http.cookiejar, io, json, os, re, ssl, sys, time, urllib.request
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender')
ВЫХ = os.path.join(DIR, 'cerber-meyer.jsonl')
ИНН_ВЫХ = os.path.join(DIR, 'cerber-meyer-inn.jsonl')
ДРОП = r'C:\seostat\drop\drop-storage'
B = 'https://cerberus.vetrf.ru/cerberus/'
РФ = '74a3cbb1-56fa-94f3-ab3f-e8db4940d96b'
НУЖНЫ = re.compile(r'боен|мясо|птиц|молок|корм|жиропер|кишечн|яйц|мед|пчел|подконтрольн|убо|холодильн|зерн|масл', re.I)
НЕ_НУЖНЫ = re.compile(r'гидробионт|рыб|розничн|аптек|клиник|лаборатор|зоомагазин|ЛПХ|личные подсобные|госветслужб|исправительн|'
                      r'дошкольн|медицинск|ипподром|крематор|пестицид|удален|работникам|вылову', re.I)


def п(*a):
    print(time.strftime('%d.%m %H:%M:%S'), *a, flush=True)


def дописать(путь, x):
    with io.open(путь, 'a', encoding='utf-8') as f:
        f.write(json.dumps(x, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def опенер():
    op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()),
                                     urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), urllib.request.ProxyHandler({}))
    op.addheaders = [('User-Agent', 'Mozilla/5.0')]
    return op


def виды(op):
    h = op.open(B + 'certified/pub', timeout=90).read().decode('utf-8', 'replace')
    сел = re.search(r'<select[^>]*name="objTypes"[^>]*>(.*?)</select>', h, re.S).group(1)
    return [(g, H.unescape(n).strip()) for g, n in re.findall(r'<option[^>]*value="([^"]+)"[^>]*>([^<]+)', сел)
            if НУЖНЫ.search(n) and not НЕ_НУЖНЫ.search(n)]


def вид_целиком(op, g):
    d = {"data": {"itemPerPageCount": "30000", "objectNumbers": [], "name": "", "latinName": "", "businessEntityInnOgrn": "",
                  "addressView": "", "productStatusInfoStateList": ["CURRENT"], "registryStatusList": ["VERIFIED"],
                  "certifiedStatusList": [], "countries": [РФ], "regions": [], "districts": [], "supervisedObjectTypeGuidList": [g],
                  "certifiedActivityIdList": [], "productTypeId": "", "productGuid": "", "subProductGuid": ""}}
    for попытка in range(4):
        try:
            r = urllib.request.Request(B + 'certified/pub?c=0&clear=true', data=json.dumps(d).encode(),
                                       headers={'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'})
            return op.open(r, timeout=600).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            п('сбой', g, repr(e)[:120])
            time.sleep(30 * (попытка + 1))
            op.open(B + 'certified/pub', timeout=90).read()
    return ''


def разобрать(h, вид):
    т = H.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)))
    out = []
    for кус in re.split(r'(?=Номер: RU-)', т)[1:]:
        ном = re.match(r'Номер: (RU-\S+)', кус).group(1)
        имена = re.findall(r'Название: (.*?) (?=Фактический адрес|Юр\. адрес|Название на|Вид предприятия)', кус)
        адр = re.search(r'Фактический адрес: (.*?) (?=Вид предприятия|Название)', кус)
        юр = re.search(r'Название: ([^:]*?) Юр\. адрес: (.*?)(?= Название:| [А-ЯЁ][а-яё]+ и | Мясо| Молоко| Корма| Продукция|$)', кус)
        прод = re.findall(r'([А-ЯЁ][^\[\]|]{3,200}?) \[ ([^\]]+)\]', кус)
        out.append({'номер': ном, 'вид': вид, 'объект': (имена[0] if имена else '')[:200], 'адрес': (адр.group(1) if адр else '')[:250],
                    'юрлицо': (юр.group(1) if юр else (имена[-1] if имена else ''))[:200],
                    'юр_адрес': re.split(r' (?=[А-ЯЁ][а-яё ,]+ / )', юр.group(2))[0][:250] if юр else '',
                    'продукция': ['%s [%s]' % (a.strip(), b.strip()) for a, b in прод][:8]})
    return out


def регион(адр):
    м = re.search(r'Российская Федерация, ([^,]+)', адр or '')
    return (м.group(1) if м else '').replace('обл.', '').replace('край', '').replace('Респ.', '').strip().lower()[:12]


def main():
    t0 = time.time()
    op = опенер()
    вв = виды(op)
    п('видов', len(вв), [н for _, н in вв])
    готово = set()
    if os.path.exists(ВЫХ):
        for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
            try:
                готово.add(json.loads(s)['вид'])
            except (ValueError, KeyError):
                pass
    for g, н in вв:
        if н in готово:
            continue
        зап = разобрать(вид_целиком(op, g), н)
        for x in зап:
            дописать(ВЫХ, x)
        if not зап:
            дописать(ВЫХ, {'вид': н, 'пусто': 1})
        п('вид «%s»: %d' % (н, len(зап)))
        time.sleep(5)
    # ИНН через DaData (юрлицо + регион)
    import meyer7_inn_poisk as IP
    dd = IP.DaData()
    все = [json.loads(s) for s in io.open(ВЫХ, encoding='utf-8', errors='replace') if s.strip()]
    юрл = {}
    for x in все:
        if x.get('юрлицо'):
            юрл.setdefault((x['юрлицо'], регион(x.get('юр_адрес') or x.get('адрес'))), x)
    сделано = set()
    if os.path.exists(ИНН_ВЫХ):
        for s in io.open(ИНН_ВЫХ, encoding='utf-8', errors='replace'):
            try:
                y = json.loads(s)
                сделано.add((y['юрлицо'], y['рег']))
            except (ValueError, KeyError):
                pass
    п('юрлиц', len(юрл), '| уже', len(сделано))
    for (ю, рег), x in юрл.items():
        if (ю, рег) in сделано:
            continue
        if dd.лимит:
            п('DaData: лимит суток — остаток в следующий запуск')
            break
        к = dd.найти('suggest', ю) or []
        выбор = [c for c in к if c.get('статус') == 'ACTIVE' and (not рег or рег[:6] in (c.get('регион') or '').lower())]
        y = {'юрлицо': ю, 'рег': рег, 'инн': выбор[0]['инн'] if len(выбор) == 1 else '', 'кандидатов': len(выбор),
             'имя_егрюл': выбор[0]['имя'] if выбор else '', 'оквэд': выбор[0].get('оквэд', '') if выбор else ''}
        дописать(ИНН_ВЫХ, y)
    import shutil
    for пп in (ВЫХ, ИНН_ВЫХ):
        shutil.copyfile(пп, os.path.join(ДРОП, os.path.basename(пп)))
    п('===ИТОГ===', json.dumps({'объектов': sum(1 for x in все if x.get('номер')), 'юрлиц': len(юрл)}, ensure_ascii=False),
      'за %.1f ч' % ((time.time() - t0) / 3600))


if __name__ == '__main__':
    os.chdir(DIR)
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'cerber_meyer_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'cerber_meyer_vykachka.py'), '--vnutri'], cwd=DIR,
                                 creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                                 close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        time.sleep(60)
        print('===ИТОГ===')
        print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог),
                          'хвост': open(лог, encoding='utf-8', errors='replace').read()[-1200:]}, ensure_ascii=False))
        sys.exit(0)
    main()
