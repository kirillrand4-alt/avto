# -*- coding: utf-8 -*-
"""Глубокая проверка токсичности доноров: sitemap/внутренний поиск -> контексты маркеров ->
LLM-классификация (редакционное размещение / тизерка / случайное упоминание)."""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp

DIR = os.path.dirname(os.path.abspath(__file__))
DOMAINS = sys.argv[1:] or ['ftimes.ru', 'gazetagavrilovka.ru', 'kineshemec.ru']
TOX_WORDS = ['казино', 'ставк', 'букмекер', 'займ', 'бонус за регистрацию', '1xbet', 'вулкан', 'слоты']
TOX_DOMS = ['1xbet', 'casino', 'kazino', 'vulkan', 'melbet', 'fonbet', 'zaim', 'mfo', 'slots', 'bet']

def curl(url, timeout=20):
    r = subprocess.run(['curl', '-sL', '--max-time', str(timeout), '-A',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0', url],
        capture_output=True, timeout=timeout+10)
    return r.stdout.decode('utf-8', errors='ignore')

def probe(dom):
    ev = {'domain': dom, 'cases': [], 'search_hits': {}}
    # 1) внутренний поиск (WP и типовые)
    for w in ['казино', 'букмекер', 'займ']:
        html = curl(f'https://{dom}/?s={w}')
        urls = re.findall(r'href="(https?://' + re.escape(dom) + r'/[^"]{8,120})"', html)
        arts = [u for u in dict.fromkeys(urls) if not re.search(r'\?s=|/tag/|/category/|#', u)][:6]
        ev['search_hits'][w] = len(arts)
        ev.setdefault('tox_urls', []).extend(arts[:3])
    # 2) sitemap: слаги с токс-словами
    sm = curl(f'https://{dom}/sitemap.xml', 15)
    locs = re.findall(r'<loc>([^<]+)</loc>', sm)[:500]
    slugs = [u for u in locs if re.search(r'kazino|casino|stavk|bukmeker|zaim|bonus|bet|slot', u)]
    ev['sitemap_tox_slugs'] = slugs[:8]
    ev.setdefault('tox_urls', []).extend(slugs[:4])
    # 3) контексты: до 8 страниц
    for u in list(dict.fromkeys(ev.get('tox_urls', [])))[:8]:
        html = curl(u)
        low = html.lower()
        for w in TOX_WORDS:
            i = low.find(w)
            if i < 0: continue
            ctx = re.sub(r'<[^>]+>', ' ', html[max(0,i-350):i+350])
            ctx = re.sub(r'\s+', ' ', ctx).strip()[:280]
            links = re.findall(r'<a\s[^>]*href="(https?://[^"]+)"[^>]*>', html[max(0,i-1200):i+1200], re.I)
            tox_links = [l for l in links if any(t in l.lower() for t in TOX_DOMS)]
            dofollow = any('nofollow' not in (re.search(r'rel="([^"]*)"', l) or [''])[0] for l in tox_links) if tox_links else False
            ev['cases'].append({'url': u[:100], 'word': w, 'context': ctx,
                                'tox_links': tox_links[:3], 'looks_dofollow': bool(tox_links)})
            break
    return ev

evidence = [probe(d) for d in DOMAINS]
json.dump(evidence, open(os.path.join(DIR, 'toxicity-evidence.json'), 'w'), ensure_ascii=False, indent=1)
print('улики собраны;', {e['domain']: len(e['cases']) for e in evidence}, flush=True)

prompt = ("Ты - линкбилдер. По уликам классифицируй ГЛУБИНУ токсичности каждого домена-донора.\n"
          "Типы случаев: A=редакционное размещение под казино/БК/займы (яд), B=тизерная реклама/виджет "
          "(терпимо для регио-СМИ), C=случайное упоминание (не токсично).\n"
          "Для каждого домена: разбор случаев (тип A/B/C с обоснованием по контексту) и ИТОГ: "
          "«токсичен - не брать» / «обычная тизерка - можно брать» / «чисто - ложная тревога фильтра». "
          "Учитывай search_hits (сколько статей находит внутренний поиск по казино/букмекер/займ) и "
          "sitemap_tox_slugs (слаги URL).\n\n=== УЛИКИ ===\n" + json.dumps(evidence, ensure_ascii=False))
client = gp.make_client()
msg = gp.call(client, [{'role':'user','content':prompt}], model='claude-fable-5', effort='high')
out = ''.join(b.text for b in msg.content if b.type == 'text')
open(os.path.join(DIR, 'toxicity-report.md'), 'w').write(out)
print('вердикт -> toxicity-report.md', flush=True)
