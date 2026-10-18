# -*- coding: utf-8 -*-
# 18.10, владелец: ФСА — DaData по ИНН (статус, регион, ОКВЭД, руководитель) для изготовителей после отсева: сначала юрлица
# (по числу деклараций), потом ИП. Лимит DaData 10 тыс./сутки (общий с news-scan) — упёрлись: ждём следующих суток и дальше.
# Кэш DaData (meyer7-inn-dadata.jsonl) — общий, резюм по нему. Итог: fsa-meyer-dadata.jsonl (fsync) + дроп.
import io, json, os, sys, time, datetime
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender'); os.chdir(DIR)
ВЫХ = os.path.join(DIR, 'fsa-meyer-dadata.jsonl')


def main():
    import meyer7_inn_poisk as P
    отсев = {}
    for s in io.open('fsa-meyer-otsev.jsonl', encoding='utf-8', errors='replace'):
        try:
            y = json.loads(s); отсев[y['инн']] = y.get('ответ')
        except (ValueError, KeyError):
            pass
    изг = [json.loads(s) for s in io.open('fsa-meyer-izg.jsonl', encoding='utf-8', errors='replace') if s.strip()]
    изг = [z for z in изг if отсев.get(z['инн']) != 'нет']
    изг.sort(key=lambda z: (len(z['инн']) != 10, -z['деклараций']))
    готово = set()
    if os.path.exists(ВЫХ):
        for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
            try: готово.add(json.loads(s)['инн'])
            except (ValueError, KeyError): pass
    очередь = [z['инн'] for z in изг if z['инн'] not in готово]
    print('к запросу', len(очередь), '| уже', len(готово), flush=True)
    while очередь:
        dd = P.DaData()
        n = 0
        while очередь and not dd.лимит:
            i = очередь[0]
            к = dd.найти('id', i)
            if к is None:
                break
            c = (к or [{}])[0]
            with io.open(ВЫХ, 'a', encoding='utf-8') as f:
                f.write(json.dumps({'инн': i, 'статус': c.get('статус', ''), 'имя': c.get('имя', ''), 'регион': c.get('регион', ''),
                                    'город': c.get('город', ''), 'оквэд': c.get('оквэд', ''), 'руководитель': c.get('руководитель', ''),
                                    'должность': c.get('должность', '')}, ensure_ascii=False) + '\n')
                f.flush(); os.fsync(f.fileno())
            очередь.pop(0); n += 1
            if n % 500 == 0:
                print(time.strftime('%d.%m %H:%M'), 'сделано', n, 'осталось', len(очередь), flush=True)
        import shutil
        shutil.copyfile(ВЫХ, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХ)))
        if not очередь:
            break
        завтра = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time(0, 10))
        print(time.strftime('%d.%m %H:%M'), 'лимит DaData; ждём до', завтра, '| осталось', len(очередь), flush=True)
        time.sleep(max(60, (завтра - datetime.datetime.now()).total_seconds()))
    print('===ИТОГ=== готово', flush=True)


if __name__ == '__main__':
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'fsa_dadata_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'fsa_meyer_dadata.py'), '--vnutri'], cwd=DIR,
                                 creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                                 close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        time.sleep(60)
        print('===ИТОГ==='); print(open(лог, encoding='utf-8', errors='replace').read()[-500:])
        sys.exit(0)
    main()
