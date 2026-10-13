# -*- coding: utf-8 -*-
# 13.10: компании холдингов со сделкой у клиента-тёзки (одинаковое юрназвание у нашей компании и у клиента сделки, ИНН
# разные; случай «Агро Альянс»: воронежское ООО и петербургское ООО «Агро-Альянс» холдинга). Модель по данным обоих юрлиц
# и адресам/телефонам сайта решает, чей сайт: «наша» (контакты остаются) / «клиента» (контакты сайта снимаются) / «неясно».
import collections, io, json, os, re, sqlite3, sys, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender'); os.chdir(DIR)
os.environ.update({'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna'})
import pilot_konveyer as PK  # noqa: E402
os.environ.update(PK.Волны().env_шага('kc_kontakty.py'))
import kc_kontakty as KK  # noqa: E402
import _inn_zamer_meyer7 as Z  # noqa: E402
print('===ИТОГ===', time.strftime('%H:%M:%S'))
цели = [json.loads(s) for s in io.open(r'C:\seostat\drop\drop-storage\meyer7-tezki-celi.jsonl', encoding='utf-8') if s.strip()]
нужны = {x['инн'] for x in цели} | {x['инн_сделки'] for x in цели}
карт = {}
for бд, q in ((r'C:\sender\obzvon-index.db', 'select inn, name_short, region, okved_main, revenue_rub, director, address from obzvon'),
              (r'C:\sender\enrich.db', "select inn, name, region, okved, revenue_rub, director, address from companies")):
    c = sqlite3.connect('file:%s?mode=ro' % бд.replace('\\', '/'), uri=True, timeout=120)
    for р in c.execute(q):
        if str(р[0]) in нужны and str(р[0]) not in карт:
            карт[str(р[0])] = 'название %s; регион %s; ОКВЭД %s; выручка %s; руководитель %s; адрес %s' % tuple((str(v or '-'))[:80] for v in р[1:])
    c.close()
сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))['компании']
блоки = []
for j, x in enumerate(цели, 1):
    стр = Z.страницы_кэша(x['ключ'])
    дом = Z.хост(x['сайт'])
    тел, адр = collections.Counter(), []
    for y in стр:
        if дом and Z.хост(y.get('url') or '').replace('www.', '') != дом.replace('www.', ''):
            continue
        т = Z.чистый(re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', (y.get('html') or '')[:300000], flags=re.S | re.I))
        for м in re.finditer(r'(?:\+7|8)[\s(-]*(\d{3,5})', т):
            тел[м.group(1)[:4]] += 1
        for м in re.finditer(r'(?:г\.|город|обл\.|область|край|респ)[^.;]{0,80}', т):
            if len(адр) < 4 and м.group(0) not in адр:
                адр.append(м.group(0)[:90])
    к = сп.get(x['ключ'], {})
    блоки.append('%d. САЙТ %s | юрназвание на сайте: %s | коды телефонов на сайте: %s | адреса на сайте: %s\n НАША компания: ИНН %s; %s; в списке: регион %s, выручка %s\n'
                 ' КЛИЕНТ сделки: ИНН %s; %s' % (j, x['сайт'], re.search(r'«(.*)»', x['как']).group(1), ', '.join(k for k, _ in тел.most_common(4)) or '-',
                                                 ' | '.join(адр) or '-', x['инн'], карт.get(x['инн'], '-'), к.get('регион', ''), к.get('выручка', ''),
                                                 x['инн_сделки'], карт.get(x['инн_сделки'], x.get('клиент', '-'))))
ПР = ('Две компании с одинаковым названием: НАША (из базы) и КЛИЕНТ (у него активная сделка). Чей это сайт? По региону, адресам и '
      'кодам телефонов на сайте, масштабу, профилю, руководителю. Ответ: «наша» / «клиента» / «неясно».\n'
      'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер,"чей":"наша|клиента|неясно","почему":"до 20 слов"}}]\n\n{б}')
о = KK.модель(ПР.format(б='\n\n'.join(блоки)), True) or {}
out = [dict(x, чей=(о.get(j) or {}).get('чей') or '', почему_т=(о.get(j) or {}).get('почему') or '') for j, x in enumerate(цели, 1)]
ВЫХ = os.path.join(DIR, 'meyer7-tezki.jsonl')
with io.open(ВЫХ, 'w', encoding='utf-8') as f:
    f.write('\n'.join(json.dumps(x, ensure_ascii=False) for x in out) + '\n'); f.flush(); os.fsync(f.fileno())
import shutil  # noqa: E402
shutil.copyfile(ВЫХ, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХ)))
for x in out:
    print(x['имя'][:26], '|', x['сайт'][:28], '|', x['чей'], '|', x['почему_т'][:90])
