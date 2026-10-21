# -*- coding: utf-8 -*-
r"""fixKO (21.10): главная панели КЦ (/obzvon/centro) – списком, как у Meyer; одна шапка; продавцы по ФИО.

Владелец 21.10: «сделать страницу КЦ такой же по структуре, как Meyer /obzvon-meyer/centro» (план согласован: «делай»);
«user1 – Кирчатов Никита Андреевич, user2 – Журавлев Александр Анатольевич – переименуй их ещё».

Что меняет в C:\seostat (больше ничего):
  * app\api\routes_centro_sales.py –
      /centro без ?inn= – режим СПИСКА (rezhim), с ?inn= – карточка: место в очереди, соседи (pred_inn / sled_inn), ссылка
      «к списку» на ту страницу, где компания; последний комментарий по компаниям страницы списка (видимость как в карточке);
      /centro/hide – поле kuda: после скрытия/возврата компании ЦЕЛИКОМ – назад в список (раньше referer вёл на ?inn= уже
      скрытой компании – 404; в режиме списка так было бы при каждом скрытии);
      блок fixKO в конце: fixKO_fio() – {логин: ФИО} из users.fio (глобал шаблонов, им же шаблоны узнают новый код);
      в тексте статистики «менеджер …» – по ФИО;
  * app\templates\_ochered_spisok.html (новый) – список очереди: №, компания (ИНН, регион, статус ЕГРЮЛ, если не
      действующая), ОКВЭД, выручка, машины (типы, «под замену», состояния), приговор, контакты, статус (+ перезвон и последний
      комментарий), балл очереди, менеджер (админу); 20/50/100 на странице, строка кликается целиком;
  * app\templates\_shapka.html (новый) – одна шапка: Вся очередь · Взял в работу · Компания не понравилась · Дубль, админу
      ещё Распределение и Статистика; активная вкладка подчёркнута; «Список компаний» и «Парк машин» убраны (страницы живы
      по прямому адресу, их код не тронут);
  * app\templates\centro.html – шапка -> _shapka.html, режим списка, «← к списку · Компания N из M», «Сохранить и перейти
      дальше» -> следующая компания очереди, «← Предыдущая / Пропустить → / К списку» по соседям, «Найти» помнит вкладку,
      ФИО в «Назначено», комментариях и фильтре «Сотрудник»;
  * app\templates\centro_admin.html, fixKS_stats.html – та же шапка, ФИО вместо логинов;
  * data\centro_sales.db – колонка users.fio: user1, user2 (логины не меняются: на них пароли, назначения и история).

8014 (p25) работает на том же коде и подхватывает Python только после своего перезапуска. Всё новое в шаблонах включается
лишь новым кодом (`rezhim is defined`, `fixKO_fio is defined`), поэтому 8014 до перезапуска рендерит главную, карточки и
распределение байт в байт как раньше (проверяется вариантом «смесь»); после перезапуска p25 станет такой же (без ФИО: у p25
колонки fio нет – логины). 8014 и 8011 этот скрипт не перезапускает.

Проверка (TestClient, копии баз в C:\seostat\_stage\fixKO-<время>\db): варианты кода «до», «после», «смесь» (старый Python
+ новые шаблоны), базы КЦ и p25, под admin и продавцами: главная, вкладки, страницы, размер, скрытые, карточки, статистика,
распределение; действия продавцов (сохранить звонок, скрыть и вернуть компанию) на своей копии базы, дамп базы после них.
«Смесь» = «до» байт в байт; «после»: списком те же компании в том же порядке и то же число, что «до»; карточки, соседи,
«дальше», возврат в список после скрытия; в шапке нет «Список компаний» и «Парк машин»; ФИО в КЦ.

    python3 zapusk_na_servere.py fixKO_primenit.py --suho      # только stage и проверки
    python3 zapusk_na_servere.py fixKO_primenit.py --primenit  # замок, копии, запись, py_compile, база (fio), nssm restart obzvon
    python3 zapusk_na_servere.py fixKO_primenit.py --otkat C:\seostat\_bekap\fixKO-<время>
Откат (--otkat): файлы из копии, новые шаблоны удалить, nssm restart obzvon. Колонка users.fio старому коду не мешает.
"""

FIO = {'user1': 'Кирчатов Никита Андреевич', 'user2': 'Журавлев Александр Анатольевич'}

