# -*- coding: utf-8 -*-
r"""Мост между ZennoPoster и конвейером обогащения.

Зачем (владелец 13.08: «надо общий конвейер», «могу запустить готовый код на 10
потоков, чтобы ты клал файл, она его подхватывала и выдавала результат»).

Дельфин поднимает профиль на КАЖДУЮ страницу и по факту доходит только до главной.
Зенка держит инстанс и проходит сайт целиком (кубик zenno/obhod_stranic.cs), но
складывает сырой HTML на диск. Этот модуль замыкает круг:

    enrich_contacts        сайт не открылся (заслон)  ->  строка в ochered.txt
            |
    ZennoPoster (10 потоков, кубик)  -> <ИНН>_N.html + <ИНН>.urls.txt в gotovo\
            |
    zenno_most --priyom    -> страницы в кэш C:\seostat\drop\pagecache\<ИНН>.json.gz
            |
    enrich_contacts        обходит компанию ОБЫЧНЫМ путём, но страницы берёт с диска
                           (crawl_contacts читает кэш) -> почты, роли, ИНН, судья

Разбор нигде не дублируется: Зенка возит HTML, всю логику по-прежнему делает питон.

Команды:
    python zenno_most.py --ochered [N]   дописать до N компаний с заслоном в очередь
    python zenno_most.py --priyom        разобрать всё готовое в кэш
    python zenno_most.py --demon [сек]   цикл: очередь + приём каждые N секунд (по умолч. 120)
    python zenno_most.py --stat          что где лежит

Пути (меняются переменными окружения):
    ZENNO_DIR      C:\seostat\drop\zenno          корень обмена
      ochered.txt                                 очередь для Зенки: «ИНН;адрес»
      gotovo\                                     сюда Зенка кладёт HTML
      razobrano\                                  сюда переносим после разбора
    PAGECACHE_DIR  C:\seostat\drop\pagecache      кэш страниц конвейера
"""
import gzip
import json
import os
import re
import shutil
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
GOTOVO = os.path.join(ZENNO, 'gotovo')
RAZOBRANO = os.path.join(ZENNO, 'razobrano')
OCHERED = os.path.join(ZENNO, 'ochered.txt')
# Длина очереди, выше которой пополнение не запускаем.
ПОРОГ_ПОПОЛНЕНИЯ = int(os.environ.get('ZENNO_POROG_OCHEREDI', '5000'))
OTDANO = os.path.join(ZENNO, 'otdano.txt')      # что уже клали в очередь — без повторов
NE_OTKRYLIS = os.path.join(ZENNO, 'ne_otkrylis.txt')   # заслон/мёртвый сайт — на второй заход
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')


def _papki():
    for p in (ZENNO, GOTOVO, RAZOBRANO, KESH):
        os.makedirs(p, exist_ok=True)


def _dlina_ocheredi():
    if not os.path.exists(OCHERED):
        return 0
    with open(OCHERED, encoding='utf-8', errors='replace') as f:
        return sum(1 for s in f if s.strip())


def _otdannye():
    if not os.path.exists(OTDANO):
        return set()
    with open(OTDANO, encoding='utf-8', errors='replace') as f:
        return {s.strip() for s in f if s.strip()}


