# -*- coding: utf-8 -*-
r"""Шаг 2 плана PLAN_CA_O2_N2.md: сигналы газа (только ранжирование, никого не удаляем) + контакты из ТЗ тендеров.

09.11, владелец: «делай всё, что можешь, параллельно». Без моделей и без сети, только чтение:
  1. кэш страниц обхода (C:\seostat\drop\pagecache\<ИНН>.json.gz, 137 тыс. сайтов от прошлых обходов + ночной обход
     набора ca): слова кислорода (УЗВ, оксигенация, цианирование CIL/CIP, озонирование, осётр/форель) и азота (азот,
     МГС, инертный газ, лазерная резка, пайка, азотирование), а также покупной газ (баллоны, жидкий азот/кислород,
     газификатор, криоген) — главный сигнал «заменить покупку своей станцией»;
  2. база тендерного сервиса (C:\tendery\data\tendery.db, только чтение): закупки заказчика с газом/генераторами в
     названии и позициях; в текстах документов — окна вокруг «контактное лицо / ответственный / по техническим
     вопросам» с телефоном или почтой (сырые окна; разбор ролей — следующим шагом через провайдера).
Компании: все ЮЛ с категорией по основному ОКВЭД (кроме «не брать») выше порога, включая n2_lazer — ему сигнал нужен,
чтобы сузить 13,5 тыс. Выход (fsync): ca\ca-signaly.jsonl (по ИНН), ca\ca-tendery-okna.jsonl (окна ТЗ, на сервере —
там ФИО и телефоны, в репозиторий и чат не выводить), ca\ca-signaly-itog.json (счётчики) + итог на дроп.
Запуск: python ca_signaly.py (сам в фон, низкий приоритет). Повторный запуск пересчитывает всё (кэш растёт за ночь).
"""
import collections, gzip, io, json, os, re, sqlite3, subprocess, sys, time

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'
КЭШ = r'C:\seostat\drop\pagecache'
ТЕНДЕРЫ = r'C:\tendery\data\tendery.db'