# ======================================================================== шаблон: список очереди
SPISOK = r'''{# fixKO (21.10): режим СПИСКА очереди панели КЦ – перенос с Meyer (там _ochered_spisok.html), колонки – под данные
   КЦ, как у первой версии списка Meyer, когда в нём ещё была база КЦ. Владелец: «вся очередь списком с основными данными
   в списке, когда проваливаешься в компанию – тогда открывается карточка». Те же фильтры и вкладки, что у карточки, тот же
   порядок (_queue_rank), только строками. Обёртка НЕ main.page-wrap намеренно: на ней висит скрипт «⚙ Вид» для блоков
   карточки, и он сам выходит, если такой обёртки нет. #}
{% set _fio = fixKO_fio() if fixKO_fio is defined else {} %}
{% set _deystvuet = ('', 'ACTIVE', 'Действующая компания', 'Действующая организация') %}
<style>
.ochered-wrap{padding:16px 22px;display:grid;gap:12px}
.och-shapka{display:flex;gap:16px;align-items:baseline;flex-wrap:wrap;font-size:13px;color:var(--muted)}
.och-shapka b{color:var(--navy);font-size:15px}
.och-shapka a{color:var(--blue)}
.och-razmer a,.och-razmer strong{margin:0 3px}
table.och-tab{border-collapse:collapse;width:100%}
table.och-tab th,table.och-tab td{padding:8px 10px;border-bottom:1px solid var(--line);
  text-align:left;vertical-align:top;font-size:13px}
table.och-tab th{position:sticky;top:0;background:var(--soft);color:var(--muted);
  font-weight:600;white-space:nowrap;z-index:5}
table.och-tab tbody tr{cursor:pointer}
table.och-tab tbody tr:hover td{background:#f4f6fb}
table.och-tab td.chislo{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
table.och-tab .nazv{font-weight:600;color:var(--blue);text-decoration:none}
table.och-tab .nazv:hover{text-decoration:underline}
table.och-tab .tiho{color:var(--muted);font-size:12px}
.och-tag{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;
  border:1px solid var(--line);white-space:nowrap}
.och-tag.da{background:#e8f6ee;border-color:#b7e1c7;color:#17663a}
.och-tag.net{background:#fdecec;border-color:#f3c2c2;color:#9b1c1c}
.och-tag.zam{background:#fff4e0;border-color:#f3d39b;color:#8a5300}
.och-komm{margin-top:5px;max-width:300px;font-size:12px;line-height:1.35;color:var(--navy);
  white-space:normal;background:#f6f7fb;border-left:3px solid #c7cbe8;padding:4px 7px;border-radius:4px}
.och-podpis{color:var(--muted);font-weight:400;font-size:11px}
.st-metka{display:inline-block;padding:2px 8px;border-radius:5px;font-size:12px;font-weight:600;
  white-space:nowrap;background:#f0f1f3;border:1px solid #d1d4db;color:#525a69}
.st-metka.st-new{padding:0;border:0;background:none;font-weight:400;color:inherit;font-size:13px}
.st-metka.st-ne_ponravilas{background:#fdecec;border-color:#f3c2c2;color:#9b1c1c}
.st-metka.st-v_rabote{background:#e8f6ee;border-color:#b7e1c7;color:#17663a}
.och-mashiny{max-width:260px}
.och-stranicy{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.och-stranicy a{padding:5px 11px;border:1px solid var(--line);border-radius:8px;
  text-decoration:none;color:var(--navy);background:var(--card)}
@media(max-width:760px){
  .ochered-wrap{padding:8px;gap:8px}
  .och-shapka{gap:6px 12px}
  table.och-tab,table.och-tab tbody,table.och-tab tr,table.och-tab td{display:block;width:auto;max-width:none}
  table.och-tab thead{display:none}
  table.och-tab tbody tr{padding:10px 12px;border-bottom:1px solid var(--line)}
  table.och-tab th,table.och-tab td{border-bottom:0;padding:2px 0}
  table.och-tab td.chislo{text-align:left}
  table.och-tab td.och-n,table.och-tab td.och-okved,table.och-tab td.och-ball{display:none}
  table.och-tab td[data-label]::before{content:attr(data-label) ": ";color:var(--muted);font-size:12px}
  .och-shapka>span:last-child{display:none}
  .och-komm,.och-mashiny{max-width:none}
}
</style>
<main class="ochered-wrap">
  {% set ot = (page - 1) * size + 1 %}{% set do = [page * size, total]|min %}
  <section class="card och-shapka">
    <b>{% if total %}Компании {{ ot }}–{{ do }} из {{ total }}{% else %}Компании не найдены{% endif %}</b>
    {% if hidden_companies_n %}<a href="{{ base_path }}/centro?skrytye={{ 0 if pokaz_skrytye else 1 }}">{% if pokaz_skrytye %}вернуться к обычному списку{% else %}скрытых предприятий: {{ hidden_companies_n }}{% endif %}</a>{% endif %}
    <span class="och-razmer">по{% for n in (20, 50, 100) %}{% if n == size %}<strong>{{ n }}</strong>{% else %}<a href="{{ base_path }}/centro?size={{ n }}{% if query_bez_size %}&{{ query_bez_size }}{% endif %}">{{ n }}</a>{% endif %}{% endfor %}на странице</span>
    <span>порядок – как у очереди: сначала новые, потом перезвоны и остальные; внутри – по сроку перезвона и баллу очереди</span>
  </section>
  {% if not total %}
  <div class="state-card"><h2>Компании не найдены</h2><p>Ослабьте фильтры или проверьте распределение.</p></div>
  {% else %}
  <section class="card" style="overflow-x:auto;padding:0">
    <table class="och-tab">
      <thead><tr>
        <th>№</th><th>Компания</th><th>ОКВЭД</th><th>Выручка</th><th>Машины</th><th>Приговор</th><th>Контакты</th><th>Статус</th><th title="По нему строится очередь: больше – выше. Важность предприятия плюс надбавки за то, что до него есть чем дозвониться (телефон, закупщик, технический человек, факты). Минус 1000, если юрлицо ликвидировано.">Балл очереди</th>{% if user.role == 'admin' %}<th>Менеджер</th>{% endif %}
      </tr></thead>
      <tbody>
      {% for c in rows %}
      {% set ssylka = base_path ~ '/centro?inn=' ~ c.inn ~ (('&' ~ query_string) if query_string else '') %}
      <tr data-href="{{ ssylka }}">
        <td class="chislo tiho och-n">{{ ot + loop.index0 }}</td>
        <td><a class="nazv" href="{{ ssylka }}">{{ c.predpriyatie or c.name_short or c.inn }}</a>
          <br><span class="tiho">{{ c.inn }}{% if c.region %} · {{ c.region }}{% endif %}</span>{% if (c.status_egrul or '')|string not in _deystvuet %} <span class="och-tag net">{{ c.status_egrul }}</span>{% endif %}</td>
        <td class="och-okved" title="{{ c.okved or '' }}">{{ (c.okved or '–')|truncate(60, True, '…') }}</td>
        <td class="chislo" data-label="Выручка">{{ money_ru(c.vyruchka_rub) or '–' }}</td>
        <td class="och-mashiny" data-label="Машины"><span title="{{ c.tipy_mashin or '' }}">{{ (c.tipy_mashin or '–')|truncate(90, True, '…') }}</span>{% if c.pod_zamenu %} <span class="och-tag zam">под замену</span>{% endif %}
          {% if c.sostoyaniya_mashin %}<br><span class="tiho">{{ c.sostoyaniya_mashin|join(', ') }}</span>{% endif %}</td>
        <td data-label="Приговор">{% if c.verdikt %}<span class="och-tag {{ 'da' if c.verdikt in ['есть', 'покупает', 'планирует'] else ('net' if c.verdikt == 'нет' else '') }}" title="{{ c.verdikt_pochemu or '' }}">{{ c.verdikt }}</span>{% else %}–{% endif %}</td>
        <td class="tiho" data-label="Контакты">{{ c.n_phones or ('есть' if c.has_phone else 0) }} тел · {{ c.n_tech or 0 }} тех · {{ c.n_purchaser or 0 }} закуп{% if c.has_role_phone %}<br><span class="och-tag da">телефон с ролью</span>{% endif %}</td>
        <td>{% set _st = c.call_result or 'new' %}<span class="st-metka st-{{ _st }}">{{ call_results.get(_st, _st) }}</span>
          {% if c.last_contact_at %}<br><span class="tiho">{{ c.last_contact_at[:10] }}</span>{% endif %}
          {% if c.next_contact_at %}<br><span class="tiho">перезвонить {{ c.next_contact_at[:16]|replace('T', ' ') }}</span>{% endif %}
          {% set km = kommentarii.get(c.inn|string) if kommentarii else none %}
          {% if km %}<div class="och-komm" title="{{ km.body }}"><span class="och-podpis">комментарий:</span> {{ km.body|truncate(120, True, '…') }}{% if user.role == 'admin' %}<span class="tiho"> – {{ _fio.get(km.username, km.username) }}{% if (km.created_at or '')[:10] != (c.last_contact_at or '')[:10] %}, {{ (km.created_at or '')[:10] }}{% endif %}</span>{% endif %}</div>{% endif %}</td>
        <td class="chislo tiho och-ball"{% if c.prioritet_pochemu %} title="{{ c.prioritet_pochemu }}"{% endif %}>{{ '%.1f'|format((c.assignment_score or 0)|float) }}</td>
        {% if user.role == 'admin' %}<td data-label="Менеджер">{{ _fio.get(c.assigned_user, c.assigned_user) if c.assigned_user else '–' }}</td>{% endif %}
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </section>
  {% if pages > 1 %}
  <nav class="och-stranicy">
    {% if page > 1 %}<a href="{{ base_path }}/centro?page={{ page - 1 }}{% if query_string %}&{{ query_string }}{% endif %}">← Назад</a>{% endif %}
    <span>{{ page }} / {{ pages }}</span>
    {% if page < pages %}<a href="{{ base_path }}/centro?page={{ page + 1 }}{% if query_string %}&{{ query_string }}{% endif %}">Далее →</a>{% endif %}
  </nav>
  {% endif %}
  {% endif %}
</main>
<script>
/* строка кликается целиком; если выделяли текст (скопировать ИНН) – не прыгаем */
document.querySelectorAll('table.och-tab tr[data-href]').forEach(function (tr) {
  tr.addEventListener('click', function (e) {
    if (e.target.closest('a, details, summary, button')) return;
    if (window.getSelection && String(window.getSelection())) return;
    location.href = tr.dataset.href;
  });
});
</script>
'''

