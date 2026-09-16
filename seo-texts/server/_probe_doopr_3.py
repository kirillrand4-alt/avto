# -*- coding: utf-8 -*-
"""Проба 3: СТРОГИЙ матчер пути 5 + честная проверка на отложенной выборке.

Проба 2 показала: наивный матч по редким токенам даёт 57% «попаданий», но глазами
видно, что общие токены — это имя ИЗДАНИЯ («деловая газета», «сибирский новостной»,
«rugrad online») и общие глаголы. Поэтому здесь:
  * с заголовка срезается хвост издания (' - ', ' | ', ' :: ');
  * токены источника (source_name) выкидываются;
  * регион и тип объекта — ОБЯЗАТЕЛЬНОЕ подтверждение (И, а не ИЛИ);
  * нужен якорь — редкий предметный токен (df<=3), не глагол-штамп.

Честная проверка: берём записи С ИМЕНЕМ, ПРЯЧЕМ имя, ищем матчером по остальному
корпусу и сравниваем найденное имя с настоящим. Это даёт измеримые точность и охват
пути 5 на реальных данных, а не на глаз.

ТОЛЬКО ЧТЕНИЕ. Сеть/провайдер/xmlriver не трогаются.
ВАЖНО: stdout режется СВЕРХУ → итог печатаем ПОСЛЕДНИМ.
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
    """Срезать хвост издания: «...завод построят - Деловая Газета.Юг» → «...завод построят»."""
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
    src = set(toks(r.get('source_name'), r.get('collector')))
    t = set(toks(strip_publisher(r.get('title')), r.get('what')))
    return t - src


def obj_class(txt):
    t = (txt or '').lower()
    return {c for c, ws in OBJ_CLS.items() if any(w in t for w in ws)}


def reg_norm(s):
    s = (s or '').lower()
    s = re.sub(r'(область|обл\.|край|республика|респ\.|округ|район|г\.|город)', ' ', s)
    return {x[:6] for x in re.sub(r'[^а-яё ]', ' ', s).split() if len(x) >= 4}


def date_of(r):
    p = (r.get('published') or '')[:40]
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', p)
    if m:
        return m.group(0)
    m = re.search(r'(\d{1,2}) (\w{3}) (\d{4})', p)
    if m:
        mm = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
              'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
        return '%s-%s-%02d' % (m.group(3), mm.get(m.group(2), '01'), int(m.group(1)))
    return ''


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
NT = [rec_tokens(r) for r in named]
NC = [obj_class(strip_publisher(r.get('title')) + ' ' + (r.get('what') or '')) for r in named]
NR = [reg_norm(r.get('region') or r.get('dd_region')) for r in named]
ND = [date_of(r) for r in named]

df = Counter()
for ts in NT:
    df.update(ts)
RARE = 3                       # «редкий» = встретился не более чем в 3 записях корпуса
idx = defaultdict(list)
for i, ts in enumerate(NT):
    for t in ts:
        if df[t] <= RARE:
            idx[t].append(i)


def norm_name(s):
    return re.sub(r'[^а-яёa-z0-9]', '', (s or '').lower())[:14]


def match(q_toks, q_reg, q_cls, q_date, skip=None, need_later=False):
    """Строгий матч: >=2 редких предметных токена И регион И класс объекта.
    Возвращает (индекс, общие токены) или None."""
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
        if need_later and q_date and ND[i] and ND[i] < q_date:
            continue
        return i, sorted(rare & NT[i])
    return None


# ---------- честная проверка на отложенной выборке (имя прячем) ----------
step = max(1, len(named) // 1200)
sample = list(range(0, len(named), step))
got = right = dup_title = right_nodup = 0
wrong_ex = []
for i in sample:
    r = named[i]
    m = match(NT[i], NR[i], NC[i], ND[i], skip=i)
    if not m:
        continue
    j, shared = m
    got += 1
    a, b = strip_publisher(r.get('title')).lower(), strip_publisher(named[j].get('title')).lower()
    is_dup = a[:60] == b[:60]
    if is_dup:
        dup_title += 1
    ok = (r.get('inn') and r.get('inn') == named[j].get('inn')) or \
         (norm_name(r.get('company')) and norm_name(r.get('company')) == norm_name(named[j].get('company')))
    if ok:
        right += 1
        if not is_dup:
            right_nodup += 1
    elif len(wrong_ex) < 6:
        wrong_ex.append((r.get('company'), named[j].get('company'),
                         strip_publisher(r.get('title'))[:70], shared[:3]))

nodup_got = got - dup_title

# ---------- применение к безымянным ----------
hits = []
for r in anon:
    t = rec_tokens(r)
    m = match(t, reg_norm(r.get('region')),
              obj_class(strip_publisher(r.get('title')) + ' ' + (r.get('what') or '')),
              date_of(r))
    if m:
        j, shared = m
        hits.append((r, named[j], shared))

print()
print('==================== ИТОГ (главное) ====================')
print('корпус jsonl: всего %d, с именем %d, без имени %d' % (len(recs), len(named), len(anon)))
print('редкий токен = df<=%d; словарь редких токенов: %d' % (RARE, len(idx)))
print('--- ЧЕСТНАЯ ПРОВЕРКА (у именованной записи спрятали имя, ищем по корпусу) ---')
print('проверено записей: %d' % len(sample))
print('матчер дал ответ: %d (охват %.0f%%)' % (got, 100.0 * got / max(1, len(sample))))
print('ответ ВЕРНЫЙ: %d (точность %.0f%%)' % (right, 100.0 * right / max(1, got)))
print('из них совпал сам заголовок (дубль новости, не «поздняя новость»): %d' % dup_title)
print('БЕЗ дублей заголовка: ответов %d, верных %d (точность %.0f%%, охват %.1f%%)'
      % (nodup_got, right_nodup, 100.0 * right_nodup / max(1, nodup_got),
         100.0 * nodup_got / max(1, len(sample))))
print('--- ПРИМЕНЕНИЕ К БЕЗЫМЯННЫМ ---')
print('безымянных: %d, матчер дал имя: %d (%.0f%%)'
      % (len(anon), len(hits), 100.0 * len(hits) / max(1, len(anon))))
print('--- ошибочные ответы на отложенной выборке (истина -> что нашли) ---')
for w in wrong_ex:
    print('  ИСТИНА=%s НАШЛИ=%s | %s | общие=%s' % w)
print('--- безымянные: что нашлось (глазами) ---')
for r, nr, sh in hits[:10]:
    print('  A: %s [%s]' % (strip_publisher(r.get('title'))[:85], r.get('region') or ''))
    print('  B: %s | %s | общие=%s' % (nr.get('company'),
                                       strip_publisher(nr.get('title'))[:70], sh[:4]))
