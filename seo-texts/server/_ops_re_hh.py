# -*- coding: utf-8 -*-
r"""ПЕРЕМЕР №2: hh после трёх сегодняшних починок.

Прежний замер (32 компании → 8 вакансий → 1 контакт) недействителен:
  * browser_probe не понимал ПАКЕТ ссылок и открывал 1 вакансию вместо 8;
  * человек без НОМЕРА (callTracking шлёт {"country":"7"} без number)
    выбрасывался молча;
  * рубеж принадлежности искал ключ "employer", которого у hh нет.

Дельфин отдаёт HTTP 500 при перегрузке — это НЕ пустой источник. Поэтому
BP.probe здесь обёрнут ретраем, а число 500-к считается отдельно: если бы
ретрая не было, ровно столько компаний ушло бы в ложный ноль.

ДОЛГОВЕЧНОСТЬ: каждая компания сразу дописывается в серверный jsonl с fsync.

usage: _ops_re_hh.py <start> <count> [threads] [budget_s]
       _ops_re_hh.py sum
"""
import io
import json
import os
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import browser_probe as BP    # noqa: E402

ПОТОК = r'C:\seostat\drop\re_hh_stream.jsonl'
_злок = threading.Lock()
_сч = {'probe': 0, 'ошибок': 0, 'пусто': 0, 'ретраев': 0, '500': 0}


def p(*a):
    print(*a)
    sys.stdout.flush()


_TL = threading.local()
ПОПЫТОК = int(os.environ.get('RE_HH_TRIES', '4'))


def _ретрай(orig):
    """Дельфин на перегрузке отдаёт 500/пустой html. Несколько заходов с
    растущей паузой — профиль успевает освободиться, а мы не записываем живой
    источник в пустые. Текст каждой неудачи кладём в запись компании: без него
    «ноль» неотличим от «источник пуст»."""
    # ПРОФИЛЬ ДЕЛЬФИНА — ЭКСКЛЮЗИВНЫЙ РЕСУРС. Круговой _hh_prof_next() этого не
    # гарантирует: пока воркер 90 секунд ходит по пачке из 8 вакансий, счётчик
    # успевает провернуться, второй воркер стартует ТОТ ЖЕ профиль и убивает
    # чужую сессию. Живьём это выглядит как «HTTP 500» и «Target page, context
    # or browser has been closed» — и читалось бы как «источник пуст».
    # Здесь профиль берётся В АРЕНДУ из очереди и возвращается в хвост:
    # одновременно занят максимум один воркер на профиль, и заходы чередуются.
    import queue
    пул = queue.Queue()
    for x in [y for y in re.split(r'[,\s]+', EC._HH_DOLPHIN_DEF) if y]:
        пул.put(x)

    def _f(арг):
        посл = ''
        for попытка in range(ПОПЫТОК):
            with _злок:
                _сч['probe'] += 1
                if попытка:
                    _сч['ретраев'] += 1
            pid = пул.get()
            try:
                r = orig(dict(арг, dolphin_profile=pid))
                if (r or {}).get('html'):
                    return r
                посл = str((r or {}).get('error') or 'пустой html')[:120]
                with _злок:
                    _сч['пусто'] += 1
            except Exception as ex:  # noqa: BLE001
                посл = f'{type(ex).__name__}: {str(ex)[:110]}'
                with _злок:
                    _сч['ошибок'] += 1
            finally:
                пул.put(pid)
            if '500' in посл:
                with _злок:
                    _сч['500'] += 1
            getattr(_TL, 'бед', []).append(
                '%s|проф%s|%s' % (str(арг.get('url'))[:40], pid, посл))
            time.sleep(8 + попытка * 10)
        return {'error': посл}
    return _f


def прозрачная():
    """Та же боевая функция, но БЕЗ схлопывания результата в None.

    Хвост `return out if (out['employer'] or out['contacts']) else None`
    выбрасывает и найденные ВАКАНСИИ, и список «пропущено», когда контактов
    нет, а имя работодателя не прочиталось из стейта. Для замера это потеря
    ровно тех цифр, которые надо измерить, поэтому берём исходник функции и
    меняем ОДНУ строку хвоста — вся логика поиска и разбора остаётся боевой.
    """
    import inspect
    src = inspect.getsource(EC.hh_lpr_contacts)
    стар = "return out if (out['employer'] or out['contacts']) else None"
    assert src.count(стар) == 1, 'хвост функции изменился — правь замер'
    src = src.replace(стар, "return out").replace(
        'def hh_lpr_contacts(', 'def _hh_прозрачно(', 1)
    g = dict(EC.__dict__)
    exec(compile(src, '<hh_прозрачно>', 'exec'), g)  # noqa: S102
    return g['_hh_прозрачно']


