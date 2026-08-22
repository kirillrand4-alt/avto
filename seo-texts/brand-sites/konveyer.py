#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Конвейер: страница целиком, от задания до вычитанного текста.

    python3 konveyer.py [--potokov 5] [--skolko 0] [--seed 1]

ЗАЧЕМ ОТДЕЛЬНЫЙ ДРАЙВЕР. Три шага (ТЗ, статья, доводка) до сих пор
запускались вручную и барьерами: сначала все задания, потом все статьи.
Барьер простаивает - пока самое долгое ТЗ идёт двадцать пять минут,
освободившиеся потоки стоят. Здесь каждая страница идёт своей цепочкой
независимо, и слот занимает следующая, а не ждёт соседей.

ВЫБОР СТРАНИЦ. Владелец 22.08: «статьи для генерации выбираешь
не по признаку (мкс, кс и тд) а рандомно, но вес в рандоме должен быть
вдвое выше у дорогих статей». Дорогие - по деньгам сделки, а не
по расходу токенов: станции и комплексы против компонентов. Разделение
проверено по карте цен (медиана позиции от 0,7 до 13,3 млн по сайтам)
и по составу поставки: станция это машина плюс подготовка воздуха плюс
контейнер плюс монтаж, осушитель - узел к ней.

ДОЛГОВЕЧНОСТЬ. Песочница за сессию откатывалась дважды, унося каталоги
целиком. Поэтому каждая готовая страница сразу коммитится и пушится,
а состояние конвейера лежит в файле с fsync - прогон переживает
рестарт и продолжает с того места, где встал.
"""
import argparse, glob as _glob, json, os, random, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
sys.path.insert(0, DIR)

SOSTOYANIE = os.path.join(DIR, 'konveyer-sostoyanie.json')
ZHURNAL = os.path.join(DIR, 'konveyer.jsonl')
PID_FAJL = os.path.join(DIR, 'konveyer.pid')

# Дорогие темы - вдвое больший вес при случайном выборе.
DOROGIE = {
    'kompressornaya-stanciya', 'mks',
    'azotnaya-stanciya', 'azotnaya-stanciya-modulnaya',
    'kislorodnaya-stanciya', 'kislorodnaya-stanciya-modulnaya',
    'tsentrobezhnye-kompressory', 'dozhimnye-kompressory',
    'generatory-azota', 'generatory-kisloroda',
}
VES_DOROGOY, VES_OBYCHNOY = 2, 1


def _zapustit(argv, minut=45):
    """Шаг конвейера отдельным процессом. Возврат (успех, хвост вывода)."""
    try:
        r = subprocess.run([sys.executable] + argv, cwd=DIR, timeout=minut * 60,
                           capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr)[-600:]
    except subprocess.TimeoutExpired:
        return False, f'шаг не уложился в {minut} минут'


def zapisat(zapis):
    """Строка журнала с fsync: песочница откатывается, журнал должен жить."""
    with open(ZHURNAL, 'a', encoding='utf-8') as f:
        f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())


def sohranit_sostoyanie(s):
    with open(SOSTOYANIE, 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
        f.flush(); os.fsync(f.fileno())


def _proverit(slug):
    """Претензии гейтов к готовой странице. Пусто - чисто.

    Возврат: (претензии, путь, нужен_ли_разбор).

    ПЕРЕЗАГРУЖАТЬ НАДО ВСЮ ЦЕПОЧКУ, А НЕ ВЕРХНИЙ МОДУЛЬ. Гейты
    чинятся по ходу ночного прогона, а конвейер живёт часами. Раньше
    здесь перечитывался только gen_statya - но он делает `import
    svyaznost`, а тот уже лежит в sys.modules и заново не исполняется.
    То есть починка арифметики доехала бы до шагов-подпроцессов
    и НЕ доехала бы до этой проверки: одна и та же страница получала
    бы разный вердикт от подпроцесса и от конвейера.
    """
    import importlib
    for imya in ('svyaznost', 'sanity', 'brand_facts_lib', 'obem'):
        m = sys.modules.get(imya)
        if m is not None:
            try:
                importlib.reload(m)
            except Exception:
                pass
    import gen_statya as S
    importlib.reload(S)
    # .RUCHNOY - это НЕ синоним .final. Доводка ставит его, когда две
    # линзы разошлись в факте; страница пригодна к чтению, но её
    # смотрит человек. Конвейер раньше брал любой из двух файлов
    # и одинаково рапортовал «чисто» - то есть пометка, ради которой
    # доводка эту развилку и заводила, гасла ровно на выходе.
    put = os.path.join(DIR, 'statyi-final', f'{slug}.final.html')
    razbor = False
    if not os.path.exists(put):
        put = os.path.join(DIR, 'statyi-final', f'{slug}.RUCHNOY.html')
        razbor = os.path.exists(put)
    if not os.path.exists(put):
        return ['нет файла после доводки'], None, False
    html = open(put, encoding='utf-8').read()
    tz = os.path.join(DIR, 'tz', f'TZ-{slug}.md')
    sh = S.razobrat_tz(open(tz, encoding='utf-8').read())
    gaz = bool(re.search(r'azotn|kislorod|mks', slug, re.I))
    return S.proverit(html, sh, gaz), put, razbor


def cepochka(slug, jobs_fajl):
    """Задание, статья, доводка, проверка. Возврат словаря итога."""
    t0 = time.time()
    itog = {'slug': slug, 'nachalo': time.strftime('%H:%M:%S')}
    tz = os.path.join(DIR, 'tz', f'TZ-{slug}.md')
    if not os.path.exists(tz):
        ok, hvost = _zapustit(['gen_tz.py', '--jobs', jobs_fajl, '--only', slug,
                               '--workers', '1', '--dva', '--tries', '3'], 45)
        if not os.path.exists(tz):
            itog.update(shag='ТЗ', itog='брак', hvost=hvost[-300:],
                        sekund=round(time.time() - t0))
            return itog
    statya = os.path.join(DIR, 'statyi', f'{slug}.html')
    if not os.path.exists(statya):
        ok, hvost = _zapustit(['gen_statya.py', '--tz', tz], 30)
        if not os.path.exists(statya):
            itog.update(shag='статья', itog='брак', hvost=hvost[-300:],
                        sekund=round(time.time() - t0))
            return itog
        if 'ЧИСТО' not in hvost:
            # НЕГОДНУЮ СТАТЬЮ УБРАТЬ С ДОРОГИ. Иначе повтор её найдёт,
            # пропустит генерацию и снова упрётся в тот же обрыв: шлюз
            # роняет стрим, документ приходит обрезанным на полуслове,
            # и никакая доводка этого не лечит - там нечего править,
            # там нет конца текста. Два обрыва на первых одиннадцати
            # страницах, то есть цена бездействия - каждая шестая.
            #
            # Не удаляем, а отставляем: если обрыв окажется не в статье,
            # а в моей проверке, работа не потеряна.
            # Обрыв шлюза - не вина страницы и попытку не тратит:
            # ограничение стоит против тех, кто падает по своей причине.
            obryv = 'оборван' in hvost or 'вероятен обрыв' in hvost
            vid = 'obryv' if obryv else 'brak'
            svoih = len(_glob.glob(os.path.join(DIR, 'statyi',
                                                f'{slug}.brak*.html')))
            nomer = len(_glob.glob(os.path.join(DIR, 'statyi',
                                                f'{slug}.{vid}*.html'))) + 1
            if obryv or svoih < 2:
                try:
                    os.rename(statya, os.path.join(
                        DIR, 'statyi', f'{slug}.{vid}{nomer}.html'))
                except OSError:
                    pass
            itog.update(shag='статья', itog='претензии механики',
                        hvost=hvost[-300:], otstavlena=True,
                        sekund=round(time.time() - t0))
            return itog
    ok, hvost = _zapustit(['dovodka_statey.py', slug, '--out',
                           os.path.join(DIR, 'statyi-final')], 40)
    pret, put, razbor = _proverit(slug)
    if pret:
        verdikt = 'претензии'
    elif razbor:
        verdikt = 'нужен разбор'
    else:
        verdikt = 'чисто'
    itog.update(shag='готово', itog=verdikt, pretenzii=pret[:3],
                fajl=os.path.basename(put) if put else None,
                sekund=round(time.time() - t0))
    return itog


def vybrat(jobs, sdelano, rnd, skolko=0):
    """Случайный порядок с двойным весом дорогих тем."""
    ostalos = [j for j in jobs if j['slug'] not in sdelano]
    korzina = []
    for j in ostalos:
        tema = j['slug'].split('--', 1)[1]
        ves = VES_DOROGOY if tema in DOROGIE else VES_OBYCHNOY
        korzina += [j] * ves
    poryadok, vzyato = [], set()
    while korzina and (not skolko or len(poryadok) < skolko):
        j = rnd.choice(korzina)
        if j['slug'] not in vzyato:
            poryadok.append(j); vzyato.add(j['slug'])
        korzina = [x for x in korzina if x['slug'] != j['slug']]
    return poryadok


def zafiksirovat(slug, itog):
    """Коммит и пуш: песочница откатывается, работа должна пережить."""
    try:
        subprocess.run(['git', 'add', '-A'], cwd=DIR, capture_output=True, timeout=120)
        msg = (f'конвейер: {slug} - {itog}\n\n'
               f'Собрано автономным прогоном ночью 22-23.08.\n\n'
               f'Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>')
        subprocess.run(['git', 'commit', '-q', '-m', msg], cwd=DIR,
                       capture_output=True, timeout=120)
        for popytka in range(4):
            r = subprocess.run(['git', 'push', '-u', 'origin',
                                'claude/guest-post-text-generator-35u4n6'],
                               cwd=DIR, capture_output=True, timeout=180)
            if r.returncode == 0:
                return True
            time.sleep(2 ** (popytka + 1))
    except Exception:
        pass
    return False


def na_drop(put):
    """Готовую страницу на дроп, чтобы владелец забрал без чата."""
    skript = os.path.join(os.path.dirname(DIR), 'server', 'drop_client.sh')
    if not os.path.exists(skript):
        return False
    try:
        r = subprocess.run(['bash', skript, 'up', put], cwd=DIR,
                           capture_output=True, text=True, timeout=180)
        return r.returncode == 0
    except Exception:
        return False


def zapisat_pid():
    """Метка «я живой» для сторожа.

    ЖИЗНЬ ПРОЦЕССА НЕЛЬЗЯ ПРОВЕРЯТЬ ПОИСКОМ ПО КОМАНДНОЙ СТРОКЕ.
    Сторож звал `pgrep -f konveyer.py` и всю ночь считал конвейер живым,
    хотя тот не работал: подстрока «konveyer.py» есть в командной строке
    моего же наблюдателя, который этот самый pgrep и запускает. Сторож
    ни разу ничего не поднял, storozh.log остался пуст, а внешне всё
    выглядело работающим - худший вид поломки.

    PID-файл однозначен: в нём номер, и либо процесс с этим номером
    жив, либо нет. Совпасть с чужой командной строкой номер не может.
    """
    with open(PID_FAJL, 'w') as f:
        f.write(str(os.getpid()))
        f.flush(); os.fsync(f.fileno())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--potokov', type=int, default=5)
    ap.add_argument('--skolko', type=int, default=0, help='0 - все')
    ap.add_argument('--seed', type=int, default=None)
    a = ap.parse_args()
    zapisat_pid()

    jobs = (json.load(open(os.path.join(DIR, 'tz-jobs.json'), encoding='utf-8'))
            + json.load(open(os.path.join(DIR, 'station-jobs.json'), encoding='utf-8')))
    jobs_po_slug = {j['slug']: j for j in jobs}
    fajl_zadaniy = {j['slug']: ('station-jobs.json'
                                if os.path.exists(os.path.join(DIR, 'station-jobs.json'))
                                and any(x['slug'] == j['slug'] for x in json.load(
                                    open(os.path.join(DIR, 'station-jobs.json'), encoding='utf-8')))
                                else 'tz-jobs.json') for j in jobs}

    sdelano = set()
    if os.path.exists(ZHURNAL):
        for s in open(ZHURNAL, encoding='utf-8'):
            try:
                z = json.loads(s)
                # «Нужен разбор» - это ЗАКОНЧЕННАЯ страница с пометкой,
                # а не брак: гейты её пропустили, спорят две линзы.
                # Гонять её заново по всей цепочке бессмысленно - второй
                # прогон даст ту же пометку и второй раз возьмёт деньги.
                if z.get('itog') in ('чисто', 'нужен разбор'):
                    sdelano.add(z['slug'])
            except Exception:
                pass

    rnd = random.Random(a.seed)
    poryadok = vybrat(jobs, sdelano, rnd, a.skolko)
    print(f'страниц к прогону: {len(poryadok)}, потоков {a.potokov}, '
          f'уже готово {len(sdelano)}', flush=True)
    dorogih = sum(1 for j in poryadok[:20] if j['slug'].split('--', 1)[1] in DOROGIE)
    print(f'в первой двадцатке дорогих: {dorogih}', flush=True)

    gotovo, brak = [], []
    with ThreadPoolExecutor(max_workers=a.potokov) as ex:
        futs = {ex.submit(cepochka, j['slug'], fajl_zadaniy[j['slug']]): j['slug']
                for j in poryadok}
        for f in as_completed(futs):
            slug = futs[f]
            try:
                itog = f.result()
            except Exception as e:
                itog = {'slug': slug, 'itog': 'сбой', 'hvost': repr(e)[:200]}
            zapisat(itog)
            if itog.get('itog') in ('чисто', 'нужен разбор'):
                gotovo.append(slug)
                zafiksirovat(slug, itog['itog'])
                if itog.get('fajl'):
                    na_drop(os.path.join(DIR, 'statyi-final', itog['fajl']))
            else:
                brak.append(slug)
            sohranit_sostoyanie({'обновлено': time.strftime('%Y-%m-%d %H:%M:%S'),
                                 'готово': len(gotovo), 'брак': len(brak),
                                 'в очереди': len(poryadok) - len(gotovo) - len(brak),
                                 'последняя': slug, 'итог последней': itog.get('itog')})
            print(f'  {slug}: {itog.get("itog")} за {itog.get("sekund", 0)} с '
                  f'[готово {len(gotovo)}, брак {len(brak)}]', flush=True)
    print(f'\nитог: чисто {len(gotovo)}, брак {len(brak)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
