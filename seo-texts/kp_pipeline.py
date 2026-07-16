# -*- coding: utf-8 -*-
"""Конвейер разбора КП/презентаций с drop-сервера:
A) скачать документы (pptx/pdf/docx/doc/xlsx/xls) -> kp-work/raw/
B) механическое извлечение текста -> kp-work/text/*.txt (0 токенов)
C) дедуп шинглами -> уникальные представители кластеров
D) LLM-структуризация представителей (Fable, effort=low, кэш kp-work/struct/)
Резюмируемо на каждом шаге. Приоритет при слиянии (шаг E, отдельно): презентация > КП.
Запуск: python3 kp_pipeline.py [--limit N]"""
import json, os, re, subprocess, sys, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import gen_provider as gp

WORK = os.path.join(DIR, 'kp-work')
RAW, TXT, STR = (os.path.join(WORK, d) for d in ('raw', 'text', 'struct'))
for d in (RAW, TXT, STR):
    os.makedirs(d, exist_ok=True)
DOC_EXT = {'pptx', 'pdf', 'docx', 'doc', 'xlsx', 'xls'}


def env():
    vals = {}
    for line in open(os.path.join(DIR, '.env')):
        line = line.strip()
        if line and '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1); vals[k] = v
    return vals


E = env()
U = E.get('DROP_URL', 'https://parsercompressor.online/drop')
TOK = E['DROP_TOKEN']


def drop_list():
    out = subprocess.run(['curl', '-s', '-H', f'X-Drop-Token: {TOK}', f'{U}/list'],
                         capture_output=True, text=True, timeout=60).stdout
    return json.loads(out)


def download_missing(names):
    todo = [n for n in names if not os.path.exists(os.path.join(RAW, n))]
    print(f'A) скачать: {len(todo)} (уже есть {len(names)-len(todo)})', flush=True)
    def dl(n):
        p = os.path.join(RAW, n)
        subprocess.run(['curl', '-s', '-H', f'X-Drop-Token: {TOK}', f'{U}/{n}', '-o', p + '.tmp'],
                       timeout=600)
        os.replace(p + '.tmp', p)
        return n
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, _ in enumerate(ex.map(dl, todo), 1):
            if i % 25 == 0:
                print(f'   скачано {i}/{len(todo)}', flush=True)


def text_pptx(p):
    out = []
    with zipfile.ZipFile(p) as z:
        slides = sorted((n for n in z.namelist() if re.match(r'ppt/slides/slide\d+\.xml$', n)),
                        key=lambda n: int(re.search(r'\d+', n).group()))
        for s in slides:
            xml = z.read(s).decode('utf-8', errors='ignore')
            ts = [t.strip() for t in re.findall(r'<a:t>(.*?)</a:t>', xml, re.S) if t.strip()]
            if ts:
                out.append(' '.join(ts))
    return '\n'.join(out)


def text_docx(p):
    with zipfile.ZipFile(p) as z:
        xml = z.read('word/document.xml').decode('utf-8', errors='ignore')
    xml = re.sub(r'</w:p>', '\n', xml)
    return re.sub(r'<[^>]+>', '', xml)


def text_pdf(p):
    r = subprocess.run(['pdftotext', '-layout', p, '-'], capture_output=True, timeout=120)
    return r.stdout.decode('utf-8', errors='ignore')


