# -*- coding: utf-8 -*-
"""Проба 2: безымянные события в news_stream.jsonl (735 шт по пробе 1) и потолок пути 5
(«имя всплывает в более поздней новости про тот же объект»).

ТОЛЬКО ЧТЕНИЕ. Сеть не трогаем, провайдера не зовём, xmlriver не тратим.
Логика матчера здесь — черновик той, что пойдёт в doopredelenie.py: редкие токены
(по df корпуса) + обязательное подтверждение (регион ИЛИ тип объекта).
ВАЖНО: stdout режется СВЕРХУ → итог печатаем ПОСЛЕДНИМ.
"""
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict

JS = r'C:\sender\server\news_stream.jsonl'
DB = r'file:C:\sender\enrich.db?mode=ro'

GEN = set('''завод завода заводе заводы фабрика фабрики цех цеха линия линии комплекс
комплекса производство производства производств предприятие предприятия компания компании
строительство строительства строительству модернизация модернизации запуск запуска
расширение расширения инвестиции инвестиций проект проекта проекты млрд рублей рубля
рублей года году регион региона области область район района город города новый новая
новое новые будет будут может можно объект объекта продукции продукция мощностью выпуск
выпуска работы работ создание создания открытие открытия предприятии заводской'''.split())


def toks(*ss):
    out = []
    for s in ss:
        for t in re.sub(r'[^а-яёa-z0-9 ]', ' ', (s or '').lower()).split():
            if len(t) >= 5 and t not in GEN:
                out.append(t[:9])       # обрезка хвоста = грубая нормализация склонения
    return out


OBJ_CLS = {'зав': ('завод',), 'фаб': ('фабрик',), 'цех': ('цех',), 'лин': ('лини',),
           'ком': ('комплекс',), 'эле': ('элеватор',), 'руд': ('рудник', 'гок', 'карьер'),
           'теп': ('теплиц',), 'фер': ('ферм', 'птицефабрик'), 'тер': ('терминал',)}


def obj_class(txt):
    t = (txt or '').lower()
    return {c for c, ws in OBJ_CLS.items() if any(w in t for w in ws)}


def reg_norm(s):
    s = (s or '').lower()
    s = re.sub(r'(область|обл\.|край|республика|респ\.|округ|район|г\.|город)', ' ', s)
    w = [x[:6] for x in re.sub(r'[^а-яё ]', ' ', s).split() if len(x) >= 4]
    return set(w)


recs = []
for line in open(JS, encoding='utf-8', errors='replace'):
    line = line.strip()
    if not line:
        continue
    try:
        recs.append(json.loads(line))
    except Exception:  # noqa: BLE001
        pass

named = [r for r in recs if (r.get('company') or '').strip()]
anon = [r for r in recs if not (r.get('company') or '').strip()]
print('jsonl всего:', len(recs), 'с именем:', len(named), 'без имени:', len(anon))

# признаки безымянных: есть ли регион, из каких коллекторов, какие темы
anon_reg = sum(1 for r in anon if (r.get('region') or '').strip())
by_col = Counter(r.get('collector') for r in anon)
PAT = {'ОЭЗ/ТОР/резидент': r'\bОЭЗ\b|\bТОР\b|ТОСЭР|особ\w+ экономическ|опережающ\w+ развити|резидент',
       'индустр.парк': r'индустриальн\w+ парк|технопарк|промпарк|промышленн\w+ парк',
       'ФРП/займ/субсидия': r'\bФРП\b|фонд\w* развития промышленности|займ|субсиди',
       'экспертиза/проектн': r'экспертиз|проектн\w+ документац|\bЕГРЗ\b|госэксперт',
       'инвестор/соглашение': r'инвестор|соглашени\w+ о|инвестсоглашени|инвестпроект',
       'сумма названа': r'\d[\d\s.,]*(млн|млрд)'}
pat_c = Counter()
for r in anon:
    t = ' '.join([r.get('title') or '', r.get('what') or ''])
    for k, p in PAT.items():
        if re.search(p, t, re.I):
            pat_c[k] += 1