# ======================================================================== шаблон: шапка
SHAPKA = r'''{# fixKO (21.10): ЕДИНСТВЕННАЯ шапка панели КЦ, по образцу Meyer (_shapka.html там). Её подключают главная (список и
   карточка), статистика и распределение. Владелец: «как у Meyer»; «Список компаний» и «Парк машин» из шапки убраны –
   главная сама стала списком (страницы живы по прямому адресу). Не добавлять сюда ссылок по одной странице – шапки снова
   разъедутся. Префикс – base_path из контекста: его передают все три маршрута. #}
{% set _put = request.url.path.rstrip('/') if request is defined else '' %}
{% set _cs = request.query_params.get('call_status', '') if request is defined else '' %}
{% set _fio = fixKO_fio() if fixKO_fio is defined else {} %}
<style>.topbar nav a.active{font-weight:700;text-decoration:underline;text-underline-offset:5px}</style>
<header class="topbar">
  <div class="brand-block">
    <strong>Центробежные</strong>
    <span>база продаж по компрессорному оборудованию</span>
  </div>
  <nav>
    <a href="{{ base_path }}/centro"{% if _put.endswith('/centro') and not _cs %} class="active"{% endif %}>Вся очередь</a>
    <a href="{{ base_path }}/centro?call_status=v_rabote"{% if _put.endswith('/centro') and _cs == 'v_rabote' %} class="active"{% endif %}>Взял в работу</a>
    <a href="{{ base_path }}/centro?call_status=ne_ponravilas"{% if _put.endswith('/centro') and _cs == 'ne_ponravilas' %} class="active"{% endif %}>Компания не понравилась</a>
    <a href="{{ base_path }}/centro?call_status=dubl"{% if _put.endswith('/centro') and _cs == 'dubl' %} class="active"{% endif %}>Дубль — уже работают</a>
    {% if user.role == 'admin' %}<a href="{{ base_path }}/centro/admin"{% if _put.endswith('/centro/admin') %} class="active"{% endif %}>Распределение</a>{% endif %}
    {% if user.role == 'admin' and fixKS_stats_est is defined %}<a href="{{ base_path }}/centro/stats"{% if _put.endswith('/centro/stats') %} class="active"{% endif %}>Статистика</a>{% endif %}
  </nav>
  <div class="user-block">
    <span>{{ _fio.get(user.username, user.username) }} · {{ 'администратор' if user.role == 'admin' else 'продавец' }}</span>
    <form method="post" action="{{ base_path }}/centro/logout"><button class="link-button">Выйти</button></form>
  </div>
</header>
'''

# ======================================================================== код: routes_centro_sales
RCS_PRIZNAK = '# ===================================================================== fixKO (21.10): список очереди, шапка, ФИО'
RCS_KOD = r'''


# ===================================================================== fixKO (21.10): список очереди, шапка, ФИО
# Владелец 21.10: главная КЦ – как у Meyer (список очереди, карточка по клику, одна шапка); «user1 – Кирчатов Никита
# Андреевич, user2 – Журавлев Александр Анатольевич». ФИО – в users.fio (логины не меняются: на них пароли, назначения,
# история). Глобал fixKO_fio одновременно сообщает шаблонам, что код новый: 8014 (p25) на том же коде до своего перезапуска
# его не видит и рендерит главную, карточки и распределение как раньше. У p25 колонки fio нет – там логины.
import sqlite3 as _ko_sq

_KO_FIO = {"t": 0.0, "d": {}}


def _fixKO_fio() -> dict:
    """{логин: ФИО} из users.fio базы продаж этой панели (кэш 30 с); нет колонки – {} (шаблон покажет логин)."""
    if time.time() - _KO_FIO["t"] > 30:
        try:
            with sales.connect() as conn:
                d = {str(r[0]): str(r[1]).strip() for r in conn.execute("SELECT username, fio FROM users")
                     if r[1] and str(r[1]).strip()}
        except _ko_sq.OperationalError:
            d = {}
        _KO_FIO.update(t=time.time(), d=d)
    return _KO_FIO["d"]


templates.env.globals["fixKO_fio"] = _fixKO_fio
# ===================================================================== /fixKO
'''

RCS_PRAVKI = [
    ('маршрут: список без inn, соседи, место в очереди',
     '''    if not chosen and visible:
        chosen = visible[(page - 1) * size]
''',
     '''    # fixKO (21.10): без выбранной компании – СПИСОК очереди, карточка открывается по клику (как у Meyer). Раньше здесь
    # подставлялась первая компания страницы, и вместо списка сразу открывалась её карточка.
    rezhim = "kartochka" if chosen else "spisok"
    pred_inn = sled_inn = ""
    pozitsiya = 0
    if chosen:
        poz = visible.index(chosen)
        pozitsiya = poz + 1
        page = poz // size + 1          # «к списку» – на ту страницу, где эта компания
        pred_inn = visible[poz - 1]["inn"] if poz > 0 else ""
        sled_inn = visible[poz + 1]["inn"] if poz + 1 < len(visible) else ""
''', 'def centro(', 1),
    ('маршрут: ссылки списка',
     '''    filter_query = urlencode(query)
''',
     '''    filter_query = urlencode(query)
    query_bez_size = urlencode({k: v for k, v in query.items() if k != "size"})          # fixKO
    q_spisok = dict(query)
    if rezhim == "kartochka" and page > 1:
        q_spisok["page"] = page
    spisok_ssylka = "%s/centro%s" % (BP, ("?" + urlencode(q_spisok)) if q_spisok else "")
''', 'def centro(', 1),
    ('маршрут: последний комментарий в списке',
     '''    hidden = sales.hidden_for(chosen["inn"]) if chosen else {"fact": {}, "phone": {}}
''',
     '''    # fixKO: последний комментарий по каждой компании страницы списка – под статусом (как у Meyer). Видимость как в
    # карточке: админ – все, продавец – свои. Отдельный запрос по ИНН страницы, а не «последние 1000» карточки: старый
    # комментарий в эту тысячу не попал бы и пропал из списка молча.
    kommentarii: dict = {}
    if rezhim == "spisok":
        inn_str = [str(c["inn"]) for c in visible[(page - 1) * size : page * size]]
        if inn_str:
            with sales.connect() as conn:
                for r in conn.execute(
                    "SELECT inn, username, body, created_at FROM company_comment "
                    "WHERE inn IN (%s) ORDER BY created_at DESC, id DESC" % ",".join("?" * len(inn_str)),
                    inn_str,
                ):
                    if user["role"] == "admin" or r["username"] == user["username"]:
                        kommentarii.setdefault(str(r["inn"]), dict(r))
    hidden = sales.hidden_for(chosen["inn"]) if chosen else {"fact": {}, "phone": {}}
''', 'def centro(', 1),
    ('маршрут: контекст шаблона',
     '''            "query_string": filter_query,
''',
     '''            "query_string": filter_query,
            "query_bez_size": query_bez_size,          # fixKO
            "rezhim": rezhim,
            "pred_inn": pred_inn,
            "sled_inn": sled_inn,
            "pozitsiya": pozitsiya,
            "spisok_ssylka": spisok_ssylka,
            "kommentarii": kommentarii,
''', 'def centro(', 1),
    ('скрытие: поле kuda',
     '''    undo: str = Form(""),
''',
     '''    undo: str = Form(""),
    kuda: str = Form(""),       # fixKO: список, куда вернуться после скрытия/возврата компании целиком
''', 'def hide(', 1),
    ('скрытие: назад в список',
     '''    return RedirectResponse(request.headers.get("referer") or f"{BP}/centro", 303)
''',
     '''    # fixKO: компанию скрыли или вернули целиком – в этой вкладке её карточка больше не откроется (по referer был 404),
    # назад в список, на ту же страницу. Только свой адрес: начинается с префикса панели, без «//».
    if kind == "company" and kuda.startswith(f"{BP}/centro") and "//" not in kuda:
        return RedirectResponse(kuda, 303)
    return RedirectResponse(request.headers.get("referer") or f"{BP}/centro", 303)
''', 'def hide(', 1),
    ('статистика: менеджер по ФИО',
     '''        chasti.append("менеджер %s" % sp["kto"])
''',
     '''        chasti.append("менеджер %s" % _fixKO_fio().get(sp["kto"], sp["kto"]))      # fixKO
''', None, 1),
]

