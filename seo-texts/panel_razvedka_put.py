# -*- coding: utf-8 -*-
"""Разведка под перенос копии на путь Мейера: откуда берётся базовый путь и чем публикуется.

Нужно ответить на три вопроса, не угадывая:
  1) задаётся ли префикс панели переменной окружения (тогда перенос это одна строка);
  2) сколько в коде и шаблонах строк «/centro» и сколько из них ЖЁСТКИЕ (с «/obzvon»),
     потому что жёсткие переименование не поймает и они уедут на боевую панель;
  3) чем сайт публикуется наружу и как именно проксируется /obzvon.

Большой вывод кладу в файл на дроп, в stdout печатаю только сводку: stdout_tail обрезает
начало, и на этом я уже дважды выбирала не ту базу по обрезанному выводу.
"""
import io
import os
import re
import subprocess

OTCHET = r'C:\seostat\drop\drop-storage\razvedka-put-meyer.txt'
KOREN = r'C:\centro2'
BOEVOY = r'C:\seostat'
vyhod = []
svodka = []


def pishi(s=''):
    vyhod.append(str(s))


def svodno(s):
    svodka.append(str(s))
    vyhod.append(str(s))


# ---------------------------------------------------------------- 1. настройки префикса
pishi('########## ГДЕ ЗАДАЁТСЯ obzvon_path')
kand = []
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d]
    for f in fajly:
        if not f.endswith('.py'):
            continue
        p = os.path.join(kor, f)
        t = io.open(p, encoding='utf-8', errors='replace').read()
        if 'obzvon_path' in t:
            kand.append((p, t))
for p, t in kand:
    pishi('--- %s' % p)
    for i, l in enumerate(t.splitlines(), 1):
        if 'obzvon_path' in l:
            pishi('   %4d: %s' % (i, l.strip()[:160]))
svodno('файлов с obzvon_path: %d' % len(kand))

# объявление поля настроек: ищем, читается ли оно из окружения
for p, t in kand:
    m = re.search(r'obzvon_path\s*:\s*str\s*=\s*([^\n]+)', t)
    if m:
        svodno('объявление: obzvon_path: str = %s  (в %s)'
               % (m.group(1).strip()[:80], os.path.basename(p)))
    if 'BaseSettings' in t or 'env_prefix' in t or 'SettingsConfigDict' in t:
        for l in t.splitlines():
            if 'env_prefix' in l or 'env_file' in l or 'SettingsConfigDict' in l:
                pishi('   настройки pydantic: %s' % l.strip()[:160])
                svodno('pydantic: %s' % l.strip()[:120])

# ---------------------------------------------------------------- 2. сколько «/centro»
pishi()
pishi('########## СТРОКИ «/centro» В КОПИИ')
myagkie = zhestkie = 0
podrobno = {}
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for f in fajly:
        if not f.endswith(('.py', '.html', '.js', '.css')):
            continue
        p = os.path.join(kor, f)
        t = io.open(p, encoding='utf-8', errors='replace').read()
        zh = len(re.findall(r'/obzvon/centro', t))
        vse = len(re.findall(r'/centro\b', t))
        if vse:
            podrobno[os.path.relpath(p, KOREN)] = (vse, zh)
            myagkie += vse - zh
            zhestkie += zh
for k in sorted(podrobno):
    vse, zh = podrobno[k]
    pishi('   %-44s всего %4d, жёстких с /obzvon %d' % (k, vse, zh))
svodno('строк «/centro»: всего %d, из них жёстких «/obzvon/centro»: %d'
       % (myagkie + zhestkie, zhestkie))

# где именно жёсткие — их переименование не поймает
pishi()
pishi('--- жёсткие вхождения /obzvon/centro построчно')
nashli = 0
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for f in fajly:
        if not f.endswith(('.py', '.html', '.js', '.css')):
            continue
        p = os.path.join(kor, f)
        for i, l in enumerate(io.open(p, encoding='utf-8', errors='replace'), 1):
            if '/obzvon/centro' in l:
                nashli += 1
                pishi('   %s:%d  %s' % (os.path.relpath(p, KOREN), i, l.strip()[:150]))
pishi('   итого жёстких строк: %d' % nashli)

# ---------------------------------------------------------------- 3. чем публикуется сайт
pishi()
pishi('########## ЧТО СЛУШАЕТ 80 И 443')
r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=120)
tekst = r.stdout.decode('cp866', 'replace')
pidy = {}
for l in tekst.splitlines():
    u = l.upper()
    if 'LISTENING' not in u:
        continue
    m = re.search(r':(80|443|8011|8012|8014|8016)\s', l)
    if m:
        pidy.setdefault(m.group(1), set()).add(l.split()[-1])
        pishi('   %s' % l.strip())
svodno('порт 80: PID %s, порт 443: PID %s'
       % (','.join(sorted(pidy.get('80', {'нет'}))),
          ','.join(sorted(pidy.get('443', {'нет'})))))

pishi()
pishi('--- чьи это процессы')
r = subprocess.run(['tasklist', '/FO', 'CSV'], capture_output=True, timeout=120)
spisok = r.stdout.decode('cp866', 'replace').splitlines()
nuzhnye = set()
for nabor in pidy.values():
    nuzhnye |= nabor
for l in spisok:
    ch = [x.strip('"') for x in l.split('","')]
    if len(ch) > 1 and ch[1] in nuzhnye:
        pishi('   PID %-8s %s' % (ch[1], ch[0]))
        svodno('PID %s = %s' % (ch[1], ch[0]))

# ---------------------------------------------------------------- 4. конфиг прокси
pishi()
pishi('########## КОНФИГИ ОБРАТНОГО ПРОКСИ')
kandidaty = []
for baza in (r'C:\nginx', r'C:\Program Files\nginx', r'C:\seostat',
             r'C:\caddy', r'C:\Users\Administrator', r'C:\inetpub\wwwroot'):
    if not os.path.isdir(baza):
        continue
    for kor, kat, fajly in os.walk(baza):
        if kor.count(os.sep) - baza.count(os.sep) > 3:
            kat[:] = []
            continue
        kat[:] = [d for d in kat
                  if d.lower() not in ('.git', 'node_modules', '__pycache__', 'logs',
                                       '.venv', 'drop-storage', 'dokaz')]
        for f in fajly:
            if f.lower() in ('nginx.conf', 'caddyfile', 'web.config') \
                    or f.lower().endswith('.conf'):
                kandidaty.append(os.path.join(kor, f))
for p in kandidaty[:25]:
    try:
        t = io.open(p, encoding='utf-8', errors='replace').read()
    except OSError:
        continue
    if 'obzvon' in t or 'proxy_pass' in t or '8012' in t:
        pishi('--- %s (%d знаков)' % (p, len(t)))
        for i, l in enumerate(t.splitlines(), 1):
            if re.search(r'server_name|listen|location|proxy_pass|obzvon|8012|8016|include',
                         l, re.I):
                pishi('   %4d: %s' % (i, l.strip()[:170]))
svodno('конфигов-кандидатов найдено: %d' % len(kandidaty))

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('полный отчёт: %s (%d строк)' % (OTCHET, len(vyhod)))
print('\n===== СВОДКА =====')
for s in svodka:
    print(s)
