# -*- coding: utf-8 -*-
"""Изначальный фильтр площадок-доноров: механические проверки (curl, бесплатно) + LLM-вердикт.
Для каждого домена: живость/https, поиск статейного раздела, выборка статей, исходящие ссылки
(dofollow/nofollow, коммерческие анкоры, токсичные соседи), archive.org (возраст, дыры).
Выход: donor-check-evidence.json + donor-check-report.md (после LLM)."""
import json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
import gen_provider as gp

DOMAINS = sorted(set(re.findall(r'^\d+ \| ([a-z0-9.-]+\.[a-z]+)', 
             open(os.path.join(DIR,'donors-selection.txt')).read(), re.M)))

TOXIC = ['казин', 'ставк', 'бетт', 'займ', 'микрозайм', 'эссе', 'диплом на заказ', 'crypto-casino', '1xbet', 'вулкан']
COMM = ['купить', 'цена', 'заказать', 'интернет-магазин', 'скидк']

def curl(url, extra=None, timeout=20):
    cmd = ['curl', '-sL', '--max-time', str(timeout), '-A',
           'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36', url]
    if extra: cmd += extra
    r = subprocess.run(cmd, capture_output=True, timeout=timeout+10)
    return r.stdout.decode('utf-8', errors='ignore')

def check(dom):
    ev = {'domain': dom}
    try:
        # 1) живость + главная
        code_page = curl(f'https://{dom}/', ['-w', '\n===CODE:%{http_code}==='])
        m = re.search(r'===CODE:(\d+)===', code_page)
        ev['http'] = m.group(1) if m else '0'
        page = code_page
        t = re.search(r'<title[^>]*>(.*?)</title>', page, re.S|re.I)
        ev['title'] = re.sub(r'\s+',' ', t.group(1)).strip()[:90] if t else ''
        # 2) кандидаты-статьи с главной
        hrefs = re.findall(r'href="(https?://' + re.escape(dom) + r'[^"]{10,120})"', page) \
              + ['https://'+dom+h for h in re.findall(r'href="(/[^"]{10,120})"', page)]
        arts = [h for h in dict.fromkeys(hrefs) if re.search(r'/(news|stat|article|blog|post|20\d\d)/|\d{4,}', h)][:4]
        ev['sampled'] = len(arts)
        # 3) разбор статей: исходящие внешние ссылки
        ext_do, ext_no, comm_hits, tox_hits = 0, 0, 0, []
        for a in arts:
            html = curl(a)
            low = html.lower()
            for mm in re.finditer(r'<a\s[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', html, re.S|re.I):
                href, anchor = mm.group(1), re.sub(r'<[^>]+>','',mm.group(2))[:60].lower()
                if dom in href: continue
                relm = re.search(r'rel="([^"]*)"', mm.group(0))
                if relm and re.search(r'nofollow|sponsored|ugc', relm.group(1)): ext_no += 1
                else: ext_do += 1
                if any(c in anchor for c in COMM): comm_hits += 1
            tox_hits += [w for w in TOXIC if w in low]
        ev.update(ext_dofollow=ext_do, ext_nofollow=ext_no, commercial_anchors=comm_hits,
                  toxic_markers=sorted(set(tox_hits))[:5])
        # 4) archive.org: возраст и число снапшотов
        cdx = curl(f'http://web.archive.org/cdx/search/cdx?url={dom}&output=json&limit=1&fl=timestamp', timeout=25)
        try:
            first = json.loads(cdx)[1][0][:4]
        except Exception:
            first = None
        ev['first_archive_year'] = first
    except Exception as e:
        ev['error'] = repr(e)[:100]
    return ev

def main():
    print(f'доменов: {len(DOMAINS)}', flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        evidence = list(ex.map(check, DOMAINS))
    json.dump(evidence, open(os.path.join(DIR,'donor-check-evidence.json'),'w'), ensure_ascii=False, indent=1)
    print('улики собраны -> donor-check-evidence.json', flush=True)
    # LLM-вердикт по уликам + исходная таблица
    table = open(os.path.join(DIR,'donors-selection.txt')).read()
    prompt = ("Ты - линкбилдер. По МЕХАНИЧЕСКИМ УЛИКАМ (ниже) и исходной таблице отбора дай "
              "изначальный фильтр площадок. Для каждого домена одна строка:\n"
              "домен | ФИЛЬТР: pass/warn/fail | причина (кратко, по уликам: живость, dofollow-профиль, "
              "коммерческие анкоры, токсичность, возраст)\n"
              "Потом блок: 'ВЫВОДЫ' - какие площадки отпали, какие требуют ручной проверки индексации.\n\n"
              "=== УЛИКИ ===\n" + json.dumps(evidence, ensure_ascii=False)
              + "\n\n=== ИСХОДНАЯ ТАБЛИЦА ===\n" + table)
    client = gp.make_client()
    msg = gp.call(client, [{'role':'user','content':prompt}], model='claude-fable-5', effort='xhigh')
    out = ''.join(b.text for b in msg.content if b.type=='text')
    open(os.path.join(DIR,'donor-check-report.md'),'w').write(out)
    u = msg.usage
    print(f'вердикт готов -> donor-check-report.md | ${u.input_tokens*10/1e6+u.output_tokens*50/1e6:.2f}', flush=True)

if __name__ == '__main__':
    main()