# ======================================================================== шаблон centro.html
FIO_SET = "{% set _fio = fixKO_fio() if fixKO_fio is defined else {} %}"
NAV_STAROE = '''      {% if page > 1 %}<a class="action-button" href="?page={{ page-1 }}{% if query_string %}&{{ query_string }}{% endif %}">← Назад</a>{% endif %}
      {% if page < pages %}<a class="action-button primary" href="?page={{ page+1 }}{% if query_string %}&{{ query_string }}{% endif %}">Пропустить →</a>{% endif %}'''
NAV_NOVOE = ('      {% if rezhim is defined %}'
             '{% if pred_inn %}<a class="action-button" href="{{ base_path }}/centro?inn={{ pred_inn }}{% if query_string %}&{{ query_string }}{% endif %}">← Предыдущая</a>{% endif %}\n'
             '      {% if sled_inn %}<a class="action-button primary" href="{{ base_path }}/centro?inn={{ sled_inn }}{% if query_string %}&{{ query_string }}{% endif %}" title="Перейти к следующей компании без отметки">Пропустить →</a>{% endif %}\n'
             '      <a class="action-button" href="{{ spisok_ssylka }}">К списку</a>'
             '{% else %}' + NAV_STAROE[6:] + '{% endif %}')
CEN_PRIZNAK = '{% include "_ochered_spisok.html" %}'
CEN_PRAVKI = [
    ('шапка: начало', '<header class="topbar">\n  <div class="brand-block">',
     FIO_SET + '{% if rezhim is defined %}{% include "_shapka.html" %}{% else %}<header class="topbar">\n  <div class="brand-block">', None, 1),
    ('шапка: конец; «Найти» помнит вкладку',
     '''  </div>
</header>

<form class="filterbar" method="get">
  <input type="search" name="q"''',
     '''  </div>
</header>{% endif %}

<form class="filterbar" method="get">
  {% if rezhim is defined and request.query_params.get('call_status') %}<input type="hidden" name="call_status" value="{{ request.query_params.get('call_status') }}">{% endif %}<input type="search" name="q"''', None, 1),
    ('фильтр «Сотрудник» по ФИО',
     '''<option value="{{ value }}" {% if request.query_params.get('assigned_user') == value %}selected{% endif %}>{{ value }}</option>''',
     '''<option value="{{ value }}" {% if request.query_params.get('assigned_user') == value %}selected{% endif %}>{{ _fio.get(value, value) }}</option>''', None, 1),
    ('режим списка', '{% elif not company %}',
     '{% elif rezhim == \'spisok\' %}\n  {% include "_ochered_spisok.html" %}\n{% elif not company %}', None, 1),
    ('карточка: «← к списку» и место в очереди',
     '<span class="eyebrow">Компания {{ (page-1)*size+1 }}–{{ [page*size,total]|min }} из {{ total }}',
     '<span class="eyebrow">{% if rezhim is defined %}<a href="{{ spisok_ssylka }}">← к списку</a> · Компания {{ pozitsiya }} из {{ total }}'
     '{% else %}Компания {{ (page-1)*size+1 }}–{{ [page*size,total]|min }} из {{ total }}{% endif %}', None, 1),
    ('карточка: «Назначено» по ФИО',
     "Назначено: <b>{{ company.assigned_user or 'не назначено' }}</b>",
     "Назначено: <b>{{ _fio.get(company.assigned_user, company.assigned_user) or 'не назначено' }}</b>", None, 1),
    ('карточка: после скрытия компании – в список',
     '''    <form method="post" action="{{ base_path }}/centro/hide" class="hide-company">
      <input type="hidden" name="inn" value="{{ company.inn }}">
      <input type="hidden" name="kind" value="company">
      <input type="hidden" name="value" value="{{ company.inn }}">''',
     '''    <form method="post" action="{{ base_path }}/centro/hide" class="hide-company">
      <input type="hidden" name="inn" value="{{ company.inn }}">
      <input type="hidden" name="kind" value="company">
      <input type="hidden" name="value" value="{{ company.inn }}">{% if rezhim is defined %}<input type="hidden" name="kuda" value="{{ spisok_ssylka }}">{% endif %}''', None, 1),
    ('карточка: «Сохранить и перейти дальше» – следующая компания',
     '''    <form method="post" action="{{ base_path }}/centro/save" class="work-form">
      <input type="hidden" name="inn" value="{{ company.inn }}">
      <input type="hidden" name="return_query" value="{{ query_string }}">''',
     '''    <form method="post" action="{{ base_path }}/centro/save" class="work-form">
      <input type="hidden" name="inn" value="{{ company.inn }}">
      <input type="hidden" name="return_query" value="{{ query_string }}{% if sled_inn %}{{ '&' if query_string else '' }}inn={{ sled_inn }}{% endif %}">''', None, 1),
    ('карточка: соседи вместо страниц', NAV_STAROE, NAV_NOVOE, None, 1),
    ('карточка: автор комментария по ФИО', '<article><b>{{ item.username }}</b>',
     '<article><b>{{ _fio.get(item.username, item.username) }}</b>', None, 1),
]

# ======================================================================== шаблон centro_admin.html
ADM_PRIZNAK = 'fixKO_fio is defined'
ADM_STAROE = ('<header class="topbar"><a href="{{ base_path }}/centro">← Моя база</a><strong>Статистика распределения</strong>'
              '<span>{{ user.username }}</span></header>')
ADM_PRAVKI = [
    ('шапка', ADM_STAROE,
     FIO_SET + '{% if fixKO_fio is defined %}{% include "_shapka.html" %}{% else %}' + ADM_STAROE + '{% endif %}', None, 1),
    ('таблица по ФИО', '<tr><td>{{ row.username }}</td>', '<tr><td>{{ _fio.get(row.username, row.username) }}</td>', None, 1),
    ('переназначение по ФИО', '{% for value in sales_users %}<option value="{{ value }}">{{ value }}</option>{% endfor %}',
     '{% for value in sales_users %}<option value="{{ value }}">{{ _fio.get(value, value) }}</option>{% endfor %}', None, 1),
]

