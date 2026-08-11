# -*- coding: utf-8 -*-
"""Ядро панели обогащения — вся логика БЕЗ веб-стека (тестируется pytest'ом напрямую).

Зачем отдельный модуль: FastAPI-слой (enrich_panel.py) должен оставаться тонким —
парсинг файлов, валидация ИНН, нарезка батчей, подпись заданий и расчёт прогресса
не зависят от HTTP и проверяются юнит-тестами без запуска сервера.

Ключевые принципы (канон проекта, см. job_runner.py / enrich_db.py):
  * Задания ставятся ЧЕРЕЗ ГОТОВУЮ ОЧЕРЕДЬ раннера: job-<id>.json на дроп с
    HMAC-подписью (JOB_SECRET) — панель НЕ зовёт enrich_contacts напрямую и не
    городит свою очередь. Формат/подпись байт-в-байт как run_on_server.submit().
  * Источник истины прогресса — stage_log в enrich.db: там только УСПЕШНО
    завершённые стадии. Рестарт панели/сервера картину не теряет.
  * Идемпотентность: и «Запустить», и «Докинуть» отбирают строки БЕЗ нужной
    стадии — повторное нажатие не дублирует уже сделанную работу.
"""
import csv
import hashlib
import hmac
import io
import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Конфигурация через окружение (дефолты — боевые пути Windows-сервера)
# ---------------------------------------------------------------------------

def _env(name, default=''):
    return os.environ.get(name, default)


def enrich_db_path():
    """Путь к enrich.db — тот же дефолт, что у enrich_db.py на сервере."""
    return _env('ENRICH_DB', os.path.join(_env('SENDER_DIR', r'C:\sender'), 'enrich.db'))


def uploads_dir():
    """Куда класть загруженные файлы. Требование безопасности: имена генерим сами,
    пользовательское имя файла в путь НЕ попадает (только расширение по whitelist)."""
    return _env('ENRICH_UPLOADS', r'C:\sender\enrich_uploads')


def obzvon_index_path():
    """Путь к индексу базы обзвона (строит sender/tools/build_obzvon_index.py,
    схема — company_card.build_obzvon_index). Канон путей как у enrich_db_path:
    env-переопределение + SENDER_DIR-дефолт; имя переменной OBZVON_INDEX — то же,
    что уже использует sender/tools/dryrun_basemerge.py."""
    return _env('OBZVON_INDEX',
                os.path.join(_env('SENDER_DIR', r'C:\sender'), 'obzvon-index.db'))


