# -*- coding: utf-8 -*-
# 18.10, владелец: «я видел сайт в декларациях» — сайт есть в контактах карточки (idContactType 5), но заполнен ~1%.
# Повторный проход по карточкам fsa-meyer-kontakty.jsonl: сайт + почты/телефоны ТОЛЬКО из блоков applicant/manufacturer
# (прежний сбор регэкспом по всему JSON цеплял почты органа сертификации/лаборатории). Типы: 1,3 телефон; 4 почта; 5 сайт.
# Durable: fsa-meyer-kontakty2.jsonl (fsync, резюм по инн) + дроп. 2 потока (6 давали 429). Лог: fsa_meyer_sayty_*.log.
import io, json, os, re, shutil, sys, threading, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender')
import fsa_pilot_orehi as F  # noqa: E402
ВХ = os.path.join(DIR, 'fsa-meyer-kontakty.jsonl')
ВЫХ = os.path.join(DIR, 'fsa-meyer-kontakty2.jsonl')
ДРОП = r'C:\seostat\drop\drop-storage'
ПОТОКОВ = int(os.environ.get('FSA_POTOKOV', '2'))
_лок = threading.Lock()


def п(*a):
    print(time.strftime('%d.%m %H:%M:%S'), *a, flush=True)


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


def дописать(x):
    with _лок:
        with io.open(ВЫХ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(x, ensure_ascii=False) + '\n')
            f.flush(); os.fsync(f.fileno())


def разобрать(d):
    с, п_, т = set(), set(), set()
    for блок in ('applicant', 'manufacturer'):
        for c in (d.get(блок) or {}).get('contacts') or []:
            v, тип = str(c.get('value') or '').strip(), c.get('idContactType')
            if not v:
                continue
            if тип == 5:
                с.add(v.lower().rstrip('/'))
            elif тип == 4 and '@' in v:
                п_.add(v.lower())
            elif тип in (1, 3):
                н = re.sub(r'[^\d+]', '', v)
                if len(re.sub(r'\D', '', н)) >= 10:
                    т.add(н)
    return sorted(с)[:4], sorted(п_)[:6], sorted(т)[:6]


def поток(очередь, всего):
    H2, t = F.вход(), time.time()
    while True:
        with _лок:
            if not очередь:
                return
            x = очередь.pop()
            ост = len(очередь)
        if time.time() - t > 1200:
            H2, t = F.вход(), time.time()
        d = None
        for попытка in range(3):
            d = F.запрос(H2, '/api/v1/rds/common/declarations/%s' % x['id'])
            if d is not None:
                break
            time.sleep(30 * (попытка + 1))
            H2, t = F.вход(), time.time()
        if d is None:
            дописать({'инн': x['инн'], 'id': x['id'], 'ошибка': 1})
            continue
        с, пч, тл = разобрать(d)
        дописать({'инн': x['инн'], 'id': x['id'], 'сайты': с, 'почты': пч, 'телефоны': тл})
        if ост % 1000 == 0:
            п('осталось', ост, 'из', всего)
        time.sleep(0.3)


def main():
    t0 = time.time()
    готово = {y['инн'] for y in читать(ВЫХ) if y.get('инн') and not y.get('ошибка')}
    очередь = [x for x in читать(ВХ) if x.get('инн') and x.get('id') and x['инн'] not in готово]
    п('карточек к проходу', len(очередь), '| уже', len(готово))
    всего = len(очередь)
    тт = [threading.Thread(target=поток, args=(очередь, всего)) for _ in range(ПОТОКОВ)]
    for т in тт:
        т.start()
    for т in тт:
        т.join()
    все = {y['инн']: y for y in читать(ВЫХ) if not y.get('ошибка')}
    shutil.copyfile(ВЫХ, os.path.join(ДРОП, os.path.basename(ВЫХ)))
    п('===ИТОГ===', json.dumps({'карточек': len(все), 'с_сайтом': sum(1 for y in все.values() if y.get('сайты')),
                                'с_почтой': sum(1 for y in все.values() if y.get('почты'))}, ensure_ascii=False),
      'за %.1f ч' % ((time.time() - t0) / 3600))


if __name__ == '__main__':
    os.chdir(DIR)
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'fsa_meyer_sayty_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'fsa_meyer_sayty.py'), '--vnutri'], cwd=DIR,
                                 creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                                 close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        time.sleep(90)
        print('===ИТОГ===')
        print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог),
                          'хвост': open(лог, encoding='utf-8', errors='replace').read()[-1000:]}, ensure_ascii=False))
        sys.exit(0)
    main()