# ======================================================================== шаблон fixKS_stats.html (рендерит только новый код)
STAT_PRIZNAK = '{% include "_shapka.html" %}'
STAT_PRAVKI = [
    ('ФИО: начало', '<body>\n', '<body>\n' + FIO_SET, None, 1),
    ('выбор менеджера', '>{{ u }}</option>', '>{{ _fio.get(u, u) }}</option>', None, 1),
    ('строка периода', 'менеджер <b>{{ kto }}</b>', 'менеджер <b>{{ _fio.get(kto, kto) }}</b>', None, 1),
    ('пометка', 'Менеджеры показаны логином: ФИО в панели не заведены.', 'Менеджеры – по ФИО, где оно заведено, иначе логином.', None, 1),
    ('список: менеджер', "<td>{{ z.u or '–' }}</td>", "<td>{{ _fio.get(z.u, z.u) or '–' }}</td>", None, 1),
    ('список: кто скрыл', '({{ z.skr_kto }})', '({{ _fio.get(z.skr_kto, z.skr_kto) }})', None, 1),
    ('список: кто нажал', '(нажал {{ z.otmetka.deystvoval }})', '(нажал {{ _fio.get(z.otmetka.deystvoval, z.otmetka.deystvoval) }})', None, 1),
    ('таблицы по менеджерам', 'else z.u }}', 'else _fio.get(z.u, z.u) }}', None, 1),
    ('таблицы по менеджерам', 'else s.u }}', 'else _fio.get(s.u, s.u) }}', None, 2),
    ('таблицы по менеджерам', 'else t.u }}', 'else _fio.get(t.u, t.u) }}', None, 1),
    ('таблицы по менеджерам', 'else p.u }}', 'else _fio.get(p.u, p.u) }}', None, 1),
    ('лента: кто', '<td>{{ e.kto }}{% if', '<td>{{ _fio.get(e.kto, e.kto) }}{% if', None, 1),
    ('лента: кто нажал', '(нажал {{ e.deystvoval }})', '(нажал {{ _fio.get(e.deystvoval, e.deystvoval) }})', None, 1),
    ('по менеджерам: ссылка', '#ochered-prodavca">{{ p.u }}</a>', '#ochered-prodavca">{{ _fio.get(p.u, p.u) }}</a>', None, 1),
    ('по менеджерам: подсказка', 'Нажмите на логин,', 'Нажмите на имя,', None, 1),
    ('очередь менеджера', 'Очередь менеджера {{ vybrannyy }} –', 'Очередь менеджера {{ _fio.get(vybrannyy, vybrannyy) }} –', None, 1),
]

import hashlib
import html as _html
import io
import json
import os
import py_compile
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\seostat'
DATA = os.path.join(KOREN, 'data')
DROP = r'C:\seostat\drop\drop-storage'
ZAMOK = os.path.join(KOREN, '_zamok.txt')
T = time.strftime('%Y%m%d-%H%M%S')
STAGE = os.path.join(KOREN, '_stage', 'fixKO-' + T)
BEKAP = os.path.join(KOREN, '_bekap', 'fixKO-' + T)
RCS_REL = os.path.join('app', 'api', 'routes_centro_sales.py')
CEN_REL = os.path.join('app', 'templates', 'centro.html')
ADM_REL = os.path.join('app', 'templates', 'centro_admin.html')
STAT_REL = os.path.join('app', 'templates', 'fixKS_stats.html')
SPISOK_REL = os.path.join('app', 'templates', '_ochered_spisok.html')
SHAPKA_REL = os.path.join('app', 'templates', '_shapka.html')
PRAVIM = (RCS_REL, CEN_REL, ADM_REL, STAT_REL)
NOVYE = {SPISOK_REL: SPISOK, SHAPKA_REL: SHAPKA}
BAZY = {'kc': ('centro_sales.db', 'centrifugal.db'), 'p25': ('p25_sales.db', 'p25.db')}
PUT = {'kc': '/obzvon', 'p25': '/p25'}
log = []


def p(*a):
    s = ' '.join(str(x) for x in a)
    log.append(s)
    print(s, flush=True)


def sha(t):
    return hashlib.sha256(t if isinstance(t, bytes) else t.encode('utf-8')).hexdigest()[:16]


def chitat(put):
    return io.open(put, encoding='utf-8', newline='').read() if os.path.exists(put) else None


def pisat(put, t):
    with io.open(put, 'w', encoding='utf-8', newline='') as f:
        f.write(t)


def zamenit(t, pravki, fayl):
    """Замены строка-в-строку: каждое «старое» – ровно n раз (в своей функции, если указана). Стиль строк – как у файла."""
    nl = '\r\n' if '\r\n' in t else '\n'
    for imya, staroe, novoe, oblast, n_ozh in pravki:
        staroe, novoe = staroe.replace('\n', nl), novoe.replace('\n', nl)
        i, j = 0, len(t)
        if oblast:
            i = t.find(oblast)
            if i < 0:
                raise SystemExit('%s: нет функции %s' % (fayl, oblast))
            j = t.find(nl + '@router.', i + 1)
            j = len(t) if j < 0 else j
        kusok = t[i:j]
        n = kusok.count(staroe)
        if n != n_ozh:
            raise SystemExit('%s: «%s» – якорь найден %d раз, ждали %d' % (fayl, imya, n, n_ozh))
        t = t[:i] + kusok.replace(staroe, novoe) + t[j:]
    return t


def pravki(koren) -> list:
    """Правки по якорям, идемпотентно. Возвращает, что сделано."""
    sd = []
    for rel, priznak, spisok, dop in ((RCS_REL, RCS_PRIZNAK, RCS_PRAVKI, RCS_KOD), (CEN_REL, CEN_PRIZNAK, CEN_PRAVKI, ''),
                                      (ADM_REL, ADM_PRIZNAK, ADM_PRAVKI, ''), (STAT_REL, STAT_PRIZNAK, STAT_PRAVKI, '')):
        put = os.path.join(koren, rel)
        t = chitat(put)
        if priznak in t:
            sd.append('%s: уже есть' % os.path.basename(rel))
            continue
        if rel == STAT_REL:          # шапка статистики – блок целиком на подключение общей
            i = t.find('<header class="topbar">')
            j = t.find('</header>', i)
            if t.count('<header class="topbar">') != 1 or j < 0 or 'Список компаний' not in t[i:j]:
                raise SystemExit('fixKS_stats.html: шапка не найдена однозначно')
            t = t[:i] + '{% include "_shapka.html" %}' + t[j + len('</header>'):]
        t = zamenit(t, spisok, os.path.basename(rel))
        if dop:
            nl = '\r\n' if '\r\n' in t else '\n'
            t += dop.replace('\n', nl)
        pisat(put, t)
        if rel.endswith('.py'):
            py_compile.compile(put, doraise=True)
        sd.append('%s: %d правок' % (os.path.basename(rel), len(spisok) + (1 if rel == STAT_REL else 0)))
    for rel, tekst in NOVYE.items():
        put = os.path.join(koren, rel)
        if chitat(put) == tekst:
            sd.append('%s: уже есть' % os.path.basename(rel))
            continue
        if os.path.exists(put):
            raise SystemExit('%s уже есть и отличается – чужой файл?' % rel)
        pisat(put, tekst)
        sd.append('%s: новый' % os.path.basename(rel))
    return sd


def migraciya_fio(put_db) -> list:
    s = sqlite3.connect(put_db, timeout=30)
    try:
        if 'fio' not in [r[1] for r in s.execute('PRAGMA table_info(users)')]:
            s.execute('ALTER TABLE users ADD COLUMN fio TEXT')
        for u, f in FIO.items():
            s.execute('UPDATE users SET fio=? WHERE username=?', (f, u))
        s.commit()
        return s.execute('SELECT username, fio FROM users ORDER BY username').fetchall()
    finally:
        s.close()


def kopiya_bazy(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True, timeout=30)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