# ---------- df по корпусу с именами (редкость токена) ----------
df = Counter()
named_toks = []
for r in named:
    ts = set(toks(r.get('title'), r.get('what')))
    named_toks.append(ts)
    df.update(ts)
N = max(1, len(named))

idx = defaultdict(list)          # токен -> индексы именованных записей
for i, ts in enumerate(named_toks):
    for t in ts:
        if df[t] <= max(3, N // 50):      # редкий: не чаще чем у 2% корпуса
            idx[t].append(i)


def date_of(r):
    p = (r.get('published') or '')[:30]
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', p)
    if m:
        return m.group(0)
    m = re.search(r'(\d{2}) (\w{3}) (\d{4})', p)
    if m:
        mm = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
              'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
        return '%s-%s-%s' % (m.group(3), mm.get(m.group(2), '01'), m.group(1))
    return ''


hit_any = hit_conf = 0
pairs = []
for r in anon:
    ats = set(toks(r.get('title'), r.get('what')))
    rare = {t for t in ats if df.get(t, 0) <= max(3, N // 50)}
    cand = Counter()
    for t in rare:
        for i in idx.get(t, ()):
            cand[i] += 1
    if not cand:
        continue
    hit_any += 1
    areg = reg_norm(r.get('region'))
    acls = obj_class(' '.join([r.get('title') or '', r.get('what') or '']))
    best = None
    for i, n in cand.most_common(12):
        nr = named[i]
        shared = sorted(rare & named_toks[i])
        nreg = reg_norm(nr.get('region') or nr.get('dd_region'))
        ncls = obj_class(' '.join([nr.get('title') or '', nr.get('what') or '']))
        reg_ok = bool(areg and nreg and (areg & nreg))
        cls_ok = bool(acls and ncls and (acls & ncls))
        # подтверждение: >=2 редких токена И (регион ИЛИ класс объекта)
        if n >= 2 and (reg_ok or cls_ok):
            best = (n, shared, nr, reg_ok, cls_ok)
            break
    if best:
        hit_conf += 1
        n, shared, nr, reg_ok, cls_ok = best
        pairs.append({'anon': (r.get('title') or '')[:95], 'anon_reg': r.get('region') or '',
                      'anon_d': date_of(r),
                      'name': nr.get('company'), 'inn': nr.get('inn') or '',
                      'named': (nr.get('title') or '')[:95],
                      'named_d': date_of(nr), 'shared': shared[:4],
                      'reg_ok': reg_ok, 'cls_ok': cls_ok})

later = sum(1 for p in pairs if p['named_d'] and p['anon_d'] and p['named_d'] > p['anon_d'])
nodate = sum(1 for p in pairs if not (p['named_d'] and p['anon_d']))

# сколько безымянных вообще имеет редкие токены (потолок любого текстового матчинга)
cx = sqlite3.connect(DB, uri=True)
sig_urls = {u for (u,) in cx.execute('SELECT DISTINCT source_url FROM signals') if u}

print()
print('==================== ИТОГ (главное) ====================')
print('безымянных событий (is_capex=true, company пусто):', len(anon),
      '| из них с регионом:', anon_reg)
print('коллекторы безымянных:', dict(by_col.most_common(8)))
print('темы в безымянных:', dict(pat_c))
print('ПУТЬ 5 (наш корпус): хоть один кандидат по редким токенам:', hit_any,
      '(%.0f%%)' % (100.0 * hit_any / max(1, len(anon))))
print('ПУТЬ 5 с подтверждением (>=2 редких токена И регион/класс объекта):', hit_conf,
      '(%.0f%%)' % (100.0 * hit_conf / max(1, len(anon))))
print('   из них именованная новость ПОЗЖЕ безымянной:', later, '| без дат:', nodate)
print('уникальных source_url в signals:', len(sig_urls))
print('--- 12 пар для глазной проверки (безымянное -> предполагаемое имя) ---')
for p in pairs[:12]:
    print('  A: %s [%s %s]' % (p['anon'], p['anon_reg'], p['anon_d']))
    print('  B: %s | %s [%s] общие=%s reg=%s cls=%s' % (
        p['name'], p['named'], p['named_d'], p['shared'], p['reg_ok'], p['cls_ok']))