def ochered(predel=500):
    """Дописать в очередь компании, чей сайт питон взять не смог.

    Берём тех, у кого сайт известен (или есть кандидат), но контактов нет — это и
    есть случаи заслона, ради которых Зенка нужна. Уже отданные не повторяем.
    """
    _papki()
    bylo = _otdannye()
    c = sqlite3.connect(BD)
    c.row_factory = sqlite3.Row
    # БЕЗ LIMIT, с курсором. Было `limit predel*4` — и наполнитель встал намертво,
    # когда отданных набралось больше этого числа: первые 1200 строк выборки все
    # оказывались уже отданными, отсев съедал их целиком, и каждый круг демона
    # честно дописывал НОЛЬ. Со стороны это выглядело как «работа кончилась»
    # (владелец 13.08: «лог пустой»), хотя в базе оставалось 3728 компаний.
    # Теперь идём курсором и останавливаемся, набрав нужное.
    kursor = c.execute(
        "select inn, coalesce(site,'') site, coalesce(cand_site,'') cand "
        "from companies where (coalesce(site,'')<>'' or coalesce(cand_site,'')<>'') "
        "and coalesce(best_email,'')='' "
        "and not exists(select 1 from emails e where e.inn=companies.inn)")

    # справочники и агрегаторы в очередь не отдаём: первая партия 13.08 показала
    # в заданиях check.tochka.com и tatcenter.ru — Зенка честно обошла чужие сайты.
    # Меркой владеет сам конвейер (_is_own_site), берём её, а не свой список.
    # Мерка enrich_contacts (_NE_SAYT) знает 22 домена и не знает ни dzen.ru
    # (яндекс переименовал zen.yandex.ru), ни b2b.house, ни банковских проверок
    # контрагентов — владелец увидел их в логе Зенки 17.08. Поэтому спрашиваем
    # ОБЕ мерки: свою общую (ploshchadki) и старую.
    try:
        sys.path.insert(0, DIR)
        import enrich_contacts as _E
        svoy = _E._is_own_site
    except Exception:  # noqa: BLE001
        svoy = lambda u: True   # модуль не поднялся — лучше отдать, чем встать
    try:
        import ploshchadki as _PL
        ploshchadka = _PL.из_списка
    except Exception:  # noqa: BLE001
        ploshchadka = lambda u: ''

    novye = []
    prosmotreno = otdano_ranshe = chuzhih = 0
    for r in kursor:
        prosmotreno += 1
        inn = str(r['inn'])
        if inn in bylo:
            otdano_ranshe += 1
            continue
        u = (r['site'] or r['cand'] or '').strip()
        if not u:
            continue
        if ploshchadka(u):
            chuzhih += 1
            continue
        try:
            if not svoy(u if u.startswith('http') else 'http://' + u):
                chuzhih += 1
                continue
        except Exception:  # noqa: BLE001
            pass
        # режим «oba»: контакты и факты за один заход. Раньше строка шла без
        # третьего поля, то есть контактным режимом, и каталог с новостями для
        # писем не собирался вовсе — за фактами приходилось гнать вторым проходом.
        novye.append('%s;%s;oba' % (inn, u))
        bylo.add(inn)
        if len(novye) >= predel:
            break
    c.close()

    if novye:
        for put, stroki in ((OCHERED, novye),
                            (OTDANO, [s.split(';')[0] for s in novye])):
            with open(put, 'a', encoding='utf-8') as f:
                f.write('\n'.join(stroki) + '\n')
                f.flush()
                os.fsync(f.fileno())
    # числа отсева печатаем всегда: молчаливый ноль — это ровно тот дефект,
    # который мы только что чинили
    return {'дописано': len(novye), 'просмотрено': prosmotreno,
            'уже_отдавали': otdano_ranshe, 'чужих_сайтов': chuzhih,
            'файл': OCHERED}


def povtor_nezashedshih(predel=700, starshe_chasov=6):
    """Сайты из ne_otkrylis.txt — обратно в очередь.

    Заслон бывает временным (лимит на адрес, мёртвая прокси, ремонт сайта), а
    файл до сих пор работал как кладбище: 636 строк, ни одна не перепроверена.
    Владелец 14.08: «кидай в очередь». Разобранный файл переименовываем с датой,
    чтобы история осталась, но вторая попытка не смешивалась с первой.
    """
    _papki()
    if not os.path.exists(NE_OTKRYLIS):
        return {'файла нет': NE_OTKRYLIS}
    stroki = []
    with open(NE_OTKRYLIS, encoding='utf-8-sig', errors='replace') as f:
        for s in f:
            s = s.strip().lstrip('\ufeff')
            if not s:
                continue
            ch = s.split(';')
            if len(ch) >= 2 and ch[0].isdigit() and ch[1].startswith('http'):
                stroki.append((ch[0], ch[1], ch[2] if len(ch) > 2 else ''))
    vidno, novye = set(), []
    for inn, u, _ts in stroki:
        if inn in vidno:
            continue
        vidno.add(inn)
        novye.append('%s;%s;oba' % (inn, u))
        if len(novye) >= predel:
            break
    if novye:
        with open(OCHERED, 'a', encoding='utf-8') as f:
            f.write('\n'.join(novye) + '\n')
            f.flush()
            os.fsync(f.fileno())
        arh = NE_OTKRYLIS.replace('.txt', '-%s.txt' % time.strftime('%Y%m%d-%H%M'))
        try:
            os.replace(NE_OTKRYLIS, arh)
        except Exception:  # noqa: BLE001
            arh = ''
        return {'вернули_в_очередь': len(novye), 'строк_в_файле': len(stroki),
                'архив': arh}
    return {'вернули_в_очередь': 0, 'строк_в_файле': len(stroki)}