def цели():
    БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
    из, было = [], set()
    for строки in (БАЗА.values() if isinstance(БАЗА, dict) else [БАЗА]):
        for x in строки:
            i = str(x.get('inn') or '').strip()
            if i and i not in было:
                было.add(i)
                из.append({'inn': i, 'name': str(x.get('name') or ''),
                           'site': str(x.get('site') or '')})
    return из


def сделано():
    д = {}
    if os.path.exists(ПОТОК):
        for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                j = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            д[j.get('inn')] = j
    return д


def дописать(зап):
    with _злок:
        with io.open(ПОТОК, 'a', encoding='utf-8') as f:
            f.write(json.dumps(зап, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


ФУНК = [None]


def _метка(orig):
    """Записываем, ЧТО именно приходит в _hh_post. Метка «кадры» ставится и
    когда комментарий есть, но не похож на роль, и когда его нет ВООБЩЕ, —
    без этого счётчика нельзя сказать, значит ли она хоть что-то."""
    def _f(comment, vacancy_title):
        r = orig(comment, vacancy_title)
        getattr(_TL, 'комм', []).append(
            {'comment': (comment or ''), 'vacancy': (vacancy_title or '')[:60],
             'метка': r})
        return r
    return _f


def один(c):
    t0 = time.time()
    ош = ''
    _TL.бед = []
    _TL.комм = []
    try:
        r = ФУНК[0](c, max_vac=8)
    except Exception as ex:  # noqa: BLE001
        r, ош = None, f'{type(ex).__name__}: {str(ex)[:90]}'
    r = r or {}
    # что отдал бы БОЕВОЙ хвост на этих же данных
    боевой_none = not (r.get('employer') or r.get('contacts'))
    дописать({'inn': c['inn'], 'name': c['name'][:70],
              'боевой_вернул_бы_none': боевой_none,
              'бренд': EC.бренд_компании(c['name'], c.get('site')),
              'сек': round(time.time() - t0, 1), 'ошибка': ош,
              'employer': r.get('employer'),
              'vacancies': r.get('vacancies') or [],
              'contacts': r.get('contacts') or [],
              'пропущено': r.get('пропущено') or [],
              'отказ': r.get('отказ') or '',
              'беды_дельфина': (getattr(_TL, 'бед', []) or [])[:8],
              'метки': (getattr(_TL, 'комм', []) or [])[:20]})
    return c['inn']


def свод(д):
    в = {'компаний': 0, 'с_вакансиями': 0, 'вакансий': 0, 'с_контактом': 0,
         'контактов': 0, 'с_фио': 0, 'с_телефоном': 0, 'с_почтой': 0,
         'без_номера_но_с_лицом': 0, 'пропущено_чужих': 0, 'отказов': 0,
         'ошибок': 0, 'пусто_совсем': 0, 'боевой_схлопнул_бы_в_none': 0,
         'вакансий_у_них': 0}
    роли = {}
    прим = []
    for j in д.values():
        в['компаний'] += 1
        if j.get('ошибка'):
            в['ошибок'] += 1
        if j.get('отказ'):
            в['отказов'] += 1
        vv = j.get('vacancies') or []
        cc = j.get('contacts') or []
        if j.get('боевой_вернул_бы_none') and (vv or j.get('пропущено')):
            в['боевой_схлопнул_бы_в_none'] += 1
            в['вакансий_у_них'] += len(vv)
        в['вакансий'] += len(vv)
        if vv:
            в['с_вакансиями'] += 1
        if cc:
            в['с_контактом'] += 1
        else:
            в['пусто_совсем'] += 1
        в['контактов'] += len(cc)
        в['пропущено_чужих'] += len(j.get('пропущено') or [])
        for c in cc:
            if c.get('person'):
                в['с_фио'] += 1
            if c.get('phone'):
                в['с_телефоном'] += 1
            else:
                if c.get('person') or c.get('email'):
                    в['без_номера_но_с_лицом'] += 1
            if c.get('email'):
                в['с_почтой'] += 1
            роли[c.get('post') or '(пусто)'] = роли.get(c.get('post') or '(пусто)', 0) + 1
            прим.append(dict(c, inn=j.get('inn'), name=(j.get('name') or '')[:40]))
    for j in д.values():
        if not (j.get('vacancies') or j.get('contacts')):
            p('ПУСТО inn=%s бренд=%r отказ=%r проп=%d беды=%s'
              % (j.get('inn'), j.get('бренд'), j.get('отказ'),
                 len(j.get('пропущено') or []),
                 json.dumps(j.get('беды_дельфина') or [], ensure_ascii=False)[:200]))
    for j in д.values():
        for s in (j.get('пропущено') or [])[:3]:
            p('ОТСЕЯНО inn=%s бренд=%r %s'
              % (j.get('inn'), j.get('бренд'),
                 json.dumps(s, ensure_ascii=False)[:230]))
    мк = {'всего': 0, 'с_комментарием': 0, 'комментарий_пуст': 0,
          'роль_из_комментария': 0, 'кадры_по_умолчанию': 0}
    образцы = []
    for j in д.values():
        for m in (j.get('метки') or []):
            мк['всего'] += 1
            c = (m.get('comment') or '').strip()
            if c:
                мк['с_комментарием'] += 1
                if len(образцы) < 8:
                    образцы.append(m)
            else:
                мк['комментарий_пуст'] += 1
            if m.get('метка') == 'кадры':
                мк['кадры_по_умолчанию'] += 1
            else:
                мк['роль_из_комментария'] += 1
    if мк['всего']:
        for m in образцы:
            p('КОММЕНТАРИЙ ' + json.dumps(m, ensure_ascii=False)[:200])
        p('МЕТКИ ' + json.dumps(мк, ensure_ascii=False))
    p('РОЛИ ' + json.dumps(sorted(роли.items(), key=lambda x: -x[1]), ensure_ascii=False))
    for x in прим[:22]:
        p('КОНТАКТ ' + json.dumps(x, ensure_ascii=False)[:290])
    p('ПРОБЫ ' + json.dumps(_сч, ensure_ascii=False))
    p('ИТОГ ' + json.dumps(в, ensure_ascii=False))


def main():
    if sys.argv[1:2] == ['sum']:
        свод(сделано())
        return
    start = int(sys.argv[1])
    count = int(sys.argv[2])
    thr = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    бюджет = float(sys.argv[4]) if len(sys.argv) > 4 else 170.0
    BP.probe = _ретрай(BP.probe)
    EC._SEM_BROWSER = threading.Semaphore(thr)
    EC._hh_post = _метка(EC._hh_post)   # ДО снимка globals в прозрачная()
    ФУНК[0] = прозрачная()
    все = цели()
    уже = сделано()
    # --redo: пустые перезапускаем. Ноль от перегруженного дельфина — не ответ
    # источника, и оставлять его в замере нельзя.
    пустые = {i for i, j in уже.items()
              if not (j.get('vacancies') or j.get('contacts'))}
    отбор = set()
    if '--inn' in sys.argv:
        отбор = {x for x in re.split(r'[,\s]+',
                 sys.argv[sys.argv.index('--inn') + 1]) if x}

    def годен(i):
        if отбор:
            return i in отбор
        return (i not in уже or '--force' in sys.argv
                or ('--redo' in sys.argv and i in пустые))
    очередь = ([c for c in все if годен(c['inn'])] if отбор
               else [c for c in все[start:start + count] if годен(c['inn'])])
    p('ЦЕЛЕЙ=%d СРЕЗ=%d..%d К_РАБОТЕ=%d УЖЕ=%d'
      % (len(все), start, start + count, len(очередь), len(уже)))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=thr) as ex:
        фью = []
        for c in очередь:
            if time.time() - t0 > бюджет:
                p('БЮДЖЕТ исчерпан')
                break
            фью.append(ex.submit(один, c))
        for f in фью:
            try:
                f.result(timeout=max(10, бюджет + 100 - (time.time() - t0)))
            except Exception as ex2:  # noqa: BLE001
                p('поток упал: %s' % str(ex2)[:90])
    свод(сделано())


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-1200:])
