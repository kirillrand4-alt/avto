# -*- coding: utf-8 -*-
# 19.10, владелец: ИНН Цербера не угадывать, а сверять. В публичной таблице реестра ИНН нет, xls-отчёт с ИНН у анонима не
# формируется (висит «NEW»), но поиск реестра по ИНН/ОГРН работает. Кандидаты DaData по названию юрлица (кэш прошлого прогона
# + очищенное название для ненайденных) -> для каждого кандидата поиск в Цербере по ИНН; подтверждён = реестр выдаёт по этому
# ИНН то же юрлицо (совпадение слов названия). Durable: cerber-meyer-inn2.jsonl (fsync, резюм по юрлицо|рег) + дроп.
import io, json, os, re, shutil, sys, time, urllib.request
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender'); os.chdir(DIR)
import cerber_meyer_vykachka as C  # noqa: E402
ВХ = os.path.join(DIR, 'cerber-meyer-inn.jsonl')
ВЫХ = os.path.join(DIR, 'cerber-meyer-inn2.jsonl')
ОПФ = re.compile(r'общество с ограниченной ответственностью|акционерное общество|публичное|непубличное|закрытое|открытое|'
                 r'индивидуальный предприниматель|сельскохозяйственный производственный кооператив|крестьянское \(фермерское\) хозяйство|'
                 r'глава кфх|\b(ооо|оао|зао|пао|ао|ип|кфх|спк|ск)\b', re.I)


def п(*a):
    print(time.strftime('%d.%m %H:%M:%S'), *a, flush=True)


def слова(s):
    s = ОПФ.sub(' ', (s or '').lower().replace('ё', 'е'))
    return {w for w in re.findall(r'[a-zа-я0-9]{2,}', s)}


def похоже(а, б):
    x, y = слова(а), слова(б)
    return bool(x and y) and len(x & y) / min(len(x), len(y)) >= 0.6


class Цербер:
    def __init__(self):
        self.op, self.t = C.опенер(), 0

    def по_инн(self, инн):
        if time.time() - self.t > 900:
            self.op.open(C.B + 'certified/pub', timeout=90).read(); self.t = time.time()
        d = {"data": {"itemPerPageCount": "50", "objectNumbers": [], "name": "", "latinName": "", "businessEntityInnOgrn": инн,
                      "addressView": "", "productStatusInfoStateList": ["CURRENT"], "registryStatusList": ["VERIFIED"], "certifiedStatusList": [],
                      "countries": [C.РФ], "regions": [], "districts": [], "supervisedObjectTypeGuidList": [], "certifiedActivityIdList": [],
                      "productTypeId": "", "productGuid": "", "subProductGuid": ""}}
        for попытка in range(4):
            try:
                r = urllib.request.Request(C.B + 'certified/pub?c=0&clear=true', data=json.dumps(d).encode(),
                                           headers={'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'})
                h = self.op.open(r, timeout=300).read().decode('utf-8', 'replace')
                return [z['юрлицо'] for z in C.разобрать(h, '')]
            except Exception as e:  # noqa: BLE001
                п('сбой Цербера', инн, repr(e)[:100]); time.sleep(20 * (попытка + 1)); self.t = 0
        return None


def main():
    import meyer7_inn_poisk as IP
    dd = IP.DaData()
    ц = Цербер()
    вх = [json.loads(s) for s in io.open(ВХ, encoding='utf-8', errors='replace') if s.strip()]
    готово = set()
    if os.path.exists(ВЫХ):
        for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
            try:
                y = json.loads(s)
                if not y.get('повторить'):
                    готово.add((y['юрлицо'], y['рег']))
            except (ValueError, KeyError):
                pass
    п('юрлиц', len(вх), '| уже', len(готово))
    for j, y in enumerate(вх, 1):
        ю, рег = y['юрлицо'], y['рег']
        if (ю, рег) in готово:
            continue
        канд = list(dd.кэш.get(('suggest', ю)) or [])
        if not канд:
            чист = ' '.join(sorted(слова(ю), key=lambda w: ю.lower().find(w)))
            if чист and чист != ю:
                канд = dd.найти('suggest', чист) or []
        # сначала выбранный прошлым прогоном, затем кандидаты своего региона, затем прочие
        канд.sort(key=lambda c: (c.get('инн') != y.get('инн'), not (рег and рег[:6] in (c.get('регион') or '').lower())))
        итог = {'юрлицо': ю, 'рег': рег, 'инн_было': y.get('инн', ''), 'кандидатов': len(канд), 'инн': '', 'как': ''}
        сбой = False
        for c in канд[:7]:
            if not c.get('инн'):
                continue
            имена = ц.по_инн(c['инн'])
            if имена is None:
                сбой = True
                continue
            if any(похоже(ю, и) for и in имена):
                итог.update(инн=c['инн'], как='Цербер подтвердил по ИНН', имя_егрюл=c.get('имя', ''), оквэд=c.get('оквэд', ''))
                break
            time.sleep(1)
        if not итог['инн']:
            итог['как'] = 'кандидатов нет' if not канд else 'ни один кандидат не подтвердился'
            if сбой or (not канд and dd.лимит):
                итог['повторить'] = 1
        C.дописать(ВЫХ, итог)
        if j % 100 == 0:
            п('пройдено', j, 'из', len(вх))
    все = {}
    for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
        y = json.loads(s); все[(y['юрлицо'], y['рег'])] = y
    сч = {'подтверждено': sum(1 for y in все.values() if y['инн']),
          'из них было угадано так же': sum(1 for y in все.values() if y['инн'] and y['инн'] == y['инн_было']),
          'угадано было неверно': sum(1 for y in все.values() if y['инн_было'] and y['инн'] and y['инн'] != y['инн_было']),
          'угаданное не подтвердилось': sum(1 for y in все.values() if y['инн_было'] and not y['инн']),
          'новых (раньше не было)': sum(1 for y in все.values() if y['инн'] and not y['инн_было']),
          'повторить': sum(1 for y in все.values() if y.get('повторить'))}
    shutil.copyfile(ВЫХ, os.path.join(C.ДРОП, os.path.basename(ВЫХ)))
    п('===ИТОГ===', json.dumps(сч, ensure_ascii=False))


if __name__ == '__main__':
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'cerber_inn_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'cerber_inn_proverka.py'), '--vnutri'], cwd=DIR,
                                 creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                                 close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        time.sleep(90)
        print('===ИТОГ===')
        print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог),
                          'хвост': open(лог, encoding='utf-8', errors='replace').read()[-1000:]}, ensure_ascii=False))
        sys.exit(0)
    main()
