# -*- coding: utf-8 -*-
"""Проба 4: (а) ужесточение матчера пути 5 «общий токен должен быть в сути события»,
(б) сколько безымянных дают РАЗБИРАЕМУЮ площадку ОЭЗ/ТОР (потолок пути 1),
(в) сколько безымянных дают составимый запрос «объект+район+отрасль» (потолок пути 6).

ТОЛЬКО ЧТЕНИЕ, сеть не трогаем. Итог печатаем ПОСЛЕДНИМ.
"""
import json
import re
from collections import Counter, defaultdict

JS = r'C:\sender\server\news_stream.jsonl'

GEN = set('''завод завода заводе заводы заводов фабрика фабрики цех цеха линия линии
комплекс комплекса производство производства производств производству предприятие
предприятия предприятий компания компании строительство строительства строительству
строить построят построит построили построено модернизация модернизации запуск запуска
запустят открылся открыли расширение расширения инвестиции инвестиций инвестор инвестора
проект проекта проекты млрд рублей рубля миллиард миллионов года году региона регион
области область округ округа район района города город новый новая новое новые будет
будут может можно объект объекта объектов продукции продукция мощностью выпуск выпуска
выпуску работы работ создание создания открытие открытия начали начал планируют планирует
хотят готов готовится обсудили встрече рамках вложит вложат составит более около первый
второй крупнейший новости новостной официальн газета деловая онлайн online news агентство
сообщает сообщил рассказал глава губернатор губернатора министр правительство'''.split())

OBJ_CLS = {'зав': ('завод',), 'фаб': ('фабрик',), 'цех': ('цех',), 'лин': ('лини',),
           'ком': ('комплекс',), 'эле': ('элеватор',), 'руд': ('рудник', 'гок', 'карьер'),
           'теп': ('теплиц',), 'фер': ('ферм', 'птицефабрик'), 'тер': ('терминал',),
           'скл': ('склад', 'логистическ')}


def strip_publisher(title):
    t = title or ''
    for sep in (' - ', ' — ', ' | ', ' :: ', ' // '):
        if sep in t:
            t = t.rsplit(sep, 1)[0]
    return t


def toks(*ss):
    out = []
    for s in ss:
        for t in re.sub(r'[^а-яёa-z0-9 ]', ' ', (s or '').lower()).split():
            if len(t) >= 5 and t not in GEN:
                out.append(t[:9])
    return out


def rec_tokens(r):
    return set(toks(strip_publisher(r.get('title')), r.get('what'))) - set(
        toks(r.get('source_name'), r.get('collector')))


def what_tokens(r):
    return set(toks(r.get('what')))


def obj_class(txt):
    t = (txt or '').lower()
    return {c for c, ws in OBJ_CLS.items() if any(w in t for w in ws)}


def reg_norm(s):
    s = (s or '').lower()
    s = re.sub(r'(область|обл\.|край|республика|респ\.|округ|район|г\.|город)', ' ', s)
    return {x[:6] for x in re.sub(r'[^а-яё ]', ' ', s).split() if len(x) >= 4}


recs = []
for line in open(JS, encoding='utf-8', errors='replace'):
    line = line.strip()
    if line:
        try:
            recs.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
named = [r for r in recs if (r.get('company') or '').strip()]
anon = [r for r in recs if not (r.get('company') or '').strip()]
NT = [rec_tokens(r) for r in named]
NW = [what_tokens(r) for r in named]
NC = [obj_class(strip_publisher(r.get('title')) + ' ' + (r.get('what') or '')) for r in named]
NR = [reg_norm(r.get('region') or r.get('dd_region')) for r in named]

df = Counter()
for ts in NT:
    df.update(ts)
RARE = 3
idx = defaultdict(list)
for i, ts in enumerate(NT):
    for t in ts:
        if df[t] <= RARE:
            idx[t].append(i)


def norm_name(s):
    return re.sub(r'[^а-яёa-z0-9]', '', (s or '').lower())[:14]


def match(q_toks, q_what, q_reg, q_cls, skip=None, need_what=True):
    rare = {t for t in q_toks if df.get(t, 0) <= RARE}
    if len(rare) < 2:
        return None
    cand = Counter()
    for t in rare:
        for i in idx.get(t, ()):
            if i != skip:
                cand[i] += 1
    for i, n in cand.most_common(15):
        if n < 2:
            break
        if not (q_reg and NR[i] and (q_reg & NR[i])):
            continue
        if not (q_cls and NC[i] and (q_cls & NC[i])):
            continue
        shared = rare & NT[i]
        # УЖЕСТОЧЕНИЕ: хотя бы один общий токен должен сидеть в СУТИ события
        # (поле what классификатора) с обеих сторон, а не только в шапке/подписи —
        # иначе матч ловит фамилию журналиста и имя издания (проба 3: «gorobzor
        # наталья оглоблина»).
        if need_what and not (shared & NW[i] & q_what):
            continue
        return i, sorted(shared)
    return None


