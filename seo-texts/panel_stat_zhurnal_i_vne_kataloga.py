# -*- coding: utf-8 -*-
"""Вторая доводка: дата последнего действия и раскрываемый список назначений вне каталога.

ПОЧЕМУ. Замер показал, что «0 / 0 / 0 действий» и «просрочено 0» — правда, а не баг:
последняя запись в activity_log от 2026-08-24, а next_contact_at не заполнен ни в одной
из 94 строк. Но три нуля подряд на странице читаются как «статистика не работает».
Поэтому рядом с окнами ставится общее число записей и дата последней — тогда ноль
означает «давно не звонили», а не «счётчик сломан».

18 назначений на ИНН вне каталога делаю раскрываемым списком: у трёх продавцов есть
карточки, которые они не могут открыть, и это единственное число на странице, по которому
нужно действие.
"""
import io
import os
import subprocess
import time

KOREN = r'C:\centro2'
ROUTES = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
SHABLON = os.path.join(KOREN, 'app', 'templates', 'centro_stats.html')
VENV = r'C:\seostat\.venv\Scripts\python.exe'
PORT = 8016
LOG = os.path.join(KOREN, 'centro2.log')

itog = []
nado = 0
sdelano = 0


def skazat(s):
    itog.append(s)
    print(s)


def pravka(put, staro, novo, priznak, imya):
    global nado, sdelano
    nado += 1
    t = io.open(put, encoding='utf-8').read()
    if priznak in t:
        skazat('%s: уже правлено' % imya)
        sdelano += 1
        return
    if staro not in t:
        skazat('%s: ЯКОРЬ НЕ НАЙДЕН, правка НЕ внесена' % imya)
        return
    io.open(put, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    sdelano += 1
    skazat('%s: внесено' % imya)


# ---------------------------------------------------------------- 1. маршрут
pravka(
    ROUTES,
    '''        naznachennye = {str(r[0]).strip() for r in conn.execute(
            "SELECT DISTINCT inn FROM company_assignment")}
        ochered = _stats_ochered(conn, vybrannyy, imena) if vybrannyy else []''',
    '''        naznachennye = {str(r[0]).strip() for r in conn.execute(
            "SELECT DISTINCT inn FROM company_assignment")}
        # Кому именно достались карточки, которых нет в каталоге. Это единственное
        # число на странице, по которому требуется действие, поэтому оно должно
        # раскрываться до списка, а не оставаться цифрой.
        vne = sorted(naznachennye - set(imena))[:500]
        vne_spisok = [dict(r) for r in conn.execute(
            "SELECT username, inn FROM company_assignment WHERE inn IN (%s) "
            "ORDER BY username, inn" % ",".join("?" * len(vne)), vne)] if vne else []
        deystviy = conn.execute(
            "SELECT COUNT(*), MAX(created_at) FROM activity_log").fetchone()
        ochered = _stats_ochered(conn, vybrannyy, imena) if vybrannyy else []''',
    'vne_spisok', 'маршрут, сбор данных')

pravka(
    ROUTES,
    '''    obshchee["dvum_prodavcam"] = max(0, obshchee["naznacheno"] - len(naznachennye))''',
    '''    obshchee["dvum_prodavcam"] = max(0, obshchee["naznacheno"] - len(naznachennye))
    obshchee["vne_kataloga_spisok"] = vne_spisok
    obshchee["vsego_deystviy"] = deystviy[0] or 0
    obshchee["poslednee_deystvie"] = str(deystviy[1] or "")[:16].replace("T", " ")''',
    'vsego_deystviy', 'маршрут, выдача')

# ---------------------------------------------------------------- 2. шаблон
pravka(
    SHABLON,
    '''    <div class="plitka"><b>{{ obshchee.aktivnost.get(1, 0) }} / {{ obshchee.aktivnost.get(7, 0) }} / {{ obshchee.aktivnost.get(30, 0) }}</b><span>действий за сутки / 7 дней / 30 дней</span></div>''',
    '''    <div class="plitka"><b>{{ obshchee.aktivnost.get(1, 0) }} / {{ obshchee.aktivnost.get(7, 0) }} / {{ obshchee.aktivnost.get(30, 0) }}</b><span>действий за сутки / 7 дней / 30 дней</span></div>
    <div class="plitka"><b>{{ obshchee.vsego_deystviy }}</b><span>действий в журнале всего, последнее {{ obshchee.poslednee_deystvie or '—' }}</span></div>''',
    'действий в журнале всего', 'шаблон, плитка журнала')

pravka(
    SHABLON,
    '''  <h2>По продавцам</h2>''',
    '''  {% if obshchee.vne_kataloga_spisok %}
  <details style="margin:4px 0 16px">
    <summary style="cursor:pointer;color:#b4232a;font-weight:600">{{ obshchee.vne_kataloga_spisok|length }} назначений смотрят на ИНН, которого нет в каталоге — раскрыть</summary>
    <p class="pometka">Продавец видит эти карточки в своей очереди, но открыть не может:
      компании с таким ИНН в базе каталога нет. Либо каталог сменился после распределения,
      либо назначение делалось по списку из другого источника.</p>
    <table class="stat">
      <thead><tr><th>Продавец</th><th>ИНН</th></tr></thead>
      <tbody>
      {% for v in obshchee.vne_kataloga_spisok %}
        <tr><td>{{ v.username }}</td><td>{{ v.inn }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </details>
  {% endif %}

  <h2>По продавцам</h2>''',
    'раскрыть</summary>', 'шаблон, список вне каталога')


# ---------------------------------------------------------------- 3. перезапуск
def pid_na_portu(port):
    r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    return {l.split()[-1] for l in r.stdout.decode('cp866', 'replace').splitlines()
            if (':%d ' % port) in l and 'LISTENING' in l.upper()}


for p in pid_na_portu(PORT):
    subprocess.run(['taskkill', '/PID', p, '/F'], capture_output=True, timeout=60)
time.sleep(2)
log = io.open(LOG, 'a', encoding='utf-8', errors='replace')
log.write('\n===== перезапуск %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
log.flush()
subprocess.Popen(
    [VENV, '-m', 'uvicorn', 'app.obzvon:app', '--host', '127.0.0.1', '--port', str(PORT)],
    cwd=KOREN, stdout=log, stderr=subprocess.STDOUT,
    creationflags=0x00000008 | 0x00000200, close_fds=True,
    env=dict(os.environ, PYTHONIOENCODING='utf-8', ENV_FILE=os.path.join(KOREN, '.env')))
for _ in range(30):
    time.sleep(1)
    if pid_na_portu(PORT):
        break
skazat('слушают порт %d: %s' % (PORT, ', '.join(sorted(pid_na_portu(PORT))) or 'НИКТО'))

print('\n===== ИТОГ =====')
print('правок внесено: %d из %d' % (sdelano, nado))
for s in itog:
    print(s)