def load_runner_env(path=None):
    """Подхватить runner-secrets.env (DROP_URL/DROP_TOKEN/JOB_SECRET) в os.environ.
    Та же семантика, что у job_runner._load_env_file: не перетираем уже заданное,
    плейсхолдеры «<...>» пропускаем. Нужно, чтобы служба панели жила с той же
    ключницей, что и раннер, без дублирования секретов."""
    p = path or _env('RUNNER_ENV', r'C:\sender\server\runner-secrets.env')
    if not os.path.exists(p):
        return
    for line in open(p, encoding='utf-8-sig'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip()
        if k and v and not v.startswith('<') and k not in os.environ:
            os.environ[k] = v


# ---------------------------------------------------------------------------
# Парсинг загруженного файла (CSV ; или , / XLSX) и валидация ИНН
# ---------------------------------------------------------------------------

MAX_BYTES = 10 * 1024 * 1024   # лимит размера файла — защита от случайного гигабайта
MAX_ROWS = 5000                # лимит строк — батчей и так сотни, больше не тянем за раз

# Алиасы заголовков (сравнение без регистра): выгрузки бывают из разных систем
INN_ALIASES = {'инн', 'inn'}
NAME_ALIASES = {'название', 'name', 'наименование', 'краткое', 'краткое наименование',
                'компания', 'company'}

_INN_RE = re.compile(r'^\d{10}$|^\d{12}$')


def _cell_str(v):
    """Ячейка -> строка. Excel хранит ИНН числом (7701234567.0) — приводим к целому,
    иначе валидный ИНН отбрасывался бы как «не цифры»."""
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def norm_inn(v):
    """Нормализованный ИНН или '' (если не 10/12 цифр). Пробелы/NBSP чистим:
    копипаст из Excel их часто тащит."""
    s = _cell_str(v).replace(' ', '').replace('\u00a0', '')
    if s.endswith('.0'):
        s = s[:-2]
    return s if _INN_RE.match(s) else ''


def _find_header(rows):
    """Ищем строку заголовков в первых 5 строках (шапки выгрузок бывают не первой
    строкой). Возврат: (индекс строки, колонка ИНН, колонка названия) или None."""
    for ri, row in enumerate(rows[:5]):
        cells = [_cell_str(c).lower() for c in row]
        inn_col = name_col = None
        for ci, c in enumerate(cells):
            if c in INN_ALIASES and inn_col is None:
                inn_col = ci
            if c in NAME_ALIASES and name_col is None:
                name_col = ci
        if inn_col is not None and name_col is not None:
            return ri, inn_col, name_col
    return None


def _rows_from_csv(blob):
    """CSV: кодировка utf-8(-sig) или cp1251 (Windows-выгрузки), разделитель — тот,
    которого в первой строке больше (; против ,)."""
    try:
        text = blob.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = blob.decode('cp1251', errors='replace')
    first = text.splitlines()[0] if text.splitlines() else ''
    delim = ';' if first.count(';') >= first.count(',') else ','
    return list(csv.reader(io.StringIO(text), delimiter=delim))


def _rows_from_xlsx(blob):
    import openpyxl  # на сервере есть; импорт локальный, чтобы CSV работал и без него
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def parse_companies_file(filename, blob):
    """Разбор файла со списком компаний.

    Возврат: {'accepted': [{'inn','name'}...], 'rejected': [{'row','inn','name','reason'}...],
              'error': '' | 'текст фатальной ошибки'}
    «Отброшено и почему» — по каждой строке, чтобы оператор мог поправить файл.
    """
    out = {'accepted': [], 'rejected': [], 'error': ''}
    if len(blob) > MAX_BYTES:
        out['error'] = f'Файл больше лимита {MAX_BYTES // (1024 * 1024)} МБ'
        return out
    ext = os.path.splitext(filename or '')[1].lower()
    try:
        if ext == '.xlsx':
            rows = _rows_from_xlsx(blob)
        elif ext == '.csv':
            rows = _rows_from_csv(blob)
        else:
            out['error'] = 'Поддерживаются только .csv и .xlsx'
            return out
    except Exception as e:  # noqa: BLE001 — битый файл не должен ронять панель
        out['error'] = f'Не удалось разобрать файл: {str(e)[:120]}'
        return out
    hdr = _find_header(rows)
    if hdr is None:
        out['error'] = ('Не найдены колонки ИНН и Название '
                        '(алиасы: инн/inn, название/name/Наименование)')
        return out
    hrow, ic, nc = hdr
    seen = {}                       # ИНН -> номер строки первого вхождения (для отчёта)
    over_limit = 0
    for i, row in enumerate(rows[hrow + 1:], start=hrow + 2):   # 1-based как в Excel
        raw_inn = _cell_str(row[ic]) if ic < len(row) else ''
        name = _cell_str(row[nc]) if nc < len(row) else ''
        if not raw_inn and not name:
            continue                # полностью пустые строки молча пропускаем
        if len(out['accepted']) >= MAX_ROWS:
            over_limit += 1
            continue
        inn = norm_inn(raw_inn)
        if not inn:
            out['rejected'].append({'row': i, 'inn': raw_inn[:20], 'name': name[:60],
                                    'reason': 'ИНН не 10/12 цифр'})
            continue
        if not name:
            out['rejected'].append({'row': i, 'inn': inn, 'name': '',
                                    'reason': 'пустое название'})
            continue
        if inn in seen:
            out['rejected'].append({'row': i, 'inn': inn, 'name': name[:60],
                                    'reason': f'дубль ИНН (строка {seen[inn]})'})
            continue
        seen[inn] = i
        out['accepted'].append({'inn': inn, 'name': name})
    if over_limit:
        out['rejected'].append({'row': 0, 'inn': '', 'name': '',
                                'reason': f'превышен лимит {MAX_ROWS} строк — '
                                          f'отброшено ещё {over_limit}'})
    return out


# ---------------------------------------------------------------------------
# База обзвона: read-only доступ к obzvon-index.db (страница «База» + выборки)
# ---------------------------------------------------------------------------

# Разбор денег из строк базы. Скопирован из sender-patches/obzvon-pagination/
# services__callbase.py (единый канон разбора денег в проекте): в индексе выручка
# лежит СТРОКОЙ — «Выручка, руб.» это число с пробелами-разделителями
# («123 456 789»), «Выручка» — человекочитаемая («55,3 млрд руб.»), и сравнить
# её в SQL напрямую нельзя.
_MONEY_MULT = {'млрд': 1e9, 'млн': 1e6, 'тыс': 1e3}
_MONEY_RE = re.compile(r'(-?\d[\d\s]*(?:[.,]\d+)?)')


def parse_money(text):
    """«55,3 млрд руб.» -> 55.3e9; «424 тыс. руб.» -> 424000; «0 руб.» -> 0;
    '' -> None. NBSP/узкие пробелы чистим — их тащат выгрузки Checko/Excel."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).replace('\xa0', ' ').replace(' ', ' ').strip()
    if not s:
        return None
    m = _MONEY_RE.search(s)
    if not m:
        return None
    num = float(m.group(1).replace(' ', '').replace(',', '.'))
    for word, k in _MONEY_MULT.items():
        if word in s:
            return num * k
    return num


BASE_PER_PAGE = 50   # строк на страницу списка базы (обзорная таблица, не выгрузка)

# Выручка для WHERE: приоритет «Выручка, руб.» (уже в рублях), фолбэк —
# человекочитаемая «Выручка». parse_money зарегистрирована SQL-функцией,
# поэтому индекс НЕ нужно пересобирать с числовой колонкой.
_REV_SQL = "panel_money(COALESCE(NULLIF(revenue_rub,''), revenue))"


def parse_base_filters(p):
    """query/form -> типизированные фильтры выборки по базе обзвона.

    Мусор в числах молча превращаем в пусто: панель фильтрует, а не валидирует
    ввод оператора (пустой фильтр = «не применять», как в панели обзвона)."""
    def _f(name):
        v = str(p.get(name, '') or '').replace(',', '.').strip()
        try:
            return float(v) if v else None
        except ValueError:
            return None

    def _i(name):
        v = str(p.get(name, '') or '').strip()
        try:
            return max(0, int(float(v))) if v else 0
        except ValueError:
            return 0

    div = str(p.get('division', '') or '').strip().lower()
    email = str(p.get('email', '') or '').strip().lower()
    site = str(p.get('site', '') or '').strip().lower()
    return {
        'rev_min': _f('rev_min'), 'rev_max': _f('rev_max'),   # млн ₽ (канон callbase)
        'tail': _i('tail'),                                    # последние N по порядку базы
        'region': str(p.get('region', '') or '').strip()[:80],
        'division': div if div in ('kc', 'meyer') else '',
        'email': email if email in ('yes', 'no') else '',
        'site': site if site in ('yes', 'no') else '',
        'take': _i('take'),                                    # сколько взять от начала выборки
    }


def filters_qs(f):
    """Фильтры -> query string для ссылок пагинации (только непустые; числа без
    хвоста «.0», чтобы ссылки были человекочитаемыми)."""
    import urllib.parse
    pairs = []
    for k in ('rev_min', 'rev_max', 'tail', 'region', 'division', 'email', 'site'):
        v = f.get(k)
        if v in (None, '', 0):
            continue
        pairs.append((k, ('%g' % v) if isinstance(v, float) else str(v)))
    return urllib.parse.urlencode(pairs)


def filters_label(f, taken):
    """Человекочитаемое имя прогона из фильтров — идёт в колонку «Файл» журнала,
    чтобы в списке прогонов было видно, ЧТО именно выбирали из базы."""
    parts = []
    if f.get('rev_min') is not None and f.get('rev_max') is not None:
        parts.append('выручка %g-%g млн' % (f['rev_min'], f['rev_max']))
    elif f.get('rev_min') is not None:
        parts.append('выручка от %g млн' % f['rev_min'])
    elif f.get('rev_max') is not None:
        parts.append('выручка до %g млн' % f['rev_max'])
    if f.get('tail'):
        parts.append(f'хвост {f["tail"]}')
    if f.get('region'):
        parts.append(f'регион ~{f["region"]}')
    if f.get('division'):
        parts.append(f['division'])
    if f.get('email'):
        parts.append('почта ' + ('есть' if f['email'] == 'yes' else 'нет'))
    if f.get('site'):
        parts.append('сайт ' + ('есть' if f['site'] == 'yes' else 'нет'))
    sel = ', '.join(parts) if parts else 'вся база'
    return f'база обзвона: {sel}; взято {taken}'


class ObzvonDB:
    """Read-only доступ к индексу базы обзвона (obzvon-index.db, таблица obzvon,
    схема — sender/company_card.build_obzvon_index). Панель ТОЛЬКО читает:
    индекс строит/перезаписывает отдельный инструмент, mode=ro (как у
    company_card.ObzvonIndex) страхует от случайной записи."""

    def __init__(self, path=None):
        self.path = path or obzvon_index_path()
        self.cx = None
        if os.path.exists(self.path):
            self.cx = sqlite3.connect(f'file:{self.path}?mode=ro', uri=True,
                                      check_same_thread=False)
            # выручка-строка -> рубли прямо в WHERE (см. _REV_SQL)
            self.cx.create_function('panel_money', 1, parse_money)
            # регистронезависимое вхождение подстроки: lower()/LIKE в стоковом
            # SQLite не понимают кириллицу, поэтому питоновская функция
            self.cx.create_function(
                'panel_contains', 2,
                lambda hay, needle: int(str(needle or '').lower()
                                        in str(hay or '').lower()))

    @property
    def available(self):
        return self.cx is not None

    def close(self):
        try:
            if self.cx is not None:
                self.cx.close()
        except Exception:  # noqa: BLE001
            pass

    def _where(self, f):
        """Фильтры -> (SQL-условие, аргументы). Все фильтры комбинируются AND."""
        cond, args = ['1=1'], []
        if f.get('rev_min') is not None:
            cond.append(_REV_SQL + ' >= ?')
            args.append(f['rev_min'] * 1e6)    # млн -> руб, как rev_from в callbase
        if f.get('rev_max') is not None:
            cond.append(_REV_SQL + ' <= ?')
            args.append(f['rev_max'] * 1e6)
        if f.get('tail'):
            # «хвост списка» = последние N строк в ПОРЯДКЕ БАЗЫ (rowid вставки):
            # порог-rowid одним запросом, дальше обычное AND с прочими фильтрами
            r = self.cx.execute('SELECT rowid FROM obzvon ORDER BY rowid DESC '
                                'LIMIT 1 OFFSET ?', (f['tail'] - 1,)).fetchone()
            cond.append('rowid >= ?')
            args.append(r[0] if r else 0)      # хвост больше базы -> вся база
        if f.get('region'):
            cond.append('panel_contains(region, ?)')
            args.append(f['region'])
        if f.get('division'):
            cond.append('division = ?')
            args.append(f['division'])
        if f.get('email') == 'yes':
            cond.append("(emails_base <> '' OR emails_site <> '')")
        elif f.get('email') == 'no':
            cond.append("emails_base = '' AND emails_site = ''")
        if f.get('site') == 'yes':
            cond.append("sites <> ''")
        elif f.get('site') == 'no':
            cond.append("sites = ''")
        return ' AND '.join(cond), args

    def count(self, f):
        where, args = self._where(f)
        return self.cx.execute(f'SELECT COUNT(*) FROM obzvon WHERE {where}',
                               args).fetchone()[0]

    def page(self, f, page=1, per_page=BASE_PER_PAGE):
        """Страница списка для таблицы «База». LIMIT/OFFSET, порядок — порядок
        базы (rowid): владелец мыслит базу как список «сверху вниз и хвост»."""
        total = self.count(f)
        pages = max(1, -(-total // per_page))
        page = min(max(1, page), pages)        # ?page=99999 -> последняя, не ошибка
        where, args = self._where(f)
        rows = []
        for r in self.cx.execute(
                'SELECT inn, name_short, name_full, region, division, revenue, '
                f'revenue_rub, emails_base, emails_site, sites FROM obzvon '
                f'WHERE {where} ORDER BY rowid LIMIT ? OFFSET ?',
                args + [per_page, (page - 1) * per_page]):
            (inn, ns, nf, region, div, rev, rev_rub, eb, es, sites) = r
            rub = parse_money(rev_rub) if (rev_rub or '').strip() else parse_money(rev)
            rows.append({
                'inn': inn, 'name': ns or nf or inn, 'region': region or '',
                'division': div or '',
                # млн ₽ для показа: в таблице сырые «123 456 789» нечитабельны
                'revenue_mln': (round(rub / 1e6, 1) if rub is not None else None),
                'has_email': bool((eb or '').strip() or (es or '').strip()),
                'has_site': bool((sites or '').strip()),
            })
        return {'rows': rows, 'total': total, 'page': page, 'pages': pages,
                'per_page': per_page}

    def select(self, f, n):
        """Первые n компаний выборки (порядок базы) -> строки для create_run.
        Ровно эта функция отвечает за «сколько компаний взять» из ТЗ владельца."""
        where, args = self._where(f)
        out = []
        for inn, ns, nf in self.cx.execute(
                f'SELECT inn, name_short, name_full FROM obzvon WHERE {where} '
                'ORDER BY rowid LIMIT ?', args + [int(n)]):
            out.append({'inn': inn, 'name': (ns or nf or inn)[:200]})
        return out

    def sites(self, inns):
        """{inn: сайт} из базы обзвона — для передачи в обогащение.

        Найдено 11.08.2026: панель отбирала строки фильтром «сайт есть», а в задание
        клала только ИНН и имя, и обогащение искало сайт заново поиском. На прогоне №2
        все 1921 строки имели сайт в базе, и поиск в 78% случаев просто выводил тот же
        домен, а в остальных иногда приносил брак (chelny-holod.ru -> check.tochka.com).
        Поле `sites` держит НЕСКОЛЬКО адресов через ' | '; соцсети сайтом не считаем —
        по ним краулить нечего, там пусть работает поиск."""
        SOC = ('vk.com', 'ok.ru', 't.me', 'telegram.me', 'instagram.com', 'facebook.com',
               'youtube.com', 'zen.yandex.ru', 'wa.me', 'api.whatsapp.com')
        out = {}
        for i in range(0, len(inns), 500):
            chunk = [str(x) for x in inns[i:i + 500]]
            ph = ','.join('?' * len(chunk))
            try:
                rows = self.cx.execute(
                    f'SELECT inn, sites FROM obzvon WHERE inn IN ({ph})', chunk)
            except sqlite3.OperationalError:
                return out
            for inn, s in rows:
                for kus in re.split(r'[|,;\s]+', str(s or '')):
                    kus = kus.strip()
                    if not kus or '.' not in kus:
                        continue
                    d = re.sub(r'^www\.', '',
                               re.sub(r'^https?://', '', kus, flags=re.I).split('/')[0]).lower()
                    if not d or any(d == m or d.endswith('.' + m) for m in SOC):
                        continue
                    out[inn] = kus if kus.lower().startswith('http') else 'http://' + d
                    break
        return out

    def ogrns(self, inns):
        """{inn: ogrn} для opo_batch (checko ходит по ОГРН). Чанками по 500 —
        лимит переменных SQLite ~999."""
        out = {}
        for i in range(0, len(inns), 500):
            chunk = [str(x) for x in inns[i:i + 500]]
            ph = ','.join('?' * len(chunk))
            for inn, ogrn in self.cx.execute(
                    f'SELECT inn, ogrn FROM obzvon WHERE inn IN ({ph})', chunk):
                out[inn] = (ogrn or '').strip()
        return out


# ---------------------------------------------------------------------------
# Подпись заданий — байт-в-байт формат run_on_server.py / job_runner.py
# ---------------------------------------------------------------------------

def canonical(job):
    """Строка для подписи. ДОЛЖНА совпадать с job_runner.canonical, иначе раннер
    выбросит задание как неподписанное (проверяется тестом на реальном job_runner)."""
    payload = {'id': job.get('id'), 'task': job.get('task'),
               'args': job.get('args', {}), 'ts': job.get('ts')}
    return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False)


def make_job(jid, task, args, secret=''):
    job = {'id': jid, 'task': task, 'args': args, 'ts': int(time.time())}
    if secret:
        job['sig'] = hmac.new(secret.encode('utf-8'), canonical(job).encode('utf-8'),
                              hashlib.sha256).hexdigest()
    return job


class DropClient:
    """Минимальный клиент дропа (тот же протокол, что drop_client.sh / job_runner):
    токен в заголовке X-Drop-Token, PUT/GET/DELETE по имени файла."""

    def __init__(self, url=None, token=None):
        self.url = (url or _env('DROP_URL', 'https://parsercompressor.online/drop')).rstrip('/')
        self.token = token if token is not None else _env('DROP_TOKEN', '')

    def _req(self, method, path, data=None, timeout=60):
        req = urllib.request.Request(f'{self.url}/{path}', data=data, method=method,
                                     headers={'X-Drop-Token': self.token})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def list(self):
        return json.loads(self._req('GET', 'list'))

    def up(self, name, blob):
        self._req('PUT', name, data=blob)

    def down(self, name):
        return self._req('GET', name)

    def delete(self, name):
        self._req('DELETE', name)


# ---------------------------------------------------------------------------
# Конвейеры: какая операция enrich_contacts, каким батчем, какая стадия = «сделано»
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Pipeline:
    key: str
    label: str
    batch: int             # строк на одно задание
    done_stages: tuple     # строка «сделана», если в stage_log есть ХОТЬ ОДНА из стадий
    note: str = ''

    def build_args(self, rows, run_id):
        raise NotImplementedError


class _BasePipeline(Pipeline):
    def build_args(self, rows, run_id):
        # Сигнатура фактическая из enrich_contacts.main(): companies=[{inn,name,...}],
        # параметры — как в боевых драйверах (launch_refail/launch_top1000), но батч
        # маленький (6-10, как в news-драйверах) => пишем СРАЗУ и переживаем рестарты.
        # сайт из базы обзвона едет ВМЕСТЕ со строкой: enrich_one возьмёт его основным,
        # а поиск позовёт вторым свидетелем (совпали домены -> verified='base+serp').
        ob = ObzvonDB()
        try:
            sajty = ob.sites([r['inn'] for r in rows]) if ob.available else {}
        finally:
            ob.close()
        comps = []
        for r in rows:
            c = {'inn': r['inn'], 'name': r['name']}
            if sajty.get(r['inn']):
                c['site'] = sajty[r['inn']]
            comps.append(c)
        return {
            'companies': comps,
            'workers': min(8, max(1, len(comps))), 'browser_workers': 2, 'channels': 4,
            'pace_min': 2, 'pace_max': 5,
            'smtp_check': True,
            # zakupki_check НЕ включаем: ЕИС — отдельный конвейер etp_fit (иначе двойная
            # работа по тем же карточкам закупок)
            'no_vk_lookup': True,   # VK через один профиль — на батчах виснет (урок массы)
            'write_db': True, 'resume': True,
            # свой stream-файл на прогон: resume и кап попыток считаются в рамках прогона
            'stream_file': f'enrich_panel_run{run_id}.jsonl',
            'source': f'panel-run{run_id}',
        }


class _EtpPipeline(Pipeline):
    def build_args(self, rows, run_id):
        # etp_fit: inns + limit (без limit возьмёт только 40!) + max_cards.
        # Внутри сам пропускает ИНН со стадией 'etp' — двойная защита идемпотентности.
        inns = [r['inn'] for r in rows]
        return {'op': 'etp_fit', 'inns': inns, 'limit': len(inns), 'max_cards': 3}


class _OkvedPipeline(Pipeline):
    def build_args(self, rows, run_id):
        # checko_okveds: полный список ОКВЭД со страницы checko + основной из dadata,
        # durable-стадия 'checko'. Внутреннего resume НЕТ — отбор несделанных на панели.
        return {'op': 'checko_okveds', 'inns': [r['inn'] for r in rows]}


class _PromotePipeline(Pipeline):
    def build_args(self, rows, run_id):
        # promote_named_email: пере-выбор лучшего адреса. Чисто БД-операция (без
        # внешних запросов), поэтому батч крупный — дробить на 8 нет смысла.
        return {'op': 'promote_named_email', 'inns': [r['inn'] for r in rows]}


# «Батч = вся выборка одним заданием»: для ops, которые сами управляют объёмом
# работы и НЕ принимают список строк (hh_signals, zakupki_mass) дробление
# бессмысленно — получилось бы N одинаковых глобальных сканов.
WHOLE = 10 ** 9


class _HhSignalsPipeline(Pipeline):
    def build_args(self, rows, run_id):
        # ФАКТ из enrich_contacts.py (op 'hh_signals'): список ИНН op НЕ принимает —
        # это глобальный скан выдачи hh.ru по компрессорным запросам с матчем
        # работодателей на ВСЮ базу обзвона (+добор ИНН через dadata). Стадию 'hh'
        # он пишет тем компаниям, у которых нашлись вакансии. Поэтому batch=WHOLE
        # (один job на постановку), а выбранные строки задают только учёт
        # прогресса и решение «ставить ли вообще» (все уже со стадией -> 0 job).
        return {'op': 'hh_signals', 'pages': 3}


class _OpoBatchPipeline(Pipeline):
    def build_args(self, rows, run_id):
        # opo_batch (enrich_contacts.py): companies=[{ogrn,inn,name}] — checko
        # ходит по ОГРН (/company/{OGRN}/licenses), поэтому ОГРН подтягиваем из
        # индекса базы обзвона по ИНН; без ОГРН op честно вернёт «нет OGRN» по
        # строке. dolphin_profiles не передаём — op сам подтянет по DOLPHIN_TOKEN.
        ob = ObzvonDB()
        try:
            og = ob.ogrns([r['inn'] for r in rows]) if ob.available else {}
        finally:
            ob.close()
        comps = [{'ogrn': og.get(r['inn'], ''), 'inn': r['inn'], 'name': r['name']}
                 for r in rows]
        # out_file уникален на батч (иначе батчи затирали бы дефолтный
        # checko-opo.csv друг друга); первый ИНН батча уникален в рамках прогона
        return {'op': 'opo_batch', 'companies': comps,
                'out_file': f'panel-opo-run{run_id}-{rows[0]["inn"]}.csv'}


class _ZakupkiMassPipeline(Pipeline):
    def build_args(self, rows, run_id):
        # ФАКТ из enrich_contacts.py (op 'zakupki_mass'): список ИНН op НЕ
        # принимает — идёт по ВСЕЙ базе сверху вниз по выручке со своим durable-
        # резюмом (.zk_done.txt на сервере). Выборка панели задаёт только ОБЪЁМ
        # (cap = сколько ещё не пройденных компаний обработать). Адресный ЕИС по
        # списку ИНН — это конвейер «ЕИС-закупки» (etp_fit), он выше.
        return {'op': 'zakupki_mass', 'cap': len(rows), 'max_cards': 3}


# ВСЕ конвейеры идут job-задачей 'enrich_contacts' (имя из allowlist job_runner.ALLOW);
# конкретная операция выбирается полем args['op'] (без op — базовое обогащение).
PIPELINES = {
    'base': _BasePipeline(
        'base', 'Базовое обогащение (сайт + краул + роли + почты + телефоны)',
        batch=8, done_stages=('site', 'site_cand', 'email'),
        note='строка «сделана», если найден сайт/кандидат сайта или почта'),
    'etp': _EtpPipeline(
        'etp', 'ЕИС-закупки (именной контакт снабженца с карточки закупки)',
        batch=8, done_stages=('etp',)),
    'okved': _OkvedPipeline(
        'okved', 'ОКВЭД-классификация (checko: полный список, направление, конкурент)',
        batch=8, done_stages=('checko',)),
    'best_email': _PromotePipeline(
        'best_email', 'Пере-выбор лучшего адреса (именной вместо приёмной)',
        batch=1000, done_stages=('best_email_v2',),
        note='стадия пишется только при фактической замене адреса; повтор дёшев (только БД)'),
    'hh': _HhSignalsPipeline(
        'hh', 'Вакансии hh (компрессорные вакансии = «оборудование есть»)',
        batch=WHOLE, done_stages=('hh',),
        note='скан hh.ru глобальный (op не принимает список ИНН): стадия появится '
             'у компаний, где найдены вакансии'),
    'opo': _OpoBatchPipeline(
        'opo', 'ОПО Ростехнадзора (лицензии на checko, через дельфин)',
        # 40 на job: каждая компания = один заход браузера, op раскладывает пачку
        # по дельфин-профилям сам; 8 (как у сетевых) жгло бы старт профилей впустую
        batch=40, done_stages=('opo',),
        note='результат — CSV на дропе; стадию opo этот op НЕ пишет, поэтому '
             'прогресс/докидка по стадии не работают — не жать повторно без нужды'),
    'zakupki': _ZakupkiMassPipeline(
        'zakupki', 'Закупки ЕИС массово (вся база, сверху вниз по выручке)',
        batch=WHOLE, done_stages=('zakupki',),
        note='op не принимает список ИНН: идёт по всей базе по убыванию выручки '
             'со своим резюмом; выборка задаёт только объём (cap)'),
}

# Человекочитаемые подписи известных стадий (для страницы прогона)
STAGE_LABELS = {
    'site': 'сайт подтверждён', 'site_cand': 'сайт-кандидат', 'crawl': 'краул сайта',
    'email': 'почты найдены', 'verify': 'верификация', 'phone': 'телефоны',
    'etp': 'ЕИС-закупки', 'checko': 'ОКВЭД (checko)', 'okved_v2': 'ОКВЭД-переклассификация',
    'best_email_v2': 'лучший адрес заменён', 'opo': 'ОПО-сигнал', 'hh': 'вакансии hh',
    'zakupki': 'закупки (база)', 'activity': 'деятельность',
}


# ---------------------------------------------------------------------------
# Состояние прогонов в enrich.db (таблицы панели) + прогресс по stage_log
# ---------------------------------------------------------------------------

_PANEL_SCHEMA = """
CREATE TABLE IF NOT EXISTS enrich_runs(              -- журнал прогонов панели
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created TEXT,                                      -- когда загружен файл
  filename TEXT,                                     -- имя файла у пользователя (для отчёта)
  stored_file TEXT,                                  -- наше сгенерённое имя в enrich_uploads
  pipelines TEXT,                                    -- выбранные конвейеры (csv ключей)
  total INTEGER,                                     -- всего принятых строк
  batches INTEGER DEFAULT 0,                         -- поставлено заданий (батчей)
  status TEXT,                                       -- новый | запущен | готов | готов (с ошибками)
  report TEXT);                                      -- JSON-отчёт валидации (принято/отброшено)
CREATE TABLE IF NOT EXISTS enrich_run_rows(          -- строки прогона (для join со stage_log)
  run_id INTEGER, inn TEXT, name TEXT, UNIQUE(run_id, inn));
CREATE TABLE IF NOT EXISTS enrich_run_batches(       -- поставленные задания (для статусов)
  run_id INTEGER, job_id TEXT UNIQUE, pipeline TEXT, n_rows INTEGER,
  status TEXT, submitted TEXT, done_ts TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_prr_run ON enrich_run_rows(run_id);
CREATE INDEX IF NOT EXISTS ix_prb_run ON enrich_run_batches(run_id);
"""

_now = lambda: time.strftime('%Y-%m-%dT%H:%M:%S')  # noqa: E731


class PanelDB:
    """Доступ панели к enrich.db. Свои таблицы создаёт сама; таблицы обогащения
    (companies/emails/stage_log) НЕ создаёт — их ведёт enrich_db.py, панель только
    читает (WAL позволяет читать параллельно с пишущим раннером)."""

    def __init__(self, path=None):
        self.path = path or enrich_db_path()
        self.cx = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self.cx.execute('PRAGMA journal_mode=WAL')
        self.cx.execute('PRAGMA busy_timeout=30000')
        self.cx.executescript(_PANEL_SCHEMA)
        self.cx.commit()
        self._lock = threading.Lock()   # FastAPI-обработчики идут из пула потоков

    def close(self):
        try:
            self.cx.close()
        except Exception:  # noqa: BLE001
            pass

    # -- прогоны -----------------------------------------------------------
    def create_run(self, filename, stored_file, rows, report):
        """Прогон + его строки одной транзакцией: журнал не должен видеть прогон
        без строк после падения между вставками."""
        with self._lock:
            cur = self.cx.execute(
                'INSERT INTO enrich_runs(created, filename, stored_file, pipelines, '
                'total, batches, status, report) VALUES(?,?,?,?,?,?,?,?)',
                (_now(), filename[:120], stored_file, '', len(rows), 0, 'новый',
                 json.dumps(report, ensure_ascii=False)))
            run_id = cur.lastrowid
            self.cx.executemany(
                'INSERT OR IGNORE INTO enrich_run_rows(run_id, inn, name) VALUES(?,?,?)',
                [(run_id, r['inn'], r['name']) for r in rows])
            self.cx.commit()
        return run_id

    def get_run(self, run_id):
        r = self.cx.execute('SELECT id, created, filename, stored_file, pipelines, total, '
                            'batches, status, report FROM enrich_runs WHERE id=?',
                            (run_id,)).fetchone()
        if not r:
            return None
        keys = ('id', 'created', 'filename', 'stored_file', 'pipelines', 'total',
                'batches', 'status', 'report')
        return dict(zip(keys, r))

    def list_runs(self, limit=100):
        rows = self.cx.execute(
            'SELECT id, created, filename, pipelines, total, batches, status '
            'FROM enrich_runs ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        keys = ('id', 'created', 'filename', 'pipelines', 'total', 'batches', 'status')
        return [dict(zip(keys, r)) for r in rows]

    def update_run(self, run_id, **f):
        allowed = {'pipelines', 'batches', 'status'}
        vals = {k: v for k, v in f.items() if k in allowed}
        if not vals:
            return
        with self._lock:
            sets = ', '.join(f'{k}=?' for k in vals)
            self.cx.execute(f'UPDATE enrich_runs SET {sets} WHERE id=?',
                            list(vals.values()) + [run_id])
            self.cx.commit()

    def run_rows(self, run_id):
        return [{'inn': r[0], 'name': r[1]} for r in self.cx.execute(
            'SELECT inn, name FROM enrich_run_rows WHERE run_id=? ORDER BY rowid',
            (run_id,))]

    # -- батчи (поставленные задания) --------------------------------------
    def add_batch(self, run_id, job_id, pipeline, n_rows):
        with self._lock:
            self.cx.execute(
                'INSERT INTO enrich_run_batches(run_id, job_id, pipeline, n_rows, status, '
                'submitted) VALUES(?,?,?,?,?,?)',
                (run_id, job_id, pipeline, n_rows, 'отправлен', _now()))
            self.cx.execute('UPDATE enrich_runs SET batches=batches+1 WHERE id=?', (run_id,))
            self.cx.commit()

    def batches(self, run_id):
        rows = self.cx.execute(
            'SELECT job_id, pipeline, n_rows, status, submitted, done_ts, note '
            'FROM enrich_run_batches WHERE run_id=? ORDER BY rowid', (run_id,)).fetchall()
        keys = ('job_id', 'pipeline', 'n_rows', 'status', 'submitted', 'done_ts', 'note')
        return [dict(zip(keys, r)) for r in rows]

    def pending_batches(self, run_id, pipeline=None):
        """Задания, ещё не завершившиеся (нет результата). Нужны для (а) обновления
        статусов с дропа, (б) защиты «Докинуть» от дублей, пока батчи в работе."""
        q = ("SELECT job_id, pipeline FROM enrich_run_batches WHERE run_id=? "
             "AND status NOT IN ('готов', 'ошибка')")
        args = [run_id]
        if pipeline:
            q += ' AND pipeline=?'
            args.append(pipeline)
        return [{'job_id': r[0], 'pipeline': r[1]}
                for r in self.cx.execute(q, args).fetchall()]

    def mark_batch(self, job_id, status, note=''):
        with self._lock:
            self.cx.execute(
                'UPDATE enrich_run_batches SET status=?, note=?, '
                "done_ts=CASE WHEN ? IN ('готов','ошибка') THEN ? ELSE done_ts END "
                'WHERE job_id=?',
                (status, note[:400], status, _now(), job_id))
            self.cx.commit()

    def batch_count(self, run_id):
        return self.cx.execute('SELECT COUNT(*) FROM enrich_run_batches WHERE run_id=?',
                               (run_id,)).fetchone()[0]

    # -- прогресс по stage_log (источник истины) ---------------------------
    def stage_counts(self, run_id):
        """{stage: сколько строк прогона её прошли}. Только по stage_log — никаких
        догадок из результатов заданий: рестарт ничего не теряет."""
        try:
            return {r[0]: r[1] for r in self.cx.execute(
                'SELECT s.stage, COUNT(DISTINCT s.inn) FROM stage_log s '
                'JOIN enrich_run_rows r ON r.inn = s.inn WHERE r.run_id=? '
                'GROUP BY s.stage ORDER BY 2 DESC', (run_id,))}
        except sqlite3.OperationalError:
            return {}   # свежая/тестовая БД без stage_log — прогресса просто нет

    def stages_for_inns(self, inns):
        """{inn: 'site,email,...'} для страницы «База» — ОДНИМ запросом на всю
        страницу списка (требование: без N+1). Чанки по 500 — лимит переменных
        SQLite ~999 (страница сейчас 50, чанк — страховка на будущее)."""
        out = {}
        if not inns:
            return out
        try:
            for i in range(0, len(inns), 500):
                chunk = [str(x) for x in inns[i:i + 500]]
                ph = ','.join('?' * len(chunk))
                for inn, stages in self.cx.execute(
                        f'SELECT inn, GROUP_CONCAT(stage) FROM stage_log '
                        f'WHERE inn IN ({ph}) GROUP BY inn', chunk):
                    out[inn] = stages or ''
        except sqlite3.OperationalError:
            return {}   # свежая/тестовая БД без stage_log — стадий просто нет
        return out

    def missing_rows(self, run_id, done_stages):
        """Строки прогона БЕЗ единой стадии из done_stages — кандидаты на (пере)запуск.
        Один и тот же отбор для «Запустить» и «Докинуть» = идемпотентность."""
        ph = ','.join('?' * len(done_stages))
        try:
            rows = self.cx.execute(
                f'SELECT r.inn, r.name FROM enrich_run_rows r WHERE r.run_id=? '
                f'AND NOT EXISTS (SELECT 1 FROM stage_log s WHERE s.inn = r.inn '
                f'AND s.stage IN ({ph})) ORDER BY r.rowid',
                [run_id] + list(done_stages)).fetchall()
        except sqlite3.OperationalError:
            rows = self.cx.execute(
                'SELECT inn, name FROM enrich_run_rows WHERE run_id=? ORDER BY rowid',
                (run_id,)).fetchall()
        return [{'inn': r[0], 'name': r[1]} for r in rows]

    def latest_results(self, run_id, limit=20):
        """Свежеобогащённые строки прогона: компания -> сайт/почта/роль.
        Роль берём у самого best_email (а не первую попавшуюся)."""
        try:
            rows = self.cx.execute(
                'SELECT r.inn, COALESCE(NULLIF(c.name, ""), r.name), c.site, '
                'c.best_email, c.updated_at FROM enrich_run_rows r '
                'JOIN companies c ON c.inn = r.inn WHERE r.run_id=? '
                'ORDER BY c.updated_at DESC, r.rowid LIMIT ?', (run_id, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        out = []
        for inn, name, site, best, upd in rows:
            role = person = ''
            if best:
                er = self.cx.execute('SELECT role, person FROM emails WHERE inn=? AND email=?',
                                     (inn, best)).fetchone()
                if er:
                    role, person = er[0] or '', er[1] or ''
            out.append({'inn': inn, 'name': name or '', 'site': site or '',
                        'best_email': best or '', 'role': role, 'person': person,
                        'updated': upd or ''})
        return out

    def export_rows(self, run_id):
        """Данные для CSV-выгрузки: по каждой принятой строке — что накоплено в
        enrich.db (сайт/лучший адрес/роль/телефоны) + пройденные стадии."""
        rows = self.run_rows(run_id)
        comp, stages, roles = {}, {}, {}
        try:
            for r in self.cx.execute(
                    'SELECT c.inn, c.name, c.site, c.best_email, c.phones FROM companies c '
                    'JOIN enrich_run_rows rr ON rr.inn = c.inn WHERE rr.run_id=?', (run_id,)):
                comp[r[0]] = {'name': r[1] or '', 'site': r[2] or '',
                              'best_email': r[3] or '', 'phones': r[4] or ''}
            for r in self.cx.execute(
                    'SELECT s.inn, GROUP_CONCAT(s.stage) FROM stage_log s '
                    'JOIN enrich_run_rows rr ON rr.inn = s.inn WHERE rr.run_id=? '
                    'GROUP BY s.inn', (run_id,)):
                stages[r[0]] = r[1] or ''
            for r in self.cx.execute(
                    'SELECT e.inn, e.email, e.role FROM emails e '
                    'JOIN enrich_run_rows rr ON rr.inn = e.inn WHERE rr.run_id=?', (run_id,)):
                roles[(r[0], r[1] or '')] = r[2] or ''
        except sqlite3.OperationalError:
            pass    # таблиц обогащения ещё нет — выгрузим только исходный список
        out = []
        for r in rows:
            c = comp.get(r['inn'], {})
            phones = c.get('phones', '')
            try:        # phones хранится JSON-списком — для CSV склеиваем в строку
                pl = json.loads(phones) if phones else []
                phones = ', '.join(str(p) for p in pl) if isinstance(pl, list) else str(pl)
            except Exception:  # noqa: BLE001
                pass
            best = c.get('best_email', '')
            out.append({'inn': r['inn'], 'name': c.get('name') or r['name'],
                        'site': c.get('site', ''), 'best_email': best,
                        'role': roles.get((r['inn'], best), ''), 'phones': phones,
                        'stages': stages.get(r['inn'], '')})
        return out


# ---------------------------------------------------------------------------
# Постановка заданий (Запустить / Докинуть — один и тот же код)
# ---------------------------------------------------------------------------

def submit_run(pdb, drop, secret, run_id, pipeline_keys):
    """Поставить подписанные задания по выбранным конвейерам.

    Идемпотентность (требование владельца) двумя рубежами:
      1. Берём только строки БЕЗ нужной стадии в stage_log (missing_rows).
      2. Пока по конвейеру есть незавершённые батчи — новые НЕ ставим (blocked):
         иначе двойной клик = двойной расход xmlriver/краула по тем же строкам.
    Возврат — отчёт для UI: сколько заданий/строк поставлено, сколько пропущено
    как уже сделанное, какие конвейеры ждут завершения предыдущих батчей.
    """
    run = pdb.get_run(run_id)
    if run is None:
        raise ValueError(f'нет прогона {run_id}')
    report = {'jobs': 0, 'rows': {}, 'skipped_done': {}, 'blocked': []}
    for key in pipeline_keys:
        p = PIPELINES.get(key)
        if p is None:
            continue
        if pdb.pending_batches(run_id, pipeline=key):
            report['blocked'].append(key)
            continue
        rows = pdb.missing_rows(run_id, p.done_stages)
        report['rows'][key] = len(rows)
        report['skipped_done'][key] = run['total'] - len(rows)
        for i in range(0, len(rows), p.batch):
            chunk = rows[i:i + p.batch]
            # id уникален: время + прогон + конвейер + сквозной номер батча в прогоне
            jid = f'{int(time.time())}-r{run_id}-{key}-b{pdb.batch_count(run_id) + 1}'
            job = make_job(jid, 'enrich_contacts', p.build_args(chunk, run_id), secret)
            drop.up(f'job-{jid}.json',
                    json.dumps(job, ensure_ascii=False).encode('utf-8'))
            # запись в БД ПОСЛЕ успешного PUT: упал дроп — батча в учёте нет,
            # повторный запуск переотправит те же строки (стадий-то не появилось)
            pdb.add_batch(run_id, jid, key, len(chunk))
            report['jobs'] += 1
    return report


def refresh_batches(pdb, drop, run_id):
    """Обновить статусы батчей по состоянию дропа (вызывается при открытии страницы
    прогона). job-файл ещё лежит -> «в очереди»; result-файл появился -> скачать
    сводку, пометить готов/ошибка и УДАЛИТЬ результат с дропа (иначе копятся);
    ни того ни другого -> раннер забрал в работу -> «выполняется».
    Дроп недоступен — молча оставляем как есть: прогресс всё равно виден по stage_log."""
    pend = pdb.pending_batches(run_id)
    if not pend:
        return
    try:
        names = {f['name'] for f in drop.list()}
    except Exception:  # noqa: BLE001
        return
    for b in pend:
        jid = b['job_id']
        rname = f'result-{jid}.json'
        if rname in names:
            note, ok = '', False
            try:
                res = json.loads(drop.down(rname))
                ok = bool(res.get('ok'))
                data = res.get('data')
                if isinstance(data, dict):
                    # короткая сводка в журнал: что вернул op (summary/счётчики)
                    brief = data.get('summary') or {
                        k: v for k, v in data.items()
                        if isinstance(v, (int, str)) and k not in ('op',)}
                    note = json.dumps(brief, ensure_ascii=False)[:300]
                elif res.get('error'):
                    note = str(res['error'])[:300]
                drop.delete(rname)
            except Exception as e:  # noqa: BLE001
                note = f'result не прочитан: {str(e)[:80]}'
            pdb.mark_batch(jid, 'готов' if ok else 'ошибка', note)
        elif f'job-{jid}.json' in names:
            pdb.mark_batch(jid, 'в очереди')
        else:
            pdb.mark_batch(jid, 'выполняется')
    # агрегатный статус прогона — после обновления батчей
    left = pdb.pending_batches(run_id)
    if not left:
        errs = [b for b in pdb.batches(run_id) if b['status'] == 'ошибка']
        pdb.update_run(run_id, status='готов (с ошибками)' if errs else 'готов')
