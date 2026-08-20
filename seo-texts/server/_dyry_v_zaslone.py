# -*- coding: utf-8 -*-
r"""Две дыры заслона в числах: без вердикта и «принимает всё»."""
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
проба = {}
for r in c.execute('select lower(email) e, verdict v, ts, coalesce(source,"") s from addr_probe'):
    проба[r['e']] = (r['v'], r['ts'], r['s'])
отпр = [dict(r) for r in c.execute('select lower(email) e, ts from send_log')]
свод = {'отправок': len(отпр), 'по_вердикту_на_момент_отправки': {}}
for о in отпр:
    в, ts, s = проба.get(о['e'], (None, None, None))
    if в is None:
        к = 'вердикта нет вовсе'
    elif ts and str(ts) > str(о['ts']):
        к = 'вердикт появился ПОСЛЕ отправки'
    else:
        к = в
    свод['по_вердикту_на_момент_отправки'][к] = \
        свод['по_вердикту_на_момент_отправки'].get(к, 0) + 1
# сколько баунсов пришлось на каждую группу
баунсы = {r[0].lower() for r in c.execute(
    "select r.email from events e join recipients r on r.id=e.recipient_id "
    "where e.event_type='bounce' and r.email is not null")}
свод['баунсов'] = len(баунсы)
пг = {}
for a in баунсы:
    в, ts, s = проба.get(a, (None, None, None))
    ключ = 'вердикт от самой отбивки' if s == 'hard-bounce' else (в or 'нет вердикта')
    пг[ключ] = пг.get(ключ, 0) + 1
свод['баунсы_по_вердикту'] = пг
# есть ли у компаний альтернатива получше, чем «принимает всё»
# альтернатива получше: у той же компании адрес с вердиктом «есть»
по_инн = {}
for r in c.execute(
        'select r.inn, lower(r.email) e, p.verdict v from recipients r '
        'join addr_probe p on lower(p.email)=lower(r.email) '
        "where coalesce(r.inn,'')<>''"):
    по_инн.setdefault(r['inn'], []).append((r['e'], r['v']))
всё, есть_замена = 0, 0
for инн, спис in по_инн.items():
    вердикты = {v for _e, v in спис}
    n = sum(1 for _e, v in спис if v == 'принимает всё')
    всё += n
    if n and 'есть' in вердикты:
        есть_замена += n
свод['получателей_принимает_всё'] = всё
свод['из_них_у_компании_есть_адрес_с_вердиктом_есть'] = есть_замена
c.close()
print(json.dumps(свод, ensure_ascii=False, indent=1))