def _ploshchadka(url):
    """Адрес — справочник или витрина? Общая мерка, та же что у чистки базы."""
    try:
        sys.path.insert(0, DIR)
        import ploshchadki as _PL
        return _PL.из_списка(url)
    except Exception:  # noqa: BLE001
        return ''


def pereobhod(predel=400, starshe_chasov=3):
    """Переобход всех, кого когда-либо обходили, — новым приоритетом разделов.

    Владелец 14.08: «если новых данных собираться не будет, все компании, которые
    когда-либо обходились, закинь на переобход». До сегодня кубик брал «о компании»
    и контакты, а каталог, производство, качество, экспорт и проекты почти не
    открывал: паспорта вышли бедными не потому, что сайты пустые.

    Порядок не случайный: сперва компании из очереди писем (их оператор увидит
    первыми), затем те, у кого паспорт пуст или без продукции, затем остальные —
    от самого старого кэша к свежему. Стоящих в очереди не дублируем, свежие
    (моложе starshe_chasov) не трогаем: они уже обойдены новым кубиком.
    """
    _papki()
    if not os.path.isdir(KESH):
        return {'кэша нет': KESH}
    porog = time.time() - starshe_chasov * 3600
    est = []
    for n in os.listdir(KESH):
        if not n.endswith('.json.gz'):
            continue
        p = os.path.join(KESH, n)
        try:
            if os.path.getmtime(p) > porog:
                continue
        except Exception:  # noqa: BLE001
            continue
        est.append((os.path.getmtime(p), n.split('.')[0]))
    est.sort()
    inny = [i for _t, i in est if i.isdigit()]
    if not inny:
        return {'нечего переобходить': 0}

    c = sqlite3.connect(BD)
    c.row_factory = sqlite3.Row
    sayty, bednye, ochered_pisem = {}, set(), set()
    for kusok in [inny[i:i + 900] for i in range(0, len(inny), 900)]:
        qq = ','.join('?' * len(kusok))
        for r in c.execute("select inn, coalesce(site,'') s, coalesce(cand_site,'') cs "
                           'from companies where inn in (%s)' % qq, kusok):
            u = (r['s'] or r['cs']).strip()
            # переобход брал всех, кого когда-либо обходили, — включая тех, кого
            # обошли ошибочно: справочники и банковские проверки контрагентов
            # возвращались в очередь круг за кругом
            if u and not _ploshchadka(u):
                sayty[str(r['inn'])] = u
    try:
        for r in c.execute("select inn, coalesce(facts_json,'') f from site_facts"):
            if not r['f'] or '"продукция": []' in r['f'] or '"продукция":[]' in r['f']:
                bednye.add(str(r['inn']))
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.path.insert(0, DIR)
        import site_facts as SF
        ochered_pisem = {k['inn'] for k in SF._kompanii_kampanii()}
    except Exception:  # noqa: BLE001
        pass
    c.close()

    v_ocheredi = set()
    if os.path.exists(OCHERED):
        with open(OCHERED, encoding='utf-8', errors='replace') as f:
            v_ocheredi = {s.split(';')[0].strip() for s in f if s.strip()}

    def ves(i):
        if i in ochered_pisem:
            return 0
        if i in bednye:
            return 1
        return 2

    kandidaty = [i for i in inny if i in sayty and i not in v_ocheredi]
    kandidaty.sort(key=ves)
    vzyato = kandidaty[:predel]
    if not vzyato:
        return {'дописано': 0, 'кандидатов': len(kandidaty)}
    with open(OCHERED, 'a', encoding='utf-8') as f:
        f.write('\n'.join('%s;%s;oba' % (i, sayty[i]) for i in vzyato) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return {'дописано': len(vzyato), 'кандидатов_всего': len(kandidaty),
            'из_очереди_писем': sum(1 for i in vzyato if i in ochered_pisem),
            'с_бедным_паспортом': sum(1 for i in vzyato if i in bednye)}


def _sobrat(inn):
    """Файлы одной компании из gotovo -> [(url, html)] в порядке обхода."""
    urls = []
    put_u = os.path.join(GOTOVO, '%s.urls.txt' % inn)
    if os.path.exists(put_u):
        # utf-8-sig, а не utf-8: .NET-овский Encoding.UTF8 пишет BOM, и первый адрес
        # приезжал как «﻿http://...» — страница теряла привязку. В кубике BOM
        # выключен, но старые файлы дочитываем корректно.
        with open(put_u, encoding='utf-8-sig', errors='replace') as f:
            urls = [s.strip().lstrip('﻿') for s in f if s.strip()]
    stranicy = []
    for i, u in enumerate(urls):
        ph = os.path.join(GOTOVO, '%s_%d.html' % (inn, i))
        if not os.path.exists(ph):
            continue
        try:
            with open(ph, encoding='utf-8', errors='replace') as f:
                h = f.read()
        except Exception:  # noqa: BLE001
            continue
        if h.strip():
            stranicy.append((u, h))
    return stranicy


def _otkazy(inn):
    """Страницы, которые Зенка запросила, а сайт не отдал: «уровень|причина|длина|url».

    Отдельным файлом, потому что это ЗАМЕР, а не данные: по нему видно, гасит ли
    защита вторую и дальше страницу (вопрос владельца 14.08). До этого отказ
    молча пропускался, и «ссылки не было» не отличалось от «не пустили».
    """
    p = os.path.join(GOTOVO, '%s.otkaz.txt' % inn)
    try:
        if os.path.exists(p):
            with open(p, encoding='utf-8-sig', errors='replace') as f:
                return [s.strip() for s in f if s.strip()][:40]
    except Exception:  # noqa: BLE001
        pass
    return []


def _kanal(inn):
    """Каким выходом Зенка взяла сайт: обычный / пауза / смена прокси / мобильный / капча.
    Кубик пишет это отдельным файлом — по нему считаем, окупаются ли мобильные и капчи."""
    p = os.path.join(GOTOVO, '%s.kanal.txt' % inn)
    try:
        if os.path.exists(p):
            return open(p, encoding='utf-8-sig', errors='replace').read().strip()[:24]
    except Exception:  # noqa: BLE001
        pass
    return ''


def _v_kesh(inn, stranicy, otkazy=None):
    """Положить страницы в кэш конвейера — В ТОМ ЖЕ формате, что пишет crawl_contacts.

    Формат обязан совпадать: читающая сторона (_stranicy_iz_kesha) ждёт {'pages':
    [{'url','html'}]}, и любое расхождение превратит работу Зенки в тишину.
    Если по этому ИНН кэш уже есть — дополняем, а не затираем: питон мог взять часть
    страниц сам, и терять их незачем.
    """
    put = os.path.join(KESH, '%s.json.gz' % inn)
    bylo = {}
    sayt = ''
    if os.path.exists(put):
        try:
            with gzip.open(put, 'rb') as f:
                d = json.loads(f.read().decode('utf-8', 'replace'))
            sayt = d.get('site') or ''
            for p in (d.get('pages') or []):
                if p.get('url') and p.get('html'):
                    bylo[p['url']] = p['html']
        except Exception:  # noqa: BLE001
            bylo = {}
    for u, h in stranicy:
        bylo[u] = h[:300000]
    if not sayt and stranicy:
        sayt = stranicy[0][0]

    pages, vsego = [], 0
    for u, h in bylo.items():
        if vsego + len(h) > 2500000:
            continue
        vsego += len(h)
        pages.append({'url': u, 'html': h, 'html_full_len': len(h),
                      'html_truncated': False})
    blob = json.dumps({'key': str(inn), 'site': sayt,
                       'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
                       'pages_dropped': len(otkazy or []), 'otkazy': (otkazy or []),
                       'pages': pages,
                       'text': '', 'istochnik': 'zenno', 'kanal': _kanal(inn)},
                      ensure_ascii=False).encode('utf-8')
    tmp = put + '.part'
    with gzip.open(tmp, 'wb') as f:
        f.write(blob)
    os.replace(tmp, put)
    return len(pages)


def priyom():
    """Разобрать всё готовое: страницы -> кэш, файлы -> razobrano.

    Каталог читаем ОДИН раз и раскладываем по ИНН. Раньше на каждую компанию
    делалось ещё два os.listdir — на проверку свежести и на перенос, — и разбор
    получался квадратичным по числу файлов. При 764 файлах в gotovo цикл успевал
    10-14 компаний за 120 секунд, а Зенка на десяти потоках приносила примерно
    тысячу в час: очередь разбора росла быстрее, чем разбиралась.
    """
    _papki()
    ГОДНЫЕ = ('.html', '.urls.txt', '.kanal.txt', '.otkaz.txt')
    по_inn, теперь = {}, time.time()
    with os.scandir(GOTOVO) as it:
        for e in it:
            if not e.is_file():
                continue
            inn = e.name.split('.')[0].split('_')[0]
            if not inn.isdigit():
                continue
            try:
                mt = e.stat().st_mtime
            except OSError:
                mt = теперь
            зап = по_inn.setdefault(inn, {'файлы': [], 'свежий': False, 'годен': False})
            зап['файлы'].append(e.name)
            if теперь - mt < 20:
                зап['свежий'] = True          # файл может дописываться прямо сейчас
            if e.name.endswith(ГОДНЫЕ):
                зап['годен'] = True
    itog = {'компаний': 0, 'страниц': 0, 'пустых': 0, 'ошибок': 0}
    for inn in sorted(по_inn):
        зап = по_inn[inn]
        if not зап['годен'] or зап['свежий']:
            continue
        try:
            stranicy = _sobrat(inn)
            if not stranicy:
                itog['пустых'] += 1
            else:
                itog['страниц'] += _v_kesh(inn, stranicy, _otkazy(inn))
                itog['компаний'] += 1
            for n in зап['файлы']:
                try:
                    shutil.move(os.path.join(GOTOVO, n), os.path.join(RAZOBRANO, n))
                except OSError:
                    pass          # уже унесён или занят — не роняем весь круг
        except Exception as e:  # noqa: BLE001
            itog['ошибок'] += 1
            itog.setdefault('примеры_ошибок', []).append('%s: %s' % (inn, str(e)[:80]))
    return itog


def _metku(put, znachenie):
    """Запомнить, до какого времени кэш уже осмотрен."""
    try:
        with open(put, 'w', encoding='utf-8') as f:
            f.write(str(znachenie))
            f.flush()
            os.fsync(f.fileno())
    except Exception:  # noqa: BLE001
        pass


def dorabotka(predel=200):
    """Разобрать компании, чьи страницы Зенка уже положила в кэш.

    Без этого шага мост работает в стол: замер 13.08 показал 29 компаний со
    страницами в кэше, переобогащено 0, почт в базе 0. Приёмник кладёт HTML —
    и на этом всё, разбор никто не звал.

    Запускаем обычный enrich_contacts по списку таких ИНН ОТДЕЛЬНЫМ процессом
    (раннер режет задания по 30 минут) и с NO_DOLPHIN=1: страницы уже на диске,
    поднимать профили незачем.
    """
    # ХОЛД ВЛАДЕЛЬЦА (19.08 «без использования провайдера и хмлривера пока что»,
    # 20.08 xmlriver разрешён, провайдер — нет). Этот путь мимо холда проскочил:
    # HOLD-FAKTY.flag гасил fakty_cikl, а разбор моста поднимает enrich_contacts
    # с extract_model=gpt-5.6-luna, то есть тоже ходит к провайдеру. Замер 20.08
    # по хвосту zenno_razbor.jsonl: 253 записи из 338 с extract='provider'.
    if os.path.exists(os.path.join(DIR, 'HOLD-FAKTY.flag')):
        return {'холд_провайдера': 'HOLD-FAKTY.flag — разбор не поднимаем'}
    _papki()
    # СКАНИРУЕМ ТОЛЬКО НОВОЕ. Раньше каждый круг разжимал ВЕСЬ кэш: на 23 636
    # карточках это тысячи gzip-распаковок в минуту, и цена росла вместе с
    # кэшем — к 75 тысячам круг встал бы намертво. Метка хранит время последнего
    # осмотра, и берутся только файлы свежее неё (с запасом в пять минут на
    # файлы, дописанные ровно в момент прошлого прохода).
    метка = os.path.join(ZENNO, 'dorabotka.metka')
    рубеж = 0.0
    try:
        рубеж = float(open(метка, encoding='utf-8').read().strip() or 0) - 300
    except Exception:  # noqa: BLE001
        рубеж = 0.0          # первый заход — осматриваем всё, дальше только новое
    svezhie, самое_свежее = [], рубеж
    with os.scandir(KESH) as it:
        for e in it:
            if not e.name.endswith('.json.gz'):
                continue
            try:
                mt = e.stat().st_mtime
            except OSError:
                continue
            самое_свежее = max(самое_свежее, mt)
            if mt < рубеж:
                continue
            try:
                with gzip.open(e.path, 'rb') as f:
                    d = json.loads(f.read().decode('utf-8', 'replace'))
            except Exception:  # noqa: BLE001
                continue
            if d.get('istochnik') != 'zenno' or not (d.get('pages') or []):
                continue
            inn = str(d.get('key') or '')
            if inn.isdigit():
                svezhie.append((inn, d.get('ts') or ''))
    if not svezhie:
        _metku(метка, самое_свежее)
        return {'нечего_разбирать': True}

    c = sqlite3.connect(BD)
    c.row_factory = sqlite3.Row
    nuzhno = []
    for inn, ts in svezhie:
        r = c.execute("select coalesce(updated_at,'') u from companies where inn=?",
                      (inn,)).fetchone()
        # разбираем, если компании ещё не трогали ПОСЛЕ прихода страниц
        if not r or not r['u'] or (ts and r['u'] < ts):
            nuzhno.append(inn)
    c.close()
    # Метку двигаем ТОЛЬКО когда окно разобрано целиком. Иначе компания,
    # отсечённая пределом, ушла бы за метку и не вернулась бы никогда.
    хвост_остался = len(nuzhno) > predel
    nuzhno = nuzhno[:predel]
    if not хвост_остался:
        _metku(метка, самое_свежее)
    if not nuzhno:
        return {'все_уже_разобраны': len(svezhie)}

    # данные компаний берём из базы обзвона — тот же вход, что у обычного прогона
    o = sqlite3.connect(os.environ.get('OBZVON_DB', r'C:\sender\obzvon-index.db'))
    o.row_factory = sqlite3.Row
    q = ','.join('?' * len(nuzhno))
    komp = []
    for r in o.execute(
            "select inn, name_short, name_full, ogrn, region, address, okved_main, "
            "coalesce(phones_base,'') p, coalesce(sites,'') s, division "
            "from obzvon where inn in (%s)" % q, nuzhno):
        komp.append({'inn': str(r['inn']), 'name': r['name_short'] or r['name_full'],
                     'ogrn': str(r['ogrn'] or ''), 'city': (r['region'] or '')[:40],
                     'region': r['region'], 'address': r['address'],
                     'okved': r['okved_main'], 'division': r['division'] or 'kc',
                     'phones': [x for x in r['p'].split(';') if x][:5],
                     'base_site': (r['s'] or '').split(';')[0].strip()})
    o.close()
    if not komp:
        return {'в_базе_обзвона_не_нашлись': len(nuzhno)}

    fajl = os.path.join(ZENNO, 'dorabotka.json')
    with open(fajl, 'w', encoding='utf-8') as f:
        json.dump(komp, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    # mass_base СЮДА НЕЛЬЗЯ (поймано 13.08): этот флаг в main() значит «взять всю
    # базу no-site», и он перебивает companies_file — процесс ушёл молотить 119 330
    # компаний вместо наших 58. Модель для ролей задаём явным ключом.
    zadanie = {'companies_file': fajl, 'stream_file': 'zenno_razbor.jsonl',
               'workers': 8, 'channels': 4, 'browser_workers': 1,
               'source': 'zenno', 'extract_model': 'gpt-5.6-luna',
               'write_db': True}
    zfile = os.path.join(ZENNO, 'dorabotka_zadanie.json')
    open(zfile, 'w', encoding='utf-8').write(json.dumps(zadanie, ensure_ascii=False))

    import subprocess
    # ОДИН разбор за раз. Демон зовёт dorabotka по расписанию, и без этой проверки
    # каждый вызов поднимал НОВЫЙ процесс: за час набралось десять, они съели
    # процессор, который мы только что освобождали под Зенку.
    zamok = os.path.join(ZENNO, 'razbor.pid')
    # ЗАМОК ДОЛЖЕН ОТПУСКАТЬ ЗАВИСШИХ. Первая версия проверяла только «процесс
    # жив» — и когда разбор завис (13.08: молчал 74 минуты, журнал не рос),
    # демон каждый круг честно писал «разбор уже идёт» и не поднимал новый.
    # Живость меряем по РАБОТЕ, а не по наличию процесса: если dorabotka.out не
    # менялся дольше RAZBOR_MOLCHIT_MIN, процесс считается мёртвым и снимается.
    molchit_predel = float(os.environ.get('RAZBOR_MOLCHIT_MIN', '20'))
    # ЖИВОСТЬ МЕРЯЕМ ПО ПОТОКУ РЕЗУЛЬТАТА, А НЕ ПО STDOUT. Первая версия смотрела
    # на dorabotka.out — а туда попадает только итоговый JSON в конце прогона,
    # то есть здоровый разбор двух сотен компаний выглядел бы «молчащим» и его
    # снимали бы каждые 20 минут. zenno_razbor.jsonl прирастает на КАЖДОЙ
    # компании, это честный пульс.
    log_put = os.path.join(DIR, 'zenno_razbor.jsonl')
    try:
        if os.path.exists(zamok):
            staryy = int(open(zamok, encoding='utf-8').read().strip() or 0)
            if staryy:
                r = subprocess.run(['tasklist', '/FI', 'PID eq %d' % staryy],
                                   capture_output=True, text=True, timeout=60)
                zhiv = str(staryy) in (r.stdout or '')
                molchit = 999.0
                try:
                    molchit = (time.time() - os.path.getmtime(log_put)) / 60
                except OSError:
                    pass
                if zhiv and molchit < molchit_predel:
                    return {'разбор_уже_идёт': staryy,
                            'молчит_мин': round(molchit, 1)}
                if zhiv:
                    subprocess.run(['taskkill', '/PID', str(staryy), '/T', '/F'],
                                   capture_output=True, text=True, timeout=60)
    except Exception:  # noqa: BLE001
        pass
    sreda = dict(os.environ, NO_DOLPHIN='1')
    log = open(os.path.join(ZENNO, 'dorabotka.out'), 'ab')
    p = subprocess.Popen([sys.executable, os.path.join(DIR, 'enrich_contacts.py')],
                         stdin=open(zfile, 'rb'), stdout=log, stderr=log,
                         cwd=DIR, env=sreda,
                         creationflags=(0x00000008 | 0x00000200) if os.name == 'nt' else 0)
    try:
        with open(zamok, 'w', encoding='utf-8') as f:
            f.write(str(p.pid))
            f.flush()
            os.fsync(f.fileno())
    except Exception:  # noqa: BLE001
        pass
    return {'запущен_разбор': p.pid, 'компаний': len(komp),
            'журнал': 'zenno_razbor.jsonl'}


def storozh(tishina_min=15):
    """Идёт ли Зенка вообще. Возвращает состояние и, если надо, поднимает ZennoPoster.

    Владелец 13.08: «пока он стоит — очередь копится, но не разбирается». Мост
    видит это раньше человека: очередь не пуста, а в gotovo и razobrano за
    tishina_min минут ничего не прибавилось — значит шаблон не крутится.
    Сам ZennoPoster поднимаем, только если его процесса нет вовсе; запускать
    внутри него задачу из командной строки нечем (TasksRunner ключей не отдаёт),
    поэтому расписание проекта остаётся на операторе — но молчание он увидит.
    """
    _papki()
    posledniy = 0.0
    for p in (GOTOVO, RAZOBRANO):
        try:
            for n in os.listdir(p):
                t = os.path.getmtime(os.path.join(p, n))
                posledniy = max(posledniy, t)
        except Exception:  # noqa: BLE001
            pass
    v_ocheredi = 0
    if os.path.exists(OCHERED):
        with open(OCHERED, encoding='utf-8-sig', errors='replace') as f:
            v_ocheredi = sum(1 for s in f if s.strip())
    tishina = (time.time() - posledniy) / 60 if posledniy else 999

    zhiv = False
    try:
        import subprocess
        r = subprocess.run(['powershell', '-NoProfile', '-Command',
                            "@(Get-Process ZennoPoster -ErrorAction SilentlyContinue).Count"],
                           capture_output=True, text=True, timeout=60)
        zhiv = (r.stdout or '0').strip() not in ('0', '')
    except Exception:  # noqa: BLE001
        pass

    itog = {'в_очереди': v_ocheredi, 'тишина_мин': round(tishina, 1),
            'ZennoPoster_запущен': zhiv}
    if v_ocheredi and tishina > tishina_min:
        itog['ТРЕВОГА'] = ('очередь %d, а результата нет %d мин — шаблон не крутится'
                           % (v_ocheredi, int(tishina)))
        with open(os.path.join(ZENNO, 'zenka-stoit.txt'), 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M'), itog['ТРЕВОГА']))
            f.flush()
            os.fsync(f.fileno())
        if not zhiv:
            try:
                import subprocess
                exe = (r'C:\Program Files\ZennoLab\RU\ZennoPoster Pro V7'
                       r'\7.9.0.0\Progs\ZennoPoster.exe')
                if os.path.exists(exe):
                    subprocess.Popen([exe], creationflags=0x00000008)
                    itog['ZennoPoster_запущен_нами'] = True
            except Exception as e:  # noqa: BLE001
                itog['запустить_не_вышло'] = str(e)[:100]
    return itog


def stat():
    _papki()
    def _n(p, hvost=''):
        try:
            return len([x for x in os.listdir(p) if x.endswith(hvost)])
        except Exception:  # noqa: BLE001
            return 0
    ochered_n = 0
    if os.path.exists(OCHERED):
        with open(OCHERED, encoding='utf-8', errors='replace') as f:
            ochered_n = sum(1 for s in f if s.strip())
    return {'в_очереди_строк': ochered_n, 'отдано_всего': len(_otdannye()),
            'в_gotovo_файлов': _n(GOTOVO), 'разобрано_файлов': _n(RAZOBRANO),
            'кэш_файлов': _n(KESH, '.json.gz'), 'пути': {'очередь': OCHERED,
            'готово': GOTOVO, 'кэш': KESH}}


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        print(json.dumps(stat(), ensure_ascii=False, indent=1))
        return 0
    if a[0] == '--pereobhod':
        print(json.dumps(pereobhod(int(a[1]) if len(a) > 1 else 400),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--povtor':
        print(json.dumps(povtor_nezashedshih(
            int(a[1]) if len(a) > 1 else 700), ensure_ascii=False, indent=1))
    elif a[0] == '--ochered':
        n = int(a[1]) if len(a) > 1 else 500
        print(json.dumps(ochered(n), ensure_ascii=False, indent=1))
        return 0
    if a[0] == '--priyom':
        print(json.dumps(priyom(), ensure_ascii=False, indent=1))
        return 0
    if a[0] == '--storozh':
        print(json.dumps(storozh(), ensure_ascii=False, indent=1))
        return 0
    if a[0] == '--dorabotka':
        print(json.dumps(dorabotka(int(a[1]) if len(a) > 1 else 200),
                         ensure_ascii=False, indent=1))
        return 0
    if a[0] == '--demon':
        pauza = int(a[1]) if len(a) > 1 else 120
        posledniy_razbor = 0.0
        while True:
            try:
                # ПОПОЛНЕНИЕ — ТОЛЬКО КОГДА ОЧЕРЕДЬ ПОДХОДИТ К КОНЦУ. Замер
                # 23.08: каждый круг наполнитель просматривал 35 436 кандидатов
                # и дописывал НОЛЬ — все давно отданы, — а приём из-за этого шёл
                # рвано: паузы по пятнадцать минут между кругами при живой
                # Зенке. Когда в очереди сорок восемь тысяч строк, искать новых
                # незачем; порог держим в переменной, чтобы менять без правки.
                длина = _dlina_ocheredi()
                if длина >= ПОРОГ_ПОПОЛНЕНИЯ:
                    o = {'пополнение_отложено': длина}
                else:
                    o = ochered(300)
                    # НОВЫХ КОМПАНИЙ БОЛЬШЕ НЕТ — идём вторым кругом по уже
                    # обойдённым, новым приоритетом разделов (владелец 14.08)
                    if not o.get('дописано') and длина < 150:
                        o['переобход'] = pereobhod(300)
                p = priyom()
                d = None
                # разбор — не чаще раза в 10 минут и только если разбирать есть что:
                # каждый запуск поднимает свой процесс обогащения, частить незачем
                if time.time() - posledniy_razbor > 600:
                    d = dorabotka(200)
                    if d.get('запущен_разбор'):
                        posledniy_razbor = time.time()
                st = storozh()
                print(json.dumps({'время': time.strftime('%H:%M:%S'),
                                  'очередь': o, 'приём': p, 'разбор': d,
                                  'сторож': st},
                                 ensure_ascii=False), flush=True)
            except Exception as e:  # noqa: BLE001
                print('сбой цикла: %s' % str(e)[:150], flush=True)
            time.sleep(pauza)
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