if '--vnutri' not in sys.argv:
    os.makedirs(ПАПКА, exist_ok=True)
    лог = os.path.join(ПАПКА, 'ca_signaly_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(20)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-600:])
    sys.exit(0)

ЗАМОК = os.path.join(ПАПКА, 'ca_signaly.lock')
try:
    _fd = os.open(ЗАМОК, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(_fd, str(os.getpid()).encode())
    os.close(_fd)
except FileExistsError:
    _pid = open(ЗАМОК).read().strip()
    if _pid and _pid in subprocess.run(['tasklist', '/FI', 'PID eq %s' % _pid], capture_output=True, text=True).stdout:
        print('уже запущен, pid', _pid)
        sys.exit(0)
    open(ЗАМОК, 'w').write(str(os.getpid()))

sys.path.insert(0, DIR)
os.chdir(DIR)
import ca_cel  # noqa: E402

СЛОВА = {
    'o2_рыба': r'\bУЗВ\b|замкнут\w* (?:водоснабж|систем\w* водоснабж)|оксигенац|насыщени\w* (?:воды )?кислород|'
               r'кислородн\w* (?:станц|установк|генератор|концентратор|насыщ)|садков|осетр|форел|смолт|молод\w* рыб|'
               r'рыбоводн\w* (?:хозяйств|комплекс|завод)',
    'o2_золото': r'цианирован|\bCIL\b|\bCIP\b|сорбционн\w* выщелач|кучн\w* выщелач|интенсивн\w* цианир|'
                 r'золотоизвлекат|\bЗИФ\b|гравитационн\w* концентрат',
    'o2_озон': r'озонатор|озонирован|озонов',
    'n2_пища': r'модифицированн\w* (?:газов\w* )?(?:атмосфер|сред)|\bМГС\b|упаковк\w* в (?:защитн|инертн|газов)|'
               r'газов\w* смес|продувк\w* азот|инертн\w* (?:газ|сред)|азотн\w* (?:упаков|продув|подушк)',
    'n2_лазер': r'лазерн\w* резк|волоконн\w* лазер|оптоволоконн\w* лазер|лазерн\w* (?:станок|станк|комплекс)|'
                r'Bodor|Trumpf|Bystronic|HSG|Amada',
    'n2_электроника': r'\bSMT\b|поверхностн\w* монтаж|пайк\w* (?:оплавлен|волн)|печ\w* оплавлен|селективн\w* пайк',
    'n2_азот': r'\bазот(?!ирован)\w*|\bN2\b|генератор\w* азота|азотн\w* (?:станц|установк|генератор)',
    'n2_азотирование': r'азотирован|нитроцементац',
    'газ_покупной': r'баллон\w* (?:с )?(?:азот|кислород)|жидк\w* (?:азот|кислород)|газификатор|криоген|'
                    r'(?:азот|кислород)\w* в баллонах|моноблок\w* баллон|сосуд\w* Дьюара|танк\w* (?:азот|кислород)',
    'кислород': r'\bкислород\w*|\bO2\b',
}
RX = {к: re.compile(v, re.I) for к, v in СЛОВА.items()}
ГАЗ_ЗАКУПКА = re.compile(r'азот|кислород|генератор\w* (?:азота|кислорода)|воздухоразделит|адсорбц|газоразделит|'
                         r'криоген|газификатор|баллон|сжат\w* воздух|компрессор', re.I)
КОНТАКТ = re.compile(r'контактн\w* лиц|ответственн\w* (?:лиц|исполнит|за)|по техническ\w* вопрос|по вопросам|'
                     r'исполнител|инициатор|главн\w* (?:инженер|механик|энергетик|технолог)|начальник\w* (?:отдела|службы|цеха)',
                     re.I)
ТЕЛ = re.compile(r'(?:\+7|8)[\s(-]*\d{3,5}[\s)-]*\d{1,3}[\s-]*\d{2}[\s-]*\d{2}')
ПОЧТА = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')


def отметка(**k):
    k['обновлено'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(ПАПКА, 'ca-signaly-progress.json'), 'w', encoding='utf-8') as f:
        json.dump(k, f, ensure_ascii=False)
    print(json.dumps(k, ensure_ascii=False)[:300], flush=True)


def текст(html):
    html = re.sub(r'(?is)<(script|style|noscript)\b.*?</\1>', ' ', html or '')
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


def компании():
    out = {}
    for имя in ('ca-reestr.jsonl', 'ca-ne-msp-kat.jsonl'):
        п = os.path.join(ПАПКА, имя)
        if not os.path.exists(п):
            continue
        for s in io.open(п, encoding='utf-8', errors='replace'):
            try:
                r = json.loads(s)
            except ValueError:
                continue
            инн = str(r.get('инн') or '')
            if r.get('тип') != 'ЮЛ' or len(инн) != 10:
                continue
            v = float(r.get('доход') or 0)
            кат = [к for к, о in ca_cel.категории(r.get('оквэд'), r.get('оквэд_доп') or []).items()
                   if о == 'осн' and ca_cel.КАТ[к][1] != 'не брать' and v >= ca_cel.порог(к)]
            if кат:
                out[инн] = кат
    return out


def main():
    комп = компании()
    отметка(этап='компании', всего=len(комп))
    # ---------- 1. кэш страниц ----------
    сиг = {}
    n = 0
    for инн in комп:
        п = os.path.join(КЭШ, '%s.json.gz' % инн)
        if not os.path.exists(п):
            continue
        try:
            d = json.load(gzip.open(п, 'rt', encoding='utf-8'))
        except Exception:  # noqa: BLE001
            continue
        n += 1
        нах = collections.defaultdict(list)
        for стр in d.get('pages') or []:
            т = текст(стр.get('html'))
            for к, rx in RX.items():
                for м in rx.finditer(т):
                    if len(нах[к]) >= 3:
                        break
                    нах[к].append({'url': стр.get('url') or '', 'фрагмент': т[max(0, м.start() - 90):м.end() + 90]})
        if нах:
            сиг[инн] = {'кат': комп[инн], 'сайт': d.get('site') or d.get('сайт_домен') or '', 'кэш': dict(нах)}
        if n % 2000 == 0:
            отметка(этап='кэш', просмотрено=n, с_сигналом=len(сиг))
    отметка(этап='кэш-готов', с_кэшем=n, с_сигналом=len(сиг))
    # ---------- 2. тендеры ----------
    окна = 0
    if os.path.exists(ТЕНДЕРЫ):
        c = sqlite3.connect('file:%s?mode=ro' % ТЕНДЕРЫ, uri=True, timeout=60)
        c.execute('create temp table t(inn text primary key)')
        c.executemany('insert or ignore into t values (?)', [(i,) for i in комп])
        for tid, инн, назв, поз, url, дата in c.execute(
                'select id, customer_inn, coalesce(title,""), coalesce(positions_json,""), coalesce(url,""), '
                'coalesce(published_at,"") from tender where customer_inn in (select inn from t)'):
            if ГАЗ_ЗАКУПКА.search(назв + ' ' + поз):
                з = сиг.setdefault(инн, {'кат': комп[инн], 'сайт': '', 'кэш': {}})
                з.setdefault('тендеры_газ', []).append({'id': tid, 'название': назв[:200], 'url': url, 'дата': дата[:10]})
        with io.open(os.path.join(ПАПКА, 'ca-tendery-okna.jsonl'), 'w', encoding='utf-8') as f:
            for tid, инн, url, док, т in c.execute(
                    'select t2.id, t2.customer_inn, t2.url, d.name, x.text from tender t2 join tender_doc d on d.tender_id=t2.id '
                    'join tender_doc_text x on x.doc_id=d.id where t2.customer_inn in (select inn from t)'):
                for м in КОНТАКТ.finditer(т or ''):
                    кус = т[max(0, м.start() - 120):м.end() + 320]
                    if ТЕЛ.search(кус) or ПОЧТА.search(кус):
                        f.write(json.dumps({'inn': инн, 'tender_id': tid, 'url': url, 'документ': (док or '')[:120],
                                            'окно': re.sub(r'\s+', ' ', кус)}, ensure_ascii=False) + '\n')
                        окна += 1
            f.flush()
            os.fsync(f.fileno())
        c.close()
    отметка(этап='тендеры-готов', окон_контактов=окна)
    # ---------- 3. запись ----------
    with io.open(os.path.join(ПАПКА, 'ca-signaly.jsonl'), 'w', encoding='utf-8') as f:
        for инн, з in сиг.items():
            f.write(json.dumps(dict(з, inn=инн), ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    итог = collections.defaultdict(collections.Counter)
    for инн, з in сиг.items():
        for к in з['кат']:
            for с in list(з['кэш']) + (['тендер_газ'] if з.get('тендеры_газ') else []):
                итог[к][с] += 1
            итог[к]['любой'] += 1
    всего_по_кат = collections.Counter(к for кк in комп.values() for к in кк)
    рез = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'компаний': len(комп), 'с_кэшем': n, 'с_сигналом': len(сиг),
           'окон_контактов_тз': окна,
           'по_категориям': {к: dict(итог[к], всего=всего_по_кат[к]) for к in sorted(всего_по_кат)}}
    п = os.path.join(ПАПКА, 'ca-signaly-itog.json')
    with open(п, 'w', encoding='utf-8') as f:
        json.dump(рез, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    import shutil
    shutil.copyfile(п, os.path.join(ДРОП, 'ca-signaly-itog.json'))
    отметка(этап='готово', с_сигналом=len(сиг))


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:  # noqa: BLE001
        отметка(этап='ошибка', ошибка=repr(e)[:500])
        raise
    finally:
        try:
            os.remove(ЗАМОК)
        except OSError:
            pass