# ---------------------------------------------------------------- проверка в отдельном процессе (venv)
NORM = [(re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:\d{2}|Z)?'), '<ВРЕМЯ>'),
        (re.compile(r'\d{2}\.\d{2}(\.\d{4})?,? \d{2}:\d{2}'), '<ВРЕМЯ>')]
URLS = ('/centro', '/centro?call_status=v_rabote', '/centro?call_status=ne_ponravilas', '/centro?call_status=dubl',
        '/centro?page=2', '/centro?size=50', '/centro?skrytye=1')


def norm(t):
    for r, z in NORM:
        t = r.sub(z, t)
    return t


def inns_na_stranice(t):
    """Порядок компаний страницы: строки списка (после) или «Личная очередь» под карточкой (до)."""
    if 'class="och-tab"' in t:
        return re.findall(r'<tr data-href="[^"]*inn=(\d{10,12})', t.split('<tbody>', 1)[1].split('</tbody>', 1)[0])
    if 'class="queue-list"' in t:
        return re.findall(r'centro\?inn=(\d{10,12})', t.split('class="queue-list"', 1)[1].split('</div>', 1)[0])
    return []


def proverka(var_koren, konf, migr, vyhod):
    sys.path.insert(0, var_koren)
    os.chdir(var_koren)
    import logging
    logging.disable(logging.CRITICAL)
    from fastapi.testclient import TestClient
    from app.obzvon import create_app
    from app.api import routes_centro_sales as rcs
    db = os.environ['CENTRO_SALES_DB']
    if migr:
        migraciya_fio(db)
    vn = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    bp = PUT[konf]
    s = sqlite3.connect(db)
    lyudi = [(r[0], r[1]) for r in s.execute('SELECT username, role FROM users WHERE is_active=1 ORDER BY username')]
    s.close()
    if not any(r == 'admin' for _u, r in lyudi):
        lyudi = [('admin', 'admin')] + lyudi
    res, tela, por = {}, {}, {}

    def kak(u, rol):
        vn.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': u, 'role': rol, 'is_active': 1}
        return TestClient(vn, follow_redirects=False)

    def get(u, rol, url, klyuch=None):
        r = kak(u, rol).get(bp + url)
        k = klyuch or '%s GET %s' % (u, url)
        res[k] = [r.status_code, sha(norm(r.text)), len(r.text)]
        tela[k] = r.text
        return r

    for u, rol in lyudi:
        for url in URLS:
            r = get(u, rol, url)
            m = re.search(r'class="total-count">(\d+) компаний', r.text)
            por['%s %s' % (u, url)] = {'kod': r.status_code, 'total': int(m.group(1)) if m else None,
                                       'inns': inns_na_stranice(r.text), 'spisok': 'class="ochered-wrap"' in r.text,
                                       'kartochka': 'class="company-hero' in r.text}
        inns = por['%s /centro' % u]['inns']
        for j, inn in enumerate(inns[:2] + por['%s /centro?page=2' % u]['inns'][:1]):
            get(u, rol, '/centro?inn=' + inn, '%s GET карточка %d' % (u, j))
        iv = por['%s /centro?call_status=v_rabote' % u]['inns']
        if iv:
            get(u, rol, '/centro?inn=%s&call_status=v_rabote' % iv[0], '%s GET карточка вкладки' % u)
        get(u, rol, '/centro/stats')
        if rol == 'admin':
            get(u, rol, '/centro/admin')
            pr = next((x for x, r in lyudi if r == 'sales'), '')
            get(u, rol, '/centro?assigned_user=' + pr, '%s GET /centro?assigned_user=продавец' % u)
    # действия продавцов – в том же порядке во всех вариантах, на своей копии базы
    for u, rol in lyudi:
        inns = por['%s /centro' % u]['inns']
        if rol != 'sales' or len(inns) < 3:
            continue
        k = kak(u, rol)
        kart = k.get(bp + '/centro?inn=' + inns[0]).text
        m = re.search(r'class="work-form">\s*<input[^>]*>\s*<input type="hidden" name="return_query" value="([^"]*)"', kart)
        r = k.post(bp + '/centro/save', data={'inn': inns[0], 'call_result': 'v_rabote', 'comment': 'fixKO проверка',
                                             'next_contact_at': '', 'return_query': _html.unescape(m.group(1)) if m else ''})
        kuda = r.headers.get('location', '')
        res['%s POST save' % u] = [r.status_code, kuda.replace(bp, ''), k.get(kuda).status_code if kuda else None]
        for imya, url, dop in (('hide', '/centro?inn=' + inns[1], {'reason': 'fixKO проверка'}),
                               ('undo', '/centro?inn=%s&skrytye=1' % inns[1], {'undo': '1'})):
            kart = k.get(bp + url)
            m = re.search(r'name="kuda" value="([^"]*)"', kart.text)
            data = dict(inn=inns[1], kind='company', value=inns[1], **dop)
            if m:
                data['kuda'] = _html.unescape(m.group(1))
            r = k.post(bp + '/centro/hide', data=data, headers={'referer': 'http://testserver' + bp + url})
            kuda = r.headers.get('location', '').replace('http://testserver', '')
            res['%s POST %s' % (u, imya)] = [r.status_code, kuda.replace(bp, ''), k.get(kuda).status_code if kuda else None,
                                             kart.status_code]
        get(u, rol, '/centro', '%s GET главная после действий' % u)
    s = sqlite3.connect(db)
    dump = {}
    for tabl, kol in (('company_state', 'inn, username, status, call_result, next_contact_at'),
                      ('company_comment', 'inn, username, body'), ('activity_log', 'inn, username, action, payload_json'),
                      ('hidden_item', 'inn, kind, value, reason, username'), ('company_assignment', 'inn, username, assignment_score')):
        dump[tabl] = sha(json.dumps(sorted(map(list, s.execute('SELECT %s FROM %s' % (kol, tabl)).fetchall())), ensure_ascii=False))
    s.close()
    io.open(vyhod, 'w', encoding='utf-8').write(json.dumps({'res': res, 'por': por, 'dump': dump, 'lyudi': lyudi}, ensure_ascii=False))
    io.open(vyhod + '.tela', 'w', encoding='utf-8').write(json.dumps(tela, ensure_ascii=False))


