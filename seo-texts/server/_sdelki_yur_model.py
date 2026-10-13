# -*- coding: utf-8 -*-
# 13.10 (продолжение _sdelki_po_yurnazvaniyam.py): совпадения ПО НАЗВАНИЮ (сайт упоминает юрлицо, у которого активная
# сделка Meyer) — проверка моделью по кускам страниц: сайт принадлежит компании сделки (или её холдингу/группе — тогда это
# тот же клиент) или она лишь упомянута (клиент, партнёр, поставщик, новость, тёзка). Только компании текущего Excel
# (meyer7-kompanii-klyuchi.txt с дропа). Совпадения «точно» (ИНН/ОГРН сделки на страницах) модель не проверяет.
# Итог — meyer7-sdelki-yur-model.jsonl (fsync, резюм) + дроп. Лог: sdelki_yur_model_*.log.
import collections, io, json, os, re, sys, threading, time
DIR = r'C:\sender\server'
ВЫХ = os.path.join(DIR, 'meyer7-sdelki-yur-model.jsonl')
_лок = threading.Lock()
ПРОМПТ = (
    'Для каждого сайта реши: принадлежит ли сайт компании СДЕЛКИ (указанной ниже, с ИНН и регионом) или её холдингу/группе '
    '(сайт холдинга, где компания сделки — одно из предприятий; торговый дом той же группы) — тогда «да»; или компания '
    'сделки на сайте лишь УПОМЯНУТА: клиент, партнёр, поставщик, покупатель, новость/статья, отзыв, список предприятий '
    'отрасли, тёзка из другого региона с другим профилем — тогда «нет». Если по кускам не понять — «неясно».\n'
    'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер,"ответ":"да|нет|неясно","почему":"до 15 слов"}}]\n\n{сайты}')


