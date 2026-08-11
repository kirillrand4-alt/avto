# -*- coding: utf-8 -*-
"""Принять ВСЁ, что выложили соседи, и запомнить, что уже принято.

Владелец спросил «влил в базу всё от соседей?» — пошёл смотреть в файлы, а не в память, и
ответ оказался «нет». Сверка журнала вливаний со списком дропа показала пропуски:

    PARK-EIS-TIK14-PODTV-3S.jsonl ..... пропущен (есть TIK13 и TIK15, между ними дыра)
    PARK-EIS-TIK21-PODTV-3S.jsonl ..... не вливался
    PARK-EIS-TIK22-PODTV-3S.jsonl ..... не вливался
    PARK-RTS-PODTV-3S.jsonl ........... не вливался
    PARK-TEKTORG-ZAKUPKI-3S.jsonl ..... не вливался
    PARK-PLOSHCHADKI-DLYA-PARKA-3S.jsonl не вливался
    PARK-ROSELTORG / park_ingest_3d ... выложены заново, дельта не взята

Причина не в лени, а в способе: я вливал руками тот файл, о котором сосед написала в своём
последнем письме. Файлы, выложенные молча или между письмами, мимо меня проходили. И
проверить «а всё ли принято» было нечем — журнал вливаний писал имя `_potok.jsonl`, потому
что я копировал поток под рабочее имя. Своё же имя источника я и стёр.

Здесь это чинится:

  * реестр `prinyatye_potoki(imya, sha256, strok, prinyato, ts)` в самой park.db — серверная
    durable-память, переживает рестарт песочницы;
  * каждый файл сверяется с реестром ПО СОДЕРЖИМОМУ (sha256), а не по имени: сосед
    перевыкладывает файл под тем же именем, дописав строки;
  * если файл уже принимался — вливается только ДЕЛЬТА (строки, которых не было);
  * имя источника пишется в журнал вливаний как есть, без `_potok.jsonl`.

Запуск: python3 park_1s_prinyat_vsyo.py [--pisat]
"""
import hashlib, json, os, re, subprocess, sqlite3, sys, time

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
KLIENT = '/home/user/avto/seo-texts/server/drop_client.sh'
# что считаем потоком для парка: подтверждённые срезы и сборы площадок
BERYOM = re.compile(r'^(PARK-EIS-TIK\d+-PODTV|PARK-RTS-PODTV|PARK-TEKTORG-ZAKUPKI|'
                    r'PARK-ROSELTORG-ZAKUPKI|PARK-PLOSHCHADKI-DLYA-PARKA|park_ingest_)', re.I)


def spisok_dropa():
    s = subprocess.run(['bash', KLIENT, 'list'], capture_output=True, text=True, timeout=120).stdout
    d = json.loads(s)
    f = d['files'] if isinstance(d, dict) and 'files' in d else d
    return sorted([x for x in f if x.get('name', '').endswith('.jsonl')
                   and BERYOM.match(x['name'])], key=lambda x: int(x.get('mtime', 0)))


p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
c.execute("""create table if not exists prinyatye_potoki(
    imya text, sha256 text, strok integer, prinyato integer, ts text,
    primary key(imya, sha256))""")
p.commit()

fayly = spisok_dropa()
uzhe = {(r[0], r[1]) for r in c.execute('select imya, sha256 from prinyatye_potoki')}
print('потоков на дропе: %d' % len(fayly))
print('в реестре принятых: %d' % len(uzhe))
print()
rabota = []
for x in fayly:
    imya = x['name']
    put = os.path.join(D, imya)
    if not os.path.exists(put) or os.path.getsize(put) != int(x.get('bytes', 0)):
        subprocess.run(['bash', KLIENT, 'down', imya], capture_output=True, timeout=600, cwd=D)
    if not os.path.exists(put):
        print('  %-42s НЕ СКАЧАЛСЯ' % imya[:42])
        continue
    sha = hashlib.sha256(open(put, 'rb').read()).hexdigest()
    if (imya, sha) in uzhe:
        continue
    # дельта: строки, которых не было ни в одной прежней версии этого файла
    bylo = set()
    for (staryy_sha,) in c.execute('select sha256 from prinyatye_potoki where imya=?', (imya,)):
        arh = os.path.join(D, '_arhiv_%s_%s' % (staryy_sha[:12], imya))
        if os.path.exists(arh):
            bylo |= set(open(arh, encoding='utf-8', errors='replace'))
    stroki = open(put, encoding='utf-8', errors='replace').readlines()
    delta = [l for l in stroki if l not in bylo] if bylo else stroki
    rabota.append((imya, sha, put, stroki, delta))
    print('  %-42s строк %-6d к вливанию %d' % (imya[:42], len(stroki), len(delta)))

print()
print('файлов к вливанию: %d, строк всего: %d'
      % (len(rabota), sum(len(r[4]) for r in rabota)))
if not PISAT:
    print('сухой прогон; вливать — с ключом --pisat')
    p.close()
    raise SystemExit
p.close()

itog = []
for imya, sha, put, stroki, delta in rabota:
    vhod = os.path.join(D, '_potok.jsonl')
    with open(vhod, 'w', encoding='utf-8') as f:
        f.writelines(delta)
    r = subprocess.run([sys.executable, os.path.join(D, 'park_vlit_3s_potok.py'), vhod],
                       capture_output=True, text=True, cwd=D, timeout=3600)
    hvost = (r.stdout or '') + (r.stderr or '')
    m = re.search(r'принято (\d+)', hvost)
    nov = re.search(r'новых для парка (\d+)', hvost)
    prinyato = int(m.group(1)) if m else 0
    itog.append((imya, len(delta), prinyato, int(nov.group(1)) if nov else 0))
    print('%-42s влито %-6d из %-6d новых предприятий %s'
          % (imya[:42], prinyato, len(delta), nov.group(1) if nov else '?'))
    # запоминаем СОДЕРЖИМОЕ этой версии, чтобы в следующий раз взять только дельту
    import shutil
    shutil.copyfile(put, os.path.join(D, '_arhiv_%s_%s' % (sha[:12], imya)))
    pp = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
    cc = pp.cursor()
    cc.execute('insert or replace into prinyatye_potoki values (?,?,?,?,?)',
               (imya, sha, len(stroki), prinyato, time.strftime('%Y-%m-%d %H:%M:%S')))
    cc.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
               (time.strftime('%Y-%m-%d %H:%M:%S'), 'ПОТОК СОСЕДА: ' + imya,
                len(delta), prinyato, len(delta) - prinyato, 'реестр prinyatye_potoki, дельта по sha256'))
    pp.commit()
    pp.close()

print()
print('=== ИТОГ')
print('файлов принято ..... %d' % len(itog))
print('строк влито ........ %d из %d' % (sum(i[2] for i in itog), sum(i[1] for i in itog)))
print('новых предприятий .. %d' % sum(i[3] for i in itog))
p = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park.db'), uri=True)
q = lambda s: p.execute(s).fetchone()[0]
print()
print('БАЗА: фактов %d | в парке %d | предприятий %d | ссылок %d'
      % (q('select count(*) from fakt'), q('select count(*) from fakt where v_parke=1'),
         q('select count(distinct inn) from fakt where v_parke=1'),
         q('select count(*) from fakt_ssylka')))
p.close()