step = max(1, len(named) // 1200)
sample = list(range(0, len(named), step))
res = {}
for label, need_what in (('без ужесточения', False), ('с ужесточением (what)', True)):
    got = right = dup = right_nodup = got_nodup = 0
    for i in sample:
        r = named[i]
        m = match(NT[i], NW[i], NR[i], NC[i], skip=i, need_what=need_what)
        if not m:
            continue
        j, shared = m
        got += 1
        a = strip_publisher(r.get('title')).lower()[:60]
        b = strip_publisher(named[j].get('title')).lower()[:60]
        is_dup = a == b
        ok = (r.get('inn') and r.get('inn') == named[j].get('inn')) or \
             (norm_name(r.get('company')) and
              norm_name(r.get('company')) == norm_name(named[j].get('company')))
        if is_dup:
            dup += 1
        else:
            got_nodup += 1
            right_nodup += 1 if ok else 0
        right += 1 if ok else 0
    res[label] = (got, right, dup, got_nodup, right_nodup)

anon_hits = [0, 0]
for r in anon:
    t, w = rec_tokens(r), what_tokens(r)
    rg = reg_norm(r.get('region'))
    cl = obj_class(strip_publisher(r.get('title')) + ' ' + (r.get('what') or ''))
    if match(t, w, rg, cl, need_what=False):
        anon_hits[0] += 1
    if match(t, w, rg, cl, need_what=True):
        anon_hits[1] += 1

# ---------- (б) площадка ОЭЗ/ТОР ----------
SITE = re.compile(r'(?:ОЭЗ|ТОР|ТОСЭР|особ\w+ экономическ\w+ зон\w*|территори\w+ опережающ\w+'
                  r'\s+развити\w*)[\s«"\']*([А-ЯЁ][А-Яа-яЁё\- ]{2,30})?', re.I)
oez_mention = oez_site = 0
oez_samples = []
for r in anon:
    txt = ' '.join([strip_publisher(r.get('title')) or '', r.get('what') or '',
                    r.get('region') or ''])
    if re.search(r'\bОЭЗ\b|\bТОР\b|ТОСЭР|особ\w+ экономическ|опережающ\w+ развити|резидент',
                 txt, re.I):
        oez_mention += 1
        m = SITE.search(txt)
        nm = (m.group(1) or '').strip(' «"\'-') if m else ''
        if nm and len(nm) >= 3:
            oez_site += 1
            if len(oez_samples) < 8:
                oez_samples.append((nm[:30], (r.get('region') or '')[:24],
                                    strip_publisher(r.get('title'))[:60]))

# ---------- (в) составим ли запрос «объект + район + отрасль» ----------
q_ok = 0
for r in anon:
    rg = (r.get('region') or '').strip()
    cl = obj_class(strip_publisher(r.get('title')) + ' ' + (r.get('what') or ''))
    subj = [t for t in rec_tokens(r) if df.get(t, 0) <= 10 and len(t) >= 6]
    if rg and cl and subj:
        q_ok += 1

print()
print('==================== ИТОГ (главное) ====================')
print('корпус: %d, с именем %d, без имени %d; проверено на отложенной выборке: %d'
      % (len(recs), len(named), len(anon), len(sample)))
for k, (got, right, dup, gnd, rnd) in res.items():
    print('%s: ответов %d (охват %.1f%%), верных %d (точность %.0f%%); '
          'без дублей заголовка: %d ответов, %d верных (точность %.0f%%, охват %.1f%%)'
          % (k, got, 100.0 * got / len(sample), right, 100.0 * right / max(1, got),
             gnd, rnd, 100.0 * rnd / max(1, gnd), 100.0 * gnd / len(sample)))
print('безымянных: %d; матч без ужесточения %d (%.1f%%), с ужесточением %d (%.1f%%)'
      % (len(anon), anon_hits[0], 100.0 * anon_hits[0] / len(anon),
         anon_hits[1], 100.0 * anon_hits[1] / len(anon)))
print('ПУТЬ 1: упоминают ОЭЗ/ТОР/резидентство %d (%.1f%%), из них ИМЯ ПЛОЩАДКИ разбирается %d (%.1f%% от всех безымянных)'
      % (oez_mention, 100.0 * oez_mention / len(anon), oez_site, 100.0 * oez_site / len(anon)))
print('ПУТЬ 6: запрос «объект+район+отрасль» составим у %d (%.0f%%)'
      % (q_ok, 100.0 * q_ok / len(anon)))
print('--- площадки ОЭЗ/ТОР, что разобралось ---')
for s in oez_samples:
    print('  площадка=%s регион=%s | %s' % s)
