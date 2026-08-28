# -*- coding: utf-8 -*-
r"""Третья фаза: вытащить ФИО и должности к адресам, снятым из кэша.

Владелец 27.08: «разбор контактов с фамилиями тоже через провайдера с запасной
моделью хайки, когда разберёт — обновим уже роль, допишем тем, кто с фамилиями».

Регулярка дала роль только по имени ящика: из 35 988 записанных адресов
опознано 6 508 (sales, zakupki, buh, приёмная, кадры, техконтакт), у 29 480 роль
пуста. Пустая — это чаще всего личный ящик вида `ivanov@`, `a.petrova@`: там и
сидят нужные люди, но кто именно, из адреса не видно. Их читает модель по той же
странице, с которой адрес снят.

ЧТО ОТДАЁМ МОДЕЛИ. Не весь сайт, а текст страницы контактов — очищенный от
разметки кусок вокруг адресов. Просим строго: ФИО и должность ТОЛЬКО если они
стоят рядом с этим адресом на странице. Придумывать нельзя — цена выдумки
здесь высокая: имя уходит в обращение письма.

ЗАПАСНАЯ МОДЕЛЬ. Основная — та же, что у обходчика; при её недоступности
gen_provider сам переводит вызов на `claude-haiku-4-5` и пишет подмену в журнал.

Роль от модели НЕ ПОНИЖАЕТ уже известную: add_email хранит правило «роль общего
ящика — это заход, а не владелец», и мы его не обходим.

ПОРЯДОК И ПОТОКИ. Калибровка на тридцати компаниях дала 1,2 компании в минуту:
вызов провайдера идёт полминуты, и последовательно 15 498 компаний уехали бы за
девять суток. Зовём в несколько потоков, а пишем из одного — база не любит
параллельных писателей. Первыми идут те, кому письмо уйдёт раньше: направление
Meyer и все, кто уже лежит в рассылке.

    python fio_iz_kesha.py --predel 30      калибровка на тридцати компаниях
    python fio_iz_kesha.py --potokov 8      весь остаток в восемь потоков
    python fio_iz_kesha.py --tolko-meyer    только направление Meyer
"""
import gzip
import json
import os
import queue
import re
import sqlite3
import sys
import threading
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault('NO_BROWSER', '1')

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ЖУРНАЛ = r'C:\sender\_tmp\fio-iz-kesha.jsonl'
МОДЕЛЬ = os.environ.get('FIO_MODEL', 'gpt-5.6-luna')
# Сколько адресов влезает в один запрос. Больше — промпт распухает и модель
# начинает терять строки; у кого адресов больше, тот получает несколько вызовов.
ПРЕДЕЛ_АДРЕСОВ = 20
# Запасная модель по слову владельца: «с запасной моделью хайки».
ЗАПАСНАЯ = os.environ.get('FIO_MODEL_ZAPAS', 'claude-haiku-4-5')

PROMPT = """Со страницы контактов предприятия «%(name)s» выпиши, кому принадлежат
адреса электронной почты.

Правила, они важнее полноты:
- ФИО и должность бери ТОЛЬКО если они стоят на странице рядом с этим адресом;
- не догадывайся по имени ящика: «ivanov@» — это не доказательство, что там Иванов;
- если рядом с адресом ничего нет, верни его с пустыми полями;
- должность пиши как на странице, своими словами не переписывай;
- отделов и общих ящиков (info, sales, zakupki) это тоже касается: у них
  «должность» — название отдела, ФИО пустое.

Адреса, которые нас интересуют:
%(adresa)s

Текст страницы:
%(tekst)s

Ответь ТОЛЬКО JSON, без единого слова до и после него. Ничего не нашёл —
верни ровно {"kontakty": []} и на этом закончи.
{"kontakty": [{"email": "...", "fio": "Фамилия Имя Отчество или пусто",
"dolzhnost": "как на странице или пусто", "ryadom": "дословный кусок страницы,
где адрес стоит рядом с ФИО, или пусто"}]}"""

_ТЕГИ = re.compile(r'<(script|style|noscript)[^>]*>.*?</\1>', re.S | re.I)
_ПОЧТА = re.compile(r'[\w.+-]+@[\w.-]+\.\w{2,6}')