def proverit_posle(konf, do, po, plokh):
    """«после» против «до»: список вместо карточки, те же компании и порядок; карточка, соседи, действия, шапка, ФИО."""
    bp = PUT[konf]
    tela = po['tela']
    for k, d in sorted(do['por'].items()):
        a = po['por'].get(k)
        if not a or a['kod'] != d['kod'] or a['total'] != d['total'] or a['inns'] != d['inns']:
            plokh.append('%s %s: до %s, после %s' % (konf, k, (d['kod'], d['total'], len(d['inns'])),
                                                      a and (a['kod'], a['total'], len(a['inns']))))
        elif a['kod'] == 200 and (not a['spisok'] or a['kartochka']):
            plokh.append('%s %s: не список (spisok %s, карточка %s)' % (konf, k, a['spisok'], a['kartochka']))
    for u, rol in po['lyudi']:
        inns, n = po['por']['%s /centro' % u]['inns'], po['por']['%s /centro' % u]['total']
        for j, ozh in ((0, 1), (1, 2), (2, 21)):
            t = tela.get('%s GET карточка %d' % (u, j))
            if t is None:
                continue
            spis = re.search(r'<a href="([^"]*)">← к списку</a>', t)
            rq = re.search(r'class="work-form">\s*<input[^>]*>\s*<input type="hidden" name="return_query" value="([^"]*)"', t)
            sled = re.search(r'href="[^"]*inn=(\d+)[^"]*"[^>]*>Пропустить →', t)
            pred = re.search(r'href="[^"]*inn=(\d+)[^"]*">← Предыдущая', t)
            # карточки 0 и 1 – первая и вторая компании очереди, карточка 2 – первая со 2-й страницы (21-я)
            ozh_sled = (po['por']['%s /centro?page=2' % u]['inns'] + [''])[1] if j == 2 else (inns[j + 1] if j + 1 < len(inns) else '')
            usl = [('Компания %d из %s' % (ozh, n)) in t, bool(spis), (spis and ('page=2' in spis.group(1))) if ozh == 21 else True,
                   (('inn=' + ozh_sled) in _html.unescape(rq.group(1)) if rq else False) if ozh_sled else True,
                   (sled and sled.group(1) == ozh_sled) if ozh_sled else not sled,
                   (pred is None) if ozh == 1 else bool(pred)]
            if not all(usl):
                plokh.append('%s карточка %s №%d: %s' % (konf, u, ozh, usl))
        tv = tela.get('%s GET карточка вкладки' % u)
        if tv is not None:
            rq = re.search(r'name="return_query" value="([^"]*)"', tv)
            if not rq or 'call_status=v_rabote' not in _html.unescape(rq.group(1)):
                plokh.append('%s %s: «дальше» во вкладке «Взял в работу» уходит из вкладки: %s' % (konf, u, rq and rq.group(1)))
        # шапка: одна, без «Список компаний» и «Парк машин»
        for k, t in tela.items():
            if not k.startswith(u + ' ') or po['res'][k][0] != 200:
                continue
            if 'href="%s/centro/spisok"' % bp in t or 'href="%s/centro/park"' % bp in t:
                plokh.append('%s %s: в шапке остались «Список компаний» / «Парк машин»' % (konf, k))
            if t.count('<header class="topbar">') != 1 or '>Вся очередь</a>' not in t:
                plokh.append('%s %s: шапка не одна или без вкладок' % (konf, k))
            if rol == 'admin' and ('href="%s/centro/admin"' % bp not in t or 'href="%s/centro/stats"' % bp not in t):
                plokh.append('%s %s: у админа нет «Распределение» / «Статистика»' % (konf, k))
        st = po['res'].get('%s GET /centro/stats' % u, [None])[0]
        if st != (200 if rol == 'admin' else 403):
            plokh.append('%s %s: статистика %s' % (konf, u, st))
        if rol == 'admin' and po['res'].get('%s GET /centro/admin' % u, [None])[0] != 200:
            plokh.append('%s %s: распределение %s' % (konf, u, po['res'].get('%s GET /centro/admin' % u)))
        if rol == 'sales' and len(inns) >= 3:
            sv, hd, un = (po['res'].get('%s POST %s' % (u, x)) for x in ('save', 'hide', 'undo'))
            if sv != [303, '/centro?inn=' + inns[1], 200]:
                plokh.append('%s %s: «сохранить и дальше» %s (ждём следующую %s)' % (konf, u, sv, inns[1]))
            if not hd or hd[:3] != [303, '/centro', 200]:
                plokh.append('%s %s: после скрытия %s (ждём 303 в список и 200)' % (konf, u, hd))
            if not un or un[:3] != [303, '/centro?skrytye=1', 200] or un[3] != 200:
                plokh.append('%s %s: после возврата %s' % (konf, u, un))
    if konf == 'kc':
        t = tela.get('admin GET /centro', '')
        for login, f in FIO.items():
            if f not in t:
                plokh.append('kc: ФИО %s нет в списке у админа' % f)
            if f not in tela.get('admin GET /centro/admin', '') or f not in tela.get('admin GET /centro/stats', ''):
                plokh.append('kc: ФИО %s нет в распределении/статистике' % f)
            tt = tela.get('%s GET /centro' % login)
            if tt is not None and ('%s · продавец' % f) not in tt:
                plokh.append('kc: в шапке %s нет «%s · продавец»' % (login, f))


def stadiya() -> bool:
    os.makedirs(os.path.join(STAGE, 'db'), exist_ok=True)
    ign = shutil.ignore_patterns('__pycache__', '*.pyc')
    do_k = os.path.join(STAGE, 'do')
    shutil.copytree(os.path.join(KOREN, 'app'), os.path.join(do_k, 'app'), ignore=ign)
    posle_k = os.path.join(STAGE, 'posle')
    shutil.copytree(os.path.join(do_k, 'app'), os.path.join(posle_k, 'app'))
    p('правки в stage:', pravki(posle_k))
    smes_k = os.path.join(STAGE, 'smes')        # старый Python + новые шаблоны = 8014 до перезапуска
    shutil.copytree(os.path.join(do_k, 'app'), os.path.join(smes_k, 'app'))
    shutil.copytree(os.path.join(posle_k, 'app', 'templates'), os.path.join(smes_k, 'app', 'templates'), dirs_exist_ok=True)
    varianty = {'do': do_k, 'posle': posle_k, 'smes': smes_k}
    procy = []
    for konf, (sdb, kdb) in BAZY.items():
        snimok = os.path.join(STAGE, 'db', '%s-sales-snimok.db' % konf)
        kat = os.path.join(STAGE, 'db', '%s-kat.db' % konf)
        kopiya_bazy(os.path.join(DATA, sdb), snimok)
        kopiya_bazy(os.path.join(DATA, kdb), kat)
        for imya, k in varianty.items():
            sd = os.path.join(STAGE, 'db', '%s-sales-%s.db' % (konf, imya))
            shutil.copy(snimok, sd)
            env = {x: v for x, v in os.environ.items() if not x.startswith(('CENTRO', 'PARK_', 'OBZVON', 'CENTRIFUGAL'))}
            env.update(PYTHONIOENCODING='utf-8', PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=k,
                       OBZVON_ROOT_PATH=PUT[konf], CENTRO_SALES_DB=sd, CENTRIFUGAL_DB=kat, CENTRO_DB=kat,
                       PARK_OCHERED_SALES_DB=sd, PARK_OCHERED_DB=kat,
                       PARK_PANEL_DB=os.path.join(STAGE, 'db', 'net-park.db'), CENTRO_SESSION_SECRET='x' * 40)
            vyh = os.path.join(STAGE, '%s-%s.json' % (konf, imya))
            # PYTHONHASHSEED: главная строит список регионов из set – без него порядок <option> у каждого процесса свой
            migr = '1' if (konf == 'kc' and imya == 'posle') else '0'
            procy.append((konf, imya, vyh, subprocess.Popen(
                [VENV, os.path.abspath(__file__), '--proverka', k, konf, migr, vyh], cwd=k, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)))
    rez = {}
    for konf, imya, vyh, pr in procy:
        out = pr.communicate(timeout=1300)[0].decode('utf-8', 'replace')
        if pr.returncode or not os.path.exists(vyh):
            p('ПРОВЕРКА %s/%s УПАЛА rc=%s:\n%s' % (konf, imya, pr.returncode, out[-2500:]))
            return False
        rez[(konf, imya)] = json.load(io.open(vyh, encoding='utf-8'))
        rez[(konf, imya)]['tela'] = json.load(io.open(vyh + '.tela', encoding='utf-8'))
    plokh = []
    for konf in BAZY:
        do, smes, posle = rez[(konf, 'do')], rez[(konf, 'smes')], rez[(konf, 'posle')]
        n_sravn = 0
        for k, v in sorted(do['res'].items()):
            if '/centro/stats' in k:     # 8014 статистику не отдаёт вовсе (его Python старше fixKS)
                continue
            n_sravn += 1
            if smes['res'].get(k) != v:
                plokh.append('%s смесь != до: %s: %s -> %s' % (konf, k, v, smes['res'].get(k)))
                if k in do['tela'] and k in smes['tela']:
                    import difflib
                    for l in list(difflib.unified_diff(norm(do['tela'][k]).splitlines(), norm(smes['tela'][k]).splitlines(),
                                                       lineterm='', n=0))[:8]:
                        p('      ' + l[:220])
        proverit_posle(konf, do, posle, plokh)
        for imya in ('smes', 'posle'):
            if rez[(konf, imya)]['dump'] != do['dump']:
                plokh.append('%s: база после действий %s отличается от «до»' % (konf, imya))
        sk = {k: v for k, v in do['res'].items() if ' POST ' in k}
        p('%s: запросов %d, «смесь»=«до» сравнено %d; действия «до»: %s' % (konf, len(do['res']), n_sravn, sk))
        p('%s: действия «после»: %s' % (konf, {k: v for k, v in posle['res'].items() if ' POST ' in k}))
        p('%s: очередь по людям (до = после): %s' % (konf, {k.split(' ', 1)[0]: posle['por'][k]['total']
                                                          for k in posle['por'] if k.endswith(' /centro')}))
    for x in plokh:
        p('ПЛОХО: ' + x)
    p('ПЛОХИХ ПРОВЕРОК: %d' % len(plokh))
    if not plokh:     # образцы страниц «после» – на дроп, посмотреть глазами
        t = rez[('kc', 'posle')]['tela']
        for imya, k in (('fixKO-spisok-admin.html', 'admin GET /centro'), ('fixKO-kartochka-user2.html', 'user2 GET карточка 1')):
            if k in t:
                io.open(os.path.join(DROP, imya), 'w', encoding='utf-8').write(t[k])
    return not plokh


