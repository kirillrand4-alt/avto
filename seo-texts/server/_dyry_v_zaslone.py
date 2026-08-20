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
свод['получателей_принимает_всё'] = c.execute(
    "select count(*) from recipients r join addr_probe p on lower(p.email)=lower(r.email) "
    "where p.verdict='принимает всё'").fetchone()[0]
свод['из_них_у_компании_есть_адрес_с_вердиктом_есть'] = c.execute("""
   select count(distinct r.id) from recipients r
     join addr_probe p on lower(p.email)=lower(r.email)
    where p.verdict='принимает всё'
      and exists (select 1 from recipients r2
                    join addr_probe p2 on lower(p2.email)=lower(r2.email)
                   where r2.inn=r.inn and p2.verdict='есть')""").fetchone()[0]
c.close()
print(json.dumps(свод, ensure_ascii=False, indent=1))