def писать(r):
    with _лок:
        with io.open(ВЫХ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def main():
    import pilot_konveyer as PK
    os.environ.update(PK.Волны().env_шага('kc_kontakty.py'))
    import kc_kontakty as KK
    import _inn_zamer_meyer7 as Z
    import sqlite3
    t0 = time.time()
    ключи = set(io.open(r'C:\seostat\drop\drop-storage\meyer7-kompanii-klyuchi.txt', encoding='utf-8').read().split())
    р = [json.loads(s) for s in io.open(os.path.join(DIR, 'meyer7-sdelki-yur.jsonl'), encoding='utf-8') if s.strip()]
    р = [x for x in р if x['ключ'] in ключи and not any(m['сила'] == 'точно' for m in x['совпадения'])]
    готово = set()
    if os.path.exists(ВЫХ):
        for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
            try:
                y = json.loads(s)
                if y.get('ответ'):
                    готово.add((y['ключ'], y['инн_сделки']))
            except (ValueError, KeyError):
                pass
    сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))['компании']
    сд_инн = {m['инн_сделки'] for x in р for m in x['совпадения']}
    о_сд = {}
    c = sqlite3.connect(r'file:C:\sender\obzvon-index.db?mode=ro', uri=True, timeout=120)
    for i, имя, рег, ок in c.execute('select inn, name_short, region, okved_main from obzvon'):
        if str(i) in сд_инн:
            о_сд[str(i)] = (имя or '', рег or '', ок or '')
    c.close()
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    for i, имя, рег, ок in c.execute('select inn, name, region, okved from companies'):
        if str(i) in сд_инн and str(i) not in о_сд:
            о_сд[str(i)] = (имя or '', рег or '', ок or '')
    c.close()
    карта = json.load(io.open(os.path.join(DIR, 'meyer7-zenno-surrogat.json'), encoding='utf-8'))
    сур = collections.defaultdict(list)
    for кл, i in карта.items():
        сур[i].append(кл)
    кк = {x['ключ'] for x in р} | {k for x in р for k in сур.get(x['ключ'], [])}
    файлы = collections.defaultdict(list)
    for п in Z.ZENNO:
        if os.path.isdir(п):
            for e in os.scandir(п):
                if e.name.endswith('.html'):
                    k, _, n = e.name[:-5].rpartition('_')
                    if k in кк and n.isdigit():
                        файлы[k].append((e.path, int(n), п))
    задачи = []
    for x in р:
        for m in x['совпадения']:
            if (x['ключ'], m['инн_сделки']) not in готово and m['как'] == 'юрназвание на сайте':
                задачи.append((x, m))
    print('к проверке пар (сайт, компания сделки)', len(задачи), '| уже', len(готово), flush=True)

    def куски(x, m):
        стр = []
        for k in [x['ключ']] + сур.get(x['ключ'], []):
            стр += Z.страницы_кэша(k) + Z.страницы_зенки(k, файлы.get(k) or [])
        имя = m['что'].split('«')[-1].rstrip('»').strip()[:30]
        out, были, заг = [], set(), ''
        for y in стр:
            h = y.get('html') or ''
            if not заг:
                мз = re.search(r'<title[^>]*>(.*?)</title>', h, re.S | re.I)
                заг = Z.чистый(мз.group(1))[:120] if мз else ''
            if имя.lower() not in h.lower():
                continue
            for кус in Z.окна(h):
                т = Z.чистый(кус).strip()
                if имя.lower() in т.lower() and т[:60] not in были:
                    были.add(т[:60])
                    out.append('[%s] %s' % ((y.get('url') or '')[-50:], т[:280]))
                if len(out) >= 4:
                    return заг, out
        return заг, out

    def пачка(п_):
        блоки = []
        for j, (x, m) in enumerate(п_, 1):
            заг, кус = куски(x, m)
            имя, рег, ок = о_сд.get(m['инн_сделки'], ('', '', ''))
            блоки.append('%d. Сайт %s (заголовок: %s) | компания в нашей базе по этому сайту: %s\n Компания СДЕЛКИ: %s, ИНН %s, %s, ОКВЭД %s; '
                         'на сайте как «%s» (страниц: %s)\n Куски страниц:\n%s' % (
                             j, x['домен'], заг, (сп.get(x['ключ']) or {}).get('имя', ''), имя, m['инн_сделки'], рег, ок, m['что'],
                             m.get('страниц'), '\n'.join('   - ' + k for k in кус) or '   -'))
        ответ = KK.модель(ПРОМПТ.format(сайты='\n\n'.join(блоки)), True) or {}
        for j, (x, m) in enumerate(п_, 1):
            y = ответ.get(j) or {}
            писать({'ключ': x['ключ'], 'домен': x['домен'], 'инн_сделки': m['инн_сделки'], 'что': m['что'], 'сила': m['сила'],
                    'ответ': y.get('ответ') or '', 'почему': y.get('почему') or '', 'сделки': x['сделки'].get(m['инн_сделки'], '')})

    from concurrent.futures import ThreadPoolExecutor
    пачки = [задачи[k:k + 8] for k in range(0, len(задачи), 8)]
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(пачка, пачки))
    посл = {}
    for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
        try:
            y = json.loads(s)
            посл[(y['ключ'], y['инн_сделки'])] = y
        except (ValueError, KeyError):
            pass
    import shutil
    shutil.copyfile(ВЫХ, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХ)))
    print('===ИТОГ МОДЕЛИ===', json.dumps({'%s: %s' % k: v for k, v in collections.Counter((y['сила'], y['ответ']) for y in посл.values()).most_common()},
                                      ensure_ascii=False), 'за %.1f мин' % ((time.time() - t0) / 60), flush=True)


if __name__ == '__main__':
    sys.path.insert(0, DIR)
    sys.path.insert(0, r'C:\sender')
    os.chdir(DIR)
    os.environ.update({'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'PILOT_MODEL': 'gpt-6-luna',
                       'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'sdelki_yur_model_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_sdelki_yur_model.py'), '--vnutri'], cwd=DIR,
                                 creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                                 close_fds=False)
        time.sleep(20)
        print('===ИТОГ===')
        print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                         ensure_ascii=False))
        sys.exit(0)
    main()