def text_legacy(p, ext):
    """.ppt/.doc/.xls -> pptx/docx/xlsx через soffice (последовательно: у LO лок профиля)."""
    import tempfile, shutil
    to = {'ppt': 'pptx', 'doc': 'docx', 'xls': 'xlsx'}[ext]
    tmp = tempfile.mkdtemp()
    try:
        subprocess.run(['soffice', '--headless', '--convert-to', to, '--outdir', tmp, p],
                       capture_output=True, timeout=180)
        conv = [f for f in os.listdir(tmp) if f.endswith('.' + to)]
        if not conv:
            return '[legacy convert fail]'
        cp = os.path.join(tmp, conv[0])
        return {'pptx': text_pptx, 'docx': text_docx, 'xlsx': text_xlsx}[to](cp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def text_xlsx(p):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        rows = []
        for ws in wb.worksheets[:5]:
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    rows.append(' | '.join(cells))
                if len(rows) > 800:
                    break
        return '\n'.join(rows)
    except Exception as ex:
        return f'[xlsx fail: {ex!r}]'


def extract_all():
    files = sorted(os.listdir(RAW))
    done = skip = 0
    for n in files:
        outp = os.path.join(TXT, n + '.txt')
        if os.path.exists(outp):
            continue
        ext = n.rsplit('.', 1)[-1].lower()
        try:
            if ext == 'pptx': t = text_pptx(os.path.join(RAW, n))
            elif ext == 'docx': t = text_docx(os.path.join(RAW, n))
            elif ext == 'pdf': t = text_pdf(os.path.join(RAW, n))
            elif ext == 'xlsx': t = text_xlsx(os.path.join(RAW, n))
            elif ext in ('ppt', 'doc', 'xls'):  # legacy -> конверсия LibreOffice
                t = text_legacy(os.path.join(RAW, n), ext)
            else: t = ''
        except Exception as ex:
            t = f'[extract fail: {ex!r}]'
        t = re.sub(r'[ \t]+', ' ', t)
        open(outp, 'w', encoding='utf-8').write(t.strip())
        done += 1
    print(f'B) извлечено новых: {done} | всего текстов: {len(os.listdir(TXT))}', flush=True)


def shingles(t, k=5):
    words = re.sub(r'\W+', ' ', t.lower()).split()
    return set(' '.join(words[i:i + k]) for i in range(0, max(len(words) - k, 0), 2))


def dedup():
    texts = {}
    for n in sorted(os.listdir(TXT)):
        t = open(os.path.join(TXT, n), encoding='utf-8').read()
        if len(t) >= 400:                      # мусор/пустышки не структурируем
            texts[n] = t
    keys = list(texts)
    sh = {n: shingles(texts[n]) for n in keys}
    parent = {n: n for n in keys}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if find(a) == find(b):
                continue
            inter = len(sh[a] & sh[b])
            if inter and inter / max(1, min(len(sh[a]), len(sh[b]))) > 0.7:
                parent[find(b)] = find(a)
    clusters = {}
    for n in keys:
        clusters.setdefault(find(n), []).append(n)
    reps = {max(m, key=lambda x: len(texts[x])): m for m in clusters.values()}
    json.dump({r: m for r, m in reps.items()}, open(os.path.join(WORK, 'clusters.json'), 'w'),
              ensure_ascii=False, indent=1)
    print(f'C) документов с текстом: {len(keys)} | уникальных кластеров: {len(reps)}', flush=True)
    return {r: texts[r] for r in reps}


SCHEMA_PROMPT = """Из текста документа о компрессорном оборудовании извлеки факты. Верни ТОЛЬКО JSON:
{"doc_type": "КП|презентация|каталог|прайс|сертификат|другое",
 "brand": "...", "series": ["..."],
 "models": [{"model":"...","power_kvt":N,"pressure_bar":N,"performance_l_min":N,
             "receiver_l":N,"dryer":true/false,"screw_block":"...","price_rub":N}],
 "warranty": "...", "delivery_terms": "...", "seller": "...",
 "company_claims": ["..."], "client": "...", "date": "..."}
Правила: числа ТОЛЬКО из текста (null если нет); doc_type определи по содержанию
(КП адресовано конкретному клиенту с ценой; презентация - общий рассказ о бренде/серии);
максимум 30 моделей, самых полных по данным."""


def structure(reps, limit=None):
    todo = [n for n in reps if not os.path.exists(os.path.join(STR, n + '.json'))]
    if limit:
        todo = todo[:limit]
    print(f'D) структурировать: {len(todo)}', flush=True)
    client = gp.make_client()
    def one(n):
        t = reps[n][:24000]
        try:
            msg = gp.call(client, [{'role': 'user', 'content': SCHEMA_PROMPT + '\n\n=== ТЕКСТ ===\n' + t}],
                          model='claude-fable-5', effort='low')
            d = gp.parse_json(msg)
            d['_source'] = n
            d['_tokens'] = [msg.usage.input_tokens, msg.usage.output_tokens]
        except Exception as ex:
            d = {'_source': n, '_error': repr(ex)[:150]}
        json.dump(d, open(os.path.join(STR, n + '.json'), 'w'), ensure_ascii=False, indent=1)
        return n, '_error' not in d
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, (n, good) in enumerate((f.result() for f in
                as_completed(ex.submit(one, n) for n in todo)), 1):
            ok += good; fail += (not good)
            if i % 10 == 0 or i == len(todo):
                print(f'   {i}/{len(todo)} (ok {ok}, fail {fail})', flush=True)


def main():
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    names = [f['name'] for f in drop_list()
             if f['name'].startswith('kp') and f['name'].rsplit('.', 1)[-1].lower() in DOC_EXT]
    download_missing(names)
    extract_all()
    reps = dedup()
    structure(reps, limit)
    print('ГОТОВО (эта фаза). Слияние в kb - отдельным шагом после манифеста.', flush=True)


if __name__ == '__main__':
    main()