class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


urllib.request.install_opener(urllib.request.build_opener(BezRedirekta))
ZHIVYE = [(8012, '/obzvon/centro/login'), (8012, '/obzvon/centro'), (8012, '/obzvon/centro/stats'),
          (8014, '/p25/centro/login'), (8014, '/p25/centro'), (8011, '/')]


def http(port, url):
    try:
        return urllib.request.urlopen('http://127.0.0.1:%d%s' % (port, url), timeout=30).status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa: BLE001
        return str(e)[:60]


def nssm_restart(svc):
    for exe in (r'C:\Windows\System32\nssm.exe', r'C:\nssm.exe'):
        if os.path.exists(exe):
            r = subprocess.run([exe, 'restart', svc], capture_output=True, timeout=120)
            return (r.stdout + r.stderr).decode('utf-16-le' if b'\x00' in r.stdout + r.stderr else 'cp866', 'replace').replace('\x00', '').strip()
    return 'nssm не найден'


def zhdat_vhod():
    for _ in range(30):
        time.sleep(2)
        if http(8012, '/obzvon/centro/login') == 200:
            return 200
    return http(8012, '/obzvon/centro/login')


def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)                      # брошенный (старше 25 мин)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('%s %s' % (kto, time.strftime('%H:%M:%S'))).encode('utf-8'))
    os.close(fd)


def vernut(papka):
    for rel in PRAVIM:
        shutil.copy2(os.path.join(papka, rel), os.path.join(KOREN, rel))
    for rel in NOVYE:
        try:
            os.remove(os.path.join(KOREN, rel))
        except OSError:
            pass


def main():
    rezhim = sys.argv[1] if len(sys.argv) > 1 else '--suho'
    if rezhim == '--proverka':
        return proverka(sys.argv[2], sys.argv[3], sys.argv[4] == '1', sys.argv[5])
    if rezhim == '--otkat':
        vzyat_zamok('fixKO откат')
        try:
            vernut(sys.argv[2])
            p('файлы возвращены из %s; перезапуск obzvon: %s %s' % (sys.argv[2], nssm_restart('obzvon'), zhdat_vhod()))
        finally:
            os.remove(ZAMOK)
        return
    os.makedirs(DROP, exist_ok=True)
    p('fixKO %s, %s' % (rezhim, T))
    zamok = rezhim == '--primenit'
    if zamok:
        vzyat_zamok('fixKO (главная КЦ списком, шапка, ФИО)')
    zapisano = False
    try:
        do_zh = {'%d %s' % k: http(*k) for k in ZHIVYE}
        p('живые до:', do_zh)
        ok = stadiya()
        if rezhim != '--primenit':
            p('сухой прогон: живые файлы и база не трогались')
            return
        if not ok:
            p('ПРОВЕРКА НЕ ПРОШЛА – живые файлы не трогались')
            raise SystemExit(1)
        # запись: копии прежних файлов и базы, правки по якорям (файлы перечитаны под замком), сверка со stage
        for rel in PRAVIM:
            os.makedirs(os.path.dirname(os.path.join(BEKAP, rel)), exist_ok=True)
            shutil.copy2(os.path.join(KOREN, rel), os.path.join(BEKAP, rel))
            if sha(chitat(os.path.join(KOREN, rel))) != sha(chitat(os.path.join(STAGE, 'do', rel))):
                p('ЖИВОЙ ФАЙЛ ИЗМЕНИЛСЯ ПОСЛЕ КОПИИ В STAGE: %s – запись отменена' % rel)
                raise SystemExit(1)
        kopiya_bazy(os.path.join(DATA, 'centro_sales.db'), os.path.join(BEKAP, 'centro_sales.db'))
        zapisano = True
        p('записано:', pravki(KOREN), ' копии прежних:', BEKAP)
        sovp = all(sha(chitat(os.path.join(KOREN, r))) == sha(chitat(os.path.join(STAGE, 'posle', r))) for r in PRAVIM + tuple(NOVYE))
        p('живые файлы = проверенный stage:', sovp)
        if not sovp:
            raise RuntimeError('живые файлы не совпали с проверенным stage')
        p('база, ФИО:', migraciya_fio(os.path.join(DATA, 'centro_sales.db')))
        p('перезапуск obzvon (8012):', nssm_restart('obzvon'), zhdat_vhod())
        posle = {'%d %s' % k: http(*k) for k in ZHIVYE}
        p('живые после:', posle)
        if posle != do_zh:
            raise RuntimeError('коды ответов изменились: %s -> %s' % (do_zh, posle))
        p('ГОТОВО')
    except Exception as e:  # noqa: BLE001 – после записи любая ошибка = откат файлов
        if not zapisano:
            raise
        p('ОШИБКА ПОСЛЕ ЗАПИСИ: %s – возвращаю файлы из %s' % (e, BEKAP))
        vernut(BEKAP)
        p('перезапуск obzvon после отката:', nssm_restart('obzvon'), zhdat_vhod())
        raise SystemExit(1)
    finally:
        if zamok:
            try:
                os.remove(ZAMOK)
            except OSError:
                pass
        io.open(os.path.join(DROP, 'fixKO-%s-%s.txt' % (rezhim.strip('-'), T)), 'w', encoding='utf-8').write('\n'.join(log))
        if os.path.isdir(STAGE):
            shutil.rmtree(os.path.join(STAGE, 'db'), ignore_errors=True)     # копии баз не копим
            if 'ГОТОВО' in log[-1:] or rezhim != '--primenit':
                shutil.rmtree(STAGE, ignore_errors=True)


if __name__ == '__main__':
    main()
