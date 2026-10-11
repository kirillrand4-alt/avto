# -*- coding: utf-8 -*-
r"""Выгрузка «нашей базы» для Excel meyer7 (<набор>-baza.jsonl -> дроп): база обзвона (директор, телефоны, почты, сайты),
люди тех. служб из enrich.db (протоколы РТН, ЕИС, tender.pro) и контакты Checko из enrich.requisites (телефоны, почты,
сайт). 11.10, ревизия (№41/46, 2-06/2-09): у ~556 компаний без контактов в Excel контакты Checko есть, но не выгружались.
Запуск: run_script_on_server.py meyer_baza_vyg.py (только чтение баз, запись jsonl с fsync).
"""
import io, json, os, re, sqlite3, shutil, collections
print('===ИТОГ===')
сп = json.load(io.open(r'C:\sender\server\meyer7-spisok.json', encoding='utf-8'))['компании']
инны = [i for i in сп if i.isdigit()]
ТЕХ = re.compile(r'главн\w*\s+(?:инженер|механик|энергетик|технолог)|гл\.\s*(?:инженер|механик|энергетик|технолог)|'
                 r'техническ\w*\s+директор|техдиректор|директор\w*\s+по\s+(?:производств|техническ|качеств|снабжен|закупк)|'
                 r'начальник\w*\s+(?:производств|цеха|ОТК|отдела\s+(?:качеств|снабжен|закуп|главного\s+механика|главного\s+энергетика))|'
                 r'(?:главн\w*|ведущ\w*)\s+специалист\w*\s+по\s+(?:снабжен|закупк)|снабжен|ОТК|лаборатори', re.I)
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
out = {}
for пачка in range(0, len(инны), 500):
    ч = инны[пачка:пачка + 500]
    м = ','.join('?' * len(ч))
    for inn, d, dp, ph, em in c.execute('select inn, director, coalesce(sites,""), phones_base, emails_base from obz.obzvon where inn in (%s)' % м, ч):
        x = out.setdefault(str(inn), {'inn': str(inn), 'люди': []})
        x['директор'] = (d or '').strip()
        x['тел'] = (ph or '').strip()
        x['почты'] = (em or '').strip()
        x['сайты'] = (dp or '').strip()
    for inn, тел, почт, сайт in c.execute('select inn, coalesce(phones_checko,""), coalesce(emails_checko,""), '
                                         'coalesce(site_checko,"") from requisites where inn in (%s)' % м, ч):
        if тел or почт or сайт:
            x = out.setdefault(str(inn), {'inn': str(inn), 'люди': []})
            x['checko_тел'], x['checko_почты'], x['checko_сайт'] = str(тел).strip(), str(почт).strip(), str(сайт).strip()
    for inn, person, post, role, phone, email, source, url, obs, принадл in c.execute(
            'select inn, person, post, role, phone, email, source, source_url, observed_at, prinadlezhnost_inn from people '
            'where inn in (%s)' % м, ч):
        if not person or not ТЕХ.search((post or '') + ' ' + (role or '')):
            continue
        if принадл and str(принадл) != str(inn):
            continue
        x = out.setdefault(str(inn), {'inn': str(inn), 'люди': []})
        x['люди'].append({'фио': person.strip(), 'должность': (post or role or '').strip()[:120], 'тел': (phone or '').strip(),
                          'почта': (email or '').strip(), 'источник': (source or '')[:60], 'дата': (obs or '')[:10],
                          'url': (url or '')[:200]})
c.close()
вых = r'C:\sender\server\meyer7-baza.jsonl'
with io.open(вых, 'w', encoding='utf-8') as f:
    for x in out.values():
        f.write(json.dumps(x, ensure_ascii=False) + '\n')
    f.flush(); os.fsync(f.fileno())
shutil.copyfile(вых, r'C:\seostat\drop\drop-storage\meyer7-baza.jsonl')
print('компаний', len(out), 'с тел', sum(1 for x in out.values() if x.get('тел')), 'с почтой', sum(1 for x in out.values() if x.get('почты')),
      'с директором', sum(1 for x in out.values() if x.get('директор')),
      'checko тел/почта', sum(1 for x in out.values() if x.get('checko_тел')), sum(1 for x in out.values() if x.get('checko_почты')), 'с людьми-тех', sum(1 for x in out.values() if x['люди']),
      'людей', sum(len(x['люди']) for x in out.values()))
print(collections.Counter(ч['источник'][:30] for x in out.values() for ч in x['люди']).most_common(10))
print(collections.Counter(bool(ч['тел'] or ч['почта']) for x in out.values() for ч in x['люди']))