def _tekst_stranicy(инн, урлы):
    """Текст тех страниц кэша, на которых стоят наши адреса."""
    п = os.path.join(KESH, инн + '.json.gz')
    if not os.path.exists(п):
        return ''
    try:
        with gzip.open(п, 'rt', encoding='utf-8', errors='replace') as f:
            дан = json.load(f)
    except Exception:  # noqa: BLE001
        return ''
    куски = []
    for стр in (дан.get('pages') or дан.get('stranicy') or []):
        у = str((стр or {}).get('url') or '')
        if урлы and у not in урлы:
            continue
        h = str((стр or {}).get('html') or (стр or {}).get('text') or '')
        h = _ТЕГИ.sub(' ', h)
        h = re.sub(r'<[^>]+>', ' ', h)
        h = re.sub(r'&nbsp;|&mdash;|&laquo;|&raquo;', ' ', h)
        куски.append(re.sub(r'[ \t\u00a0]+', ' ', h).strip())
    текст = '\n\n'.join(куски)
    return текст[:14000]


def _celi(predel=None, tolko_meyer=False):
    """Компании, у которых есть адрес из кэша без роли и без имени."""
    сделано = set()
    if os.path.exists(ЖУРНАЛ):
        with open(ЖУРНАЛ, encoding='utf-8', errors='replace') as f:
            for s in f:
                try:
                    з = json.loads(s)
                except Exception:  # noqa: BLE001
                    continue
                if not з.get('сбой'):
                    сделано.add(str(з['инн']))
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    усл = ("select e.inn, e.email, coalesce(e.source_url,'') u, "
           "coalesce(k.name,'') nm from emails e join companies k on k.inn=e.inn "
           "where coalesce(e.pometka,'') like '%кэш-добор%' "
           "and coalesce(e.role,'')='' and coalesce(e.person,'')=''")
    if tolko_meyer:
        усл += " and k.division like '%meyer%'"
    по_инн = {}
    for r in c.execute(усл):
        и = str(r[0])
        if и in сделано:
            continue
        по_инн.setdefault(и, {'name': r[3], 'адреса': [], 'урлы': set()})
        по_инн[и]['адреса'].append(r[1])
        if r[2]:
            по_инн[и]['урлы'].add(r[2])
    # ПОРЯДОК ПО СРОЧНОСТИ: сперва те, кому письмо уйдёт раньше.
    важные = set()
    try:
        s_ = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
        важные = {''.join(ch for ch in str(r[0]) if ch.isdigit())
                  for r in s_.execute('select inn from recipients '
                                      'where inn is not null')}
        s_.close()
    except Exception:  # noqa: BLE001
        pass
    мейер = set()
    c2 = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    мейер = {str(r[0]) for r in c2.execute(
        "select inn from companies where division like '%meyer%'")}
    c2.close()
    c.close()

    def вес(п):
        и = п[0]
        return (0 if и in мейер else 1, 0 if и in важные else 1, и)

    цели = sorted(по_инн.items(), key=вес)
    return цели[:predel] if predel else цели


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    предел = None
    if '--predel' in sys.argv:
        предел = int(sys.argv[sys.argv.index('--predel') + 1])
    цели = _celi(предел, '--tolko-meyer' in sys.argv)
    d = {'компаний_к_разбору': len(цели),
         'адресов': sum(len(x[1]['адреса']) for x in цели), 'модель': МОДЕЛЬ}
    if not цели:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0

    import enrich_db as EDB
    import gen_provider as GP

    потоков = 1
    if '--potokov' in sys.argv:
        потоков = max(1, min(12, int(sys.argv[sys.argv.index('--potokov') + 1])))
    d['потоков'] = потоков
    клиент = GP.make_client()
    # ОТКРЫТИЕ БАЗЫ ТОЖЕ ЖДЁТ. EnrichDB на конструкторе делает миграции, то есть
    # просит запись, — а рядом работает демон моста и держит замок минутами.
    # Дважды из-за этого разбор молча висел на старте: процесс жив, журнал не
    # растёт, в логе пусто. Теперь ждём явно и говорим об этом в лог.
    db = None
    for попытка in range(60):
        try:
            db = EDB.EnrichDB()
            db.cx.execute('PRAGMA busy_timeout=120000')
            break
        except Exception as e:  # noqa: BLE001
            if 'locked' not in str(e).lower() and 'busy' not in str(e).lower():
                raise
            if попытка % 5 == 0:
                print('база занята, жду открытия [%d/60]' % (попытка + 1),
                      flush=True)
            time.sleep(10)
    if db is None:
        print('база так и не открылась за десять минут', flush=True)
        return 1
    итог = {'разобрано': 0, 'с_фио': 0, 'с_должностью': 0, 'записано_имён': 0,
            'сбоев': 0, 'пусто': 0}
    журнал = open(ЖУРНАЛ, 'a', encoding='utf-8')
    t0 = time.time()
    задачи = queue.Queue()
    готовое = queue.Queue()
    for пара in цели:
        задачи.put(пара)
    замок_журнала = threading.Lock()

    def спросить(инн, зап):
        """Вызовы провайдера по одной компании. Возвращает (инн, находки, сбой).

        ПОЧЕМУ НЕ ОДНИМ ВЫЗОВОМ. Сперва в запрос уходили первые двадцать адресов
        и всё: у 124 компаний из очереди адресов больше, и 2 299 из них молча
        не попадали в разбор — а на следующем заходе их отрезал бы тот же
        потолок, то есть навсегда. Теперь длинный список делится на куски по
        двадцать, текст страницы у них общий и перечитывать его не надо.
        """
        текст = _tekst_stranicy(инн, зап['урлы'])
        if not текст.strip():
            return инн, [], 'нет текста'
        все_адреса = set(зап['адреса'])
        найдено, сбои = [], []
        for нач in range(0, len(зап['адреса']), ПРЕДЕЛ_АДРЕСОВ):
            кусок = зап['адреса'][нач:нач + ПРЕДЕЛ_АДРЕСОВ]
            сооб = [{'role': 'user', 'content': PROMPT % {
                'name': зап['name'][:120],
                'adresa': '\n'.join('- ' + a for a in кусок),
                'tekst': текст}}]
            данные = None
            # ЗОВЁМ СТРИМ НАПРЯМУЮ, минуя GP.call. Через него разбор дважды
            # вставал намертво: в логе «claude-haiku-4-5 молчит», хотя прямая
            # проверка показала, что все три модели отвечают за 2,5 секунды.
            # Виновата не сеть, а обвязка: gen_provider помечает модель
            # «остывшей» на 15 минут после любого молчания и начинает
            # перекидывать вызовы между двумя одинаково «остывшими», а его
            # проверка ответа считает законное {"kontakty": []} обрезанным,
            # потому что модель дописывает после JSON фразу «адрес не найден».
            # Здесь обе беды не нужны: думать не просим, пустой ответ законен,
            # запасная модель — вторым заходом, как и просил владелец.
            for модель in (МОДЕЛЬ, ЗАПАСНАЯ):
                try:
                    о = GP._raw_stream(сооб, модель, 4000, thinking=False,
                                       effort='low')
                    данные = GP.parse_json(о) or {}
                    break
                except Exception as ex:  # noqa: BLE001
                    сбои.append('%s: %s' % (модель, str(ex)[:60]))
            if данные is None:
                continue
            for к in (данные.get('kontakty') or []):
                адрес = str(к.get('email') or '').strip().lower()
                фио = str(к.get('fio') or '').strip()
                должн = str(к.get('dolzhnost') or '').strip()
                рядом = str(к.get('ryadom') or '').strip()
                if not адрес or адрес not in все_адреса:
                    continue
                # ЦИТАТА ОБЯЗАТЕЛЬНА. Имя без куска страницы, где оно стоит
                # рядом с адресом, — догадка модели по имени ящика, а такое имя
                # уедет в обращение письма. Нет цитаты — нет имени.
                if фио and (not рядом
                            or фио.split()[0].lower() not in рядом.lower()):
                    фио = ''
                if фио or должн:
                    найдено.append((адрес, фио, должн))
        if сбои and not найдено:
            return инн, [], сбои[0]
        return инн, найдено, ''

    def работник():
        while True:
            try:
                инн, зап = задачи.get_nowait()
            except queue.Empty:
                return
            готовое.put(спросить(инн, зап))
            задачи.task_done()

    нити = [threading.Thread(target=работник, daemon=True)
            for _ in range(потоков)]
    for н in нити:
        н.start()

    # ПИШЕТ ОДИН ПОТОК, И ПИШЕТ ПАЧКАМИ. Сперва каждый найденный человек шёл в
    # базу отдельным add_email с тридцатью повторами по замку — и весь конвейер
    # упирался в это: шлюз отдавал 70 ответов в минуту, а в журнал ложилось
    # полторы компании. Теперь ответ сразу отмечается в журнале, находки копятся
    # в буфере, а в базу уходят одной транзакцией на сотню адресов.
    настоящее = db.cx
    настоящий_commit = настоящее.commit

    class _БезКоммита:
        """Соединение, глотающее commit: пачку фиксируем сами."""

        def __init__(self, cx):
            object.__setattr__(self, '_cx', cx)

        def commit(self):
            return None

        def __getattr__(self, имя):
            return getattr(self._cx, имя)

    db.cx = _БезКоммита(настоящее)

    # ЗАПИСЬ — ОТДЕЛЬНАЯ НИТЬ. Пока слив шёл прямо в главном потоке, он вставал
    # на замке базы вместе со всем конвейером: 44 компании в минуту, потом пять
    # минут тишины, потом снова. Теперь главный поток только принимает ответы и
    # ведёт журнал, а писарь копит и сливает в своём темпе.
    на_запись = queue.Queue()
    стоп_записи = threading.Event()

    def писарь():
        буфер = []

        def слить():
            if not буфер:
                return
            for попытка in range(30):
                try:
                    for инн_, адрес_, фио_, должн_ in буфер:
                        db.add_email(инн_, адрес_, role=должн_, person=фио_,
                                     source='кэш-добор', pometka='кэш-добор фио')
                    настоящий_commit()
                    итог['записано_имён'] += len(буфер)
                    буфер.clear()
                    return
                except Exception as e:  # noqa: BLE001
                    if ('locked' not in str(e).lower()
                            and 'busy' not in str(e).lower()):
                        raise
                    try:
                        настоящее.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                    time.sleep(min(10, 2 + попытка))
            итог['сбоев_записи'] = итог.get('сбоев_записи', 0) + len(буфер)
            буфер.clear()

        while not (стоп_записи.is_set() and на_запись.empty()):
            try:
                буфер.append(на_запись.get(timeout=5))
            except queue.Empty:
                слить()
                continue
            if len(буфер) >= 100:
                слить()
        слить()

    нить_записи = threading.Thread(target=писарь, daemon=True)
    нить_записи.start()

    всего = len(цели)
    получено = 0
    while получено < всего:
        try:
            инн, найдено, сбой = готовое.get(timeout=300)
        except queue.Empty:
            if not any(н.is_alive() for н in нити):
                break
            continue
        получено += 1
        # ЖУРНАЛ ПЕРВЫМ. Он и есть точка резюма: компания, чей ответ получен,
        # не должна переспрашиваться из-за того, что база была занята.
        with замок_журнала:
            журнал.write(json.dumps(
                {'инн': инн, 'сбой': сбой} if сбой else
                {'инн': инн, 'найдено': [[a, f, p] for a, f, p in найдено],
                 'ts': time.strftime('%H:%M:%S')}, ensure_ascii=False) + '\n')
            журнал.flush()
        if сбой:
            итог['сбоев' if сбой != 'нет текста' else 'пусто'] += 1
            continue
        for адрес, фио, должн in найдено:
            if фио:
                итог['с_фио'] += 1
            if должн:
                итог['с_должностью'] += 1
            на_запись.put((инн, адрес, фио, должн))
        итог['разобрано'] += 1
        if итог['разобрано'] % 200 == 0:
            os.fsync(журнал.fileno())
            print(json.dumps({'секунд': round(time.time() - t0), **итог},
                             ensure_ascii=False), flush=True)
    стоп_записи.set()
    нить_записи.join(timeout=600)
    db.cx = настоящее
    журнал.close()
    db.cx.close()
    итог['секунд'] = round(time.time() - t0)
    d['итог'] = итог
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
