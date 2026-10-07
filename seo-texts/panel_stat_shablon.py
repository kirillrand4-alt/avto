# -*- coding: utf-8 -*-
"""Шаблон страницы статистики + ссылка на неё из админки. Только в копии."""
import io
import os

KOREN = r'C:\centro2'
SHABLON = os.path.join(KOREN, 'app', 'templates', 'centro_stats.html')
ADMIN = os.path.join(KOREN, 'app', 'templates', 'centro_admin.html')

HTML = '''<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Статистика — Центробежные</title>
  <link rel="stylesheet" href="{{ base_path }}/static/css/centro.css">
  <style>
    .stat-setka{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0}
    .plitka{border:1px solid #d7dde5;border-radius:8px;padding:10px 14px;min-width:150px}
    .plitka b{display:block;font-size:22px;line-height:1.1}
    .plitka span{color:#5a6472;font-size:12px}
    table.stat{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}
    table.stat th,table.stat td{border:1px solid #dde3ea;padding:5px 8px;text-align:left}
    table.stat th{background:#2f5496;color:#fff;font-weight:600}
    table.stat tr:nth-child(even) td{background:#f6f8fb}
    .prosr{color:#b4232a;font-weight:600}
    .nead{color:#8a94a0}
    .pometka{color:#5a6472;font-size:12px;margin:4px 0 14px}
  </style>
</head>
<body>
<header class="topbar">
  <a href="{{ base_path }}/centro">← Моя база</a>
  <a href="{{ base_path }}/centro/admin">Распределение</a>
  <strong>Статистика</strong>
  <span>{{ user.username }}</span>
</header>
<main class="admin-page">

  <h2>Общая статистика</h2>
  <div class="stat-setka">
    <div class="plitka"><b>{{ obshchee.v_kataloge }}</b><span>компаний в каталоге</span></div>
    <div class="plitka"><b>{{ obshchee.naznacheno }}</b><span>назначено продавцам</span></div>
    <div class="plitka"><b>{{ obshchee.ne_naznacheno }}</b><span>не назначено</span></div>
    <div class="plitka"><b>{{ obshchee.obrabotano }}</b><span>обработано</span></div>
    <div class="plitka"><b class="{% if obshchee.prosrocheno %}prosr{% endif %}">{{ obshchee.prosrocheno }}</b><span>просрочен следующий контакт</span></div>
    <div class="plitka"><b>{{ obshchee.kommentariev }}</b><span>комментариев</span></div>
    <div class="plitka"><b>{{ obshchee.skryto }}</b><span>скрыто компаний</span></div>
    <div class="plitka"><b>{{ obshchee.aktivnost.get(1, 0) }} / {{ obshchee.aktivnost.get(7, 0) }} / {{ obshchee.aktivnost.get(30, 0) }}</b><span>действий за сутки / 7 дней / 30 дней</span></div>
  </div>

  <h3>По результатам звонка</h3>
  <table class="stat">
    <thead><tr><th>Результат</th><th>Компаний</th><th>Доля</th></tr></thead>
    <tbody>
    {% for kod, n in obshchee.po_rezultatu|dictsort(by='value', reverse=true) %}
      <tr>
        <td>{{ metki.get(kod, kod) }}</td>
        <td>{{ n }}</td>
        <td>{% if obshchee.naznacheno %}{{ '%.1f'|format(100.0 * n / obshchee.naznacheno) }} %{% else %}—{% endif %}</td>
      </tr>
    {% else %}<tr><td colspan="3">Назначений нет.</td></tr>{% endfor %}
    </tbody>
  </table>

  <h2>По продавцам</h2>
  <p class="pometka">Нажмите на имя, чтобы увидеть очередь этого продавца в том же
    порядке, в каком её видит он сам.</p>
  <table class="stat">
    <thead><tr>
      <th>Продавец</th><th>Роль</th><th>Назначено</th><th>Обработано</th><th>Осталось</th>
      <th>Просрочено</th><th>Сумма балла</th><th>Средний балл</th><th>Последнее действие</th>
    </tr></thead>
    <tbody>
    {% for p in prodavcy %}
      <tr{% if not p.aktiven %} class="nead"{% endif %}>
        <td><a href="{{ base_path }}/centro/stats?user={{ p.username }}">{{ p.username }}</a>{% if not p.aktiven %} (отключён){% endif %}</td>
        <td>{{ p.role }}</td>
        <td>{{ p.naznacheno }}</td>
        <td>{{ p.obrabotano }}</td>
        <td>{{ p.ostalos }}</td>
        <td{% if p.prosrocheno %} class="prosr"{% endif %}>{{ p.prosrocheno }}</td>
        <td>{{ '%.1f'|format(p.ball_summa) }}</td>
        <td>{{ '%.2f'|format(p.ball_sredniy) }}</td>
        <td>{{ p.poslednyaya_aktivnost[:16].replace('T', ' ') or '—' }}</td>
      </tr>
      <tr><td colspan="9" style="font-size:12px;color:#5a6472">
        {% for kod, n in p.po_rezultatu|dictsort(by='value', reverse=true) %}{{ metki.get(kod, kod) }}: {{ n }}{% if not loop.last %} · {% endif %}{% endfor %}
      </td></tr>
    {% else %}<tr><td colspan="9">Пользователей нет.</td></tr>{% endfor %}
    </tbody>
  </table>

  {% if vybrannyy %}
  <h2>Очередь продавца {{ vybrannyy }} — {{ ochered|length }} компаний</h2>
  <p class="pometka">Порядок тот же, что у продавца: сначала новые, затем перезвоны по
    сроку, внутри — по убыванию балла. Красным отмечен просроченный следующий контакт.</p>
  <table class="stat">
    <thead><tr>
      <th>№</th><th>Компания</th><th>ИНН</th><th>Балл</th><th>Результат</th>
      <th>Последний контакт</th><th>Следующий контакт</th><th>Телефон</th><th>Тех / Закуп</th>
    </tr></thead>
    <tbody>
    {% for z in ochered %}
      <tr>
        <td>{{ loop.index }}</td>
        <td><a href="{{ base_path }}/centro?{{ poisk_param }}={{ z.inn }}">{{ z.nazvanie or '—' }}</a></td>
        <td>{{ z.inn }}</td>
        <td>{{ '%.1f'|format(z.assignment_score or 0) }}</td>
        <td>{{ metki.get(z.call_result, z.call_result) }}</td>
        <td>{{ (z.last_contact_at or '')[:16].replace('T', ' ') or '—' }}</td>
        <td>{{ (z.next_contact_at or '')[:16].replace('T', ' ') or '—' }}</td>
        <td>{{ 'да' if z.has_phone else '—' }}</td>
        <td>{{ 'тех' if z.has_tech else '' }}{% if z.has_tech and z.has_purchaser %} / {% endif %}{{ 'закуп' if z.has_purchaser else '' }}{% if not z.has_tech and not z.has_purchaser %}—{% endif %}</td>
      </tr>
    {% else %}<tr><td colspan="9">У этого продавца нет назначений.</td></tr>{% endfor %}
    </tbody>
  </table>
  {% endif %}

</main>
</body>
</html>
'''

io.open(SHABLON, 'w', encoding='utf-8').write(HTML)
print('шаблон записан: %s (%d знаков)' % (SHABLON, len(HTML)))

# ссылка со страницы распределения на статистику
t = io.open(ADMIN, encoding='utf-8').read()
if '/centro/stats' not in t:
    t = t.replace(
        '<strong>Статистика распределения</strong>',
        '<a href="{{ base_path }}/centro/stats">Статистика</a>'
        '<strong>Распределение</strong>', 1)
    io.open(ADMIN, 'w', encoding='utf-8').write(t)
    print('в centro_admin.html добавлена ссылка на статистику')
else:
    print('ссылка в админке уже была')
