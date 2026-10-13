# -*- coding: utf-8 -*-
# 13.10, владелец: «запускай» (этап 5 поиска ИНН). Ключи файлов базы НЕ меняются — найденный ИНН ложится отдельным
# файлом meyer7-inn-sayt.jsonl (ключ САЙТ:<домен> → ИНН/УНП), сборка Excel (pilot_xlsx) применяет его сама:
# надёжный (правило или модель «высокая») — показ ИНН, регион/ОКВЭД/выручка, база обзвона, проверка активных сделок
# по ИНН, склейка с компанией списка под тем же ИНН; вероятный (модель «средняя») — колонка «ИНН вероятный ⚠» и
# проверка сделок. Здесь — сбор этих данных: из meyer7-inn-poisk.jsonl + раздел списка, где ИНН уже есть (компании/
# снято/ниже порога…), выручка/директор/телефоны/почты из obzvon-index.db и enrich.db. Итог — сервер + дроп (fsync).
import collections, io, json, os, shutil, sqlite3, time
DIR = r'C:\sender\server'
ВЫХ = os.path.join(DIR, 'meyer7-inn-sayt.jsonl')
print('===ИТОГ===', time.strftime('%H:%M:%S'))
посл = {}
for s in io.open(os.path.join(DIR, 'meyer7-inn-poisk.jsonl'), encoding='utf-8', errors='replace'):
    try:
        r = json.loads(s)
        посл[r['ключ']] = r
    except (ValueError, KeyError):
        pass
сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))
раздел = {}
for р in ('компании', 'снято', 'ниже_порога', 'на_решение', 'ждут_оквэд'):
    for i, к in (сп.get(р) or {}).items():
        раздел.setdefault(i, (р, к))
пр = [r for r in посл.values() if r.get('итог') == 'принят']
инны = {(r.get('инн') or '') for r in пр if (r.get('инн') or '').isdigit()}
obz, enr = {}, {}
c = sqlite3.connect(r'file:C:\sender\obzvon-index.db?mode=ro', uri=True, timeout=120)
for р in c.execute('select inn, director, phones_base, emails_base, revenue_rub, god_otch, okved_main, region from obzvon'):
    if str(р[0]) in инны:
        obz[str(р[0])] = р
c.close()
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
for р in c.execute('select inn, director, director_post, phones, best_email, revenue_rub, revenue_year, okved, region from companies'):
    if str(р[0]) in инны:
        enr[str(р[0])] = р
c.close()
сч = collections.Counter()
with io.open(ВЫХ + '.tmp', 'w', encoding='utf-8') as f:
    for r in пр:
        к = r.get('кандидат') or {}
        инн = r.get('инн') or r.get('ключ_новый') or ''
        мод = (r.get('как') or '').startswith('модель')
        надёжн = 'вероятный' if мод and r.get('уверенность') == 'средняя' else 'надёжный'
        о, е = obz.get(инн), enr.get(инн)
        выр = max([float(x or 0) for x in ((о or [None] * 8)[4], (е or [None] * 9)[5])] + [0.0])
        база = {}
        if о or е:
            тел = ' | '.join(dict.fromkeys(x.strip() for x in ((о or [''] * 8)[2] or '').replace(',', '|').split('|') + ((е or [''] * 9)[3] or '').replace(',', '|').split('|') if x.strip()))
            почты = ' | '.join(dict.fromkeys(x.strip().lower() for x in ((о or [''] * 8)[3] or '').replace(',', '|').split('|') + [((е or [''] * 9)[4] or '')] if '@' in (x or '')))
            база = {'inn': инн, 'люди': [], 'директор': (о and о[1]) or (е and е[1]) or '', 'тел': тел, 'почты': почты, 'сайты': ''}
        р_, к_ = раздел.get(инн, ('', {}))
        x = {'ключ': r['ключ'], 'домен': r.get('домен') or '', 'инн': инн, 'надёжность': надёжн,
             'как': ('модель (%s): %s' % (r.get('уверенность'), r.get('как', '')[8:])) if мод else r.get('как', ''),
             'почему': r.get('почему') or '', 'юрлицо': к.get('имя') or '', 'регион': к.get('регион') or (о and о[7]) or '',
             'город': к.get('город') or '', 'оквэд': к.get('оквэд') or (о and о[6]) or (е and е[7]) or '',
             'руководитель': к.get('руководитель') or '', 'должность': к.get('должность') or '', 'огрн': к.get('огрн') or '',
             'выручка': выр or 0, 'выручка_год': str((е and е[6]) or (о and о[5]) or ''), 'база': база,
             'в_списке': р_, 'в_списке_почему': (к_.get('причина') or к_.get('почему') or к_.get('примечание') or '')[:200] if р_ else ''}
        f.write(json.dumps(x, ensure_ascii=False) + '\n')
        сч[надёжн] += 1
        сч['%s: ИНН в разделе «%s»' % (надёжн, р_ or 'нет')] += 1
        сч['%s: есть выручка' % надёжн] += bool(выр)
        сч['%s: есть в базе обзвона/enrich' % надёжн] += bool(база)
    f.flush()
    os.fsync(f.fileno())
os.replace(ВЫХ + '.tmp', ВЫХ)
shutil.copyfile(ВЫХ, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХ)))
for k, v in sorted(сч.items()):
    print(' ', k, v)
