import gzip, json, re, html, os
п = r'C:\seostat\drop\pagecache\9701069920.json.gz'
д = json.load(gzip.open(п, 'rt', encoding='utf-8'))
print('===ИТОГ===')
def опис(o, d=0):
    if isinstance(o, dict): return '{' + ', '.join('%s: %s' % (k, опис(v, d+1) if d < 2 else type(v).__name__) for k, v in list(o.items())[:8]) + '}'
    if isinstance(o, list): return '[%d × %s]' % (len(o), опис(o[0], d+1) if o and d < 2 else '')
    return type(o).__name__
print(опис(д))
def обход(o):
    if isinstance(o, dict):
        if any(isinstance(v, str) and '<' in v and len(v) > 500 for v in o.values()):
            yield o
        for v in o.values(): yield from обход(v)
    elif isinstance(o, list):
        for v in o: yield from обход(v)
for x in обход(д):
    u = x.get('url', '?'); h = next(v for v in x.values() if isinstance(v, str) and '<' in v and len(v) > 500)
    t = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t)))
    for м in re.finditer(r'966\D{0,3}321\D{0,3}80\D{0,3}50', t):
        print(u, x.get('ts', ''), '\n…' + t[max(0, м.start() - 400):м.end() + 150] + '…\n')
