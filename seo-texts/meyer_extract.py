# -*- coding: utf-8 -*-
"""Meyer KB: fable-экстракция ценного для писем из текстов (архив КП + страницы сайтов).
Кэшируемо/резюмируемо (по файлу на источник). Параллельно (8 потоков провайдера).
Запуск: python3 meyer_extract.py [batch_chars]"""
import os, sys, json, re, time, pathlib, hashlib
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G

SCR = pathlib.Path('/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad')
CACHE = SCR / 'meyer_extract_cache'
CACHE.mkdir(parents=True, exist_ok=True)
MODEL = 'claude-fable-5'

PROMPT = """Ты собираешь БАЗУ ЗНАНИЙ для B2B-рассыльщика направления Meyer (ООО «Руспром»):
фотосепараторы и рентген-инспекция (зерно/пищёвка/вторсырьё/руда). Из текста ниже извлеки ВСЁ
ценное для холодных писем и ответов клиентам. Верни СТРОГО JSON без markdown:
{"models":[{"model":"","series":"","type":"фотосепаратор|рентген|другое","specs":"ключевые
характеристики кратко","price":"цена если есть","capacity":"производительность если есть"}],
"claims":["конкурентные преимущества/клеймы (для писем)"],
"certs":["сертификаты/стандарты (SGS/FDA/RoHS/CE/EAC...)"],
"industries":["отрасли применения"],
"cases":[{"client":"","what":"","industry":""}],
"facts":["полезные факты о компании/продукте (гарантия, сервис, сроки, производство)"],
"faq":[{"q":"вопрос клиента","a":"ответ из текста"}]}
Пустые списки допустимы. НЕ выдумывай — только из текста. Текст:
"""


def call(text):
    prompt = PROMPT + text[:22000]
    for _ in range(3):
        try:
            msg = G._raw_stream([{'role': 'user', 'content': prompt}], MODEL, 3000, thinking=False)
            out = ''.join(b.text for b in msg.content if b.type == 'text')
            m = re.search(r'\{.*\}', out, re.S)
            if m:
                return json.loads(m.group(0))
        except Exception:
            time.sleep(3)
    return None


def sources():
    """Источники: (id, text). Архивные тексты + страницы сайтов (батчами по ~20к)."""
    out = []
    for f in sorted((SCR / 'meyer_txt').glob('*.txt')):
        t = f.read_text(encoding='utf-8', errors='replace').strip()
        if len(t) > 150:
            out.append((f'arc_{f.stem[:70]}', t))
    pages_f = SCR / 'meyer_pages.json'
    if pages_f.exists():
        pages = json.loads(pages_f.read_text())
        for dom, pl in pages.items():
            batch, size, bi = [], 0, 0
            for p in pl:
                batch.append(f"[{p['title']}]\n{p['text']}")
                size += len(p['text'])
                if size > 20000:
                    out.append((f'site_{dom}_{bi}', '\n\n'.join(batch)))
                    batch, size, bi = [], 0, bi + 1
            if batch:
                out.append((f'site_{dom}_{bi}', '\n\n'.join(batch)))
    return out


def one(sid_text):
    sid, text = sid_text
    cf = CACHE / (hashlib.md5(sid.encode()).hexdigest()[:16] + '.json')
    if cf.exists():
        return sid, json.loads(cf.read_text())
    d = call(text)
    if d is not None:
        cf.write_text(json.dumps({'sid': sid, 'data': d}, ensure_ascii=False))
        return sid, {'sid': sid, 'data': d}
    return sid, None


def main():
    src = sources()
    print(f'источников: {len(src)} (архив+сайты)', flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (sid, r) in enumerate(ex.map(one, src), 1):
            if r:
                results.append(r)
            if i % 10 == 0:
                print(f'  {i}/{len(src)}', flush=True)
    # свод
    agg = {'models': {}, 'claims': set(), 'certs': set(), 'industries': set(),
           'cases': [], 'facts': set(), 'faq': []}
    for r in results:
        d = r['data']
        for m in d.get('models') or []:
            k = (m.get('model') or '').strip()
            if k and k not in agg['models']:
                agg['models'][k] = m
        for k in ('claims', 'certs', 'industries', 'facts'):
            for x in d.get(k) or []:
                if x and len(x) < 300:
                    agg[k].add(x.strip())
        agg['cases'] += [c for c in (d.get('cases') or []) if c.get('what')]
        agg['faq'] += [q for q in (d.get('faq') or []) if q.get('q')]
    out = {k: (sorted(v) if isinstance(v, set) else v) for k, v in agg.items()}
    (SCR / 'meyer_kb_raw.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nСВОД: моделей {len(out['models'])} | клеймов {len(out['claims'])} | "
          f"сертификатов {len(out['certs'])} | отраслей {len(out['industries'])} | "
          f"кейсов {len(out['cases'])} | фактов {len(out['facts'])} | faq {len(out['faq'])}", flush=True)


if __name__ == '__main__':
    main()
