# 14. Ветки, состояние работ и что не влито

Срез сделан **2026-07-27, 15:52–16:10 UTC**, на рабочей копии `/home/user/avto`.
Репозиторий живой: пока писался этот документ, параллельная сессия сделала коммит
и запушила его (HEAD переехал с `f6a7480` на `7e2b968`). Все числа ниже —
на момент `7e2b968`; проверяйте заново командой из раздела «Точки входа».

> **[ПРОВЕРКА СКЕПТИКА, 2026-07-27 ~17:10 UTC]** Документ вычитан по коду.
> Исправленные места помечены «[ИСПРАВЛЕНО СКЕПТИКОМ]». За время между срезом
> и вычиткой HEAD переехал ещё дважды — на `c21cd61` (16:48) и `ba03097` (16:59);
> `c21cd61` отменил один из главных выводов документа (см. раздел про обзвон).
> Проверка велась на `ba03097`.

---

## Что это и зачем

В репозитории нет ни главной ветки `main`/`master`, ни тегов. Про pull-request'ы
сказать нечего: `origin` — локальный прокси песочницы, `gh` в среде не установлен,
API GitHub из песочницы не опрашивался. **НЕ ПРОВЕРЕНО:** есть ли PR'ы на GitHub.
Есть шесть веток вида `claude/<имя>`, каждая — след отдельной длинной сессии.

**[ИСПРАВЛЕНО СКЕПТИКОМ]** Исходный текст утверждал «работа НЕ сливалась через
merge». Это неверно. Merge-коммит в истории ЕСТЬ — ровно один:

```
b1bfc6c 2026-07-22 16:25 Merge remote-tracking branch
        'origin/claude/persona-prompt-seo-sender-vi4tcq' into claude/youthful-sagan-ny4fm6
        parents: 072929a ff78ddf
```

`git merge-base --is-ancestor b1bfc6c HEAD` → истина, то есть этот merge лежит
в истории текущей ветки. `git merge-base HEAD origin/claude/persona-prompt-seo-sender-vi4tcq`
даёт `ff78ddf` (22.07 07:19) — это коммит ИЗ инженерной ветки, и всё, что было
в ней до него, попало в HEAD обычным git-merge, а не через сервер.
Проверка: `git log --all --merges --oneline` (один результат).

Итого код доезжал до результата ТРЕМЯ путями:

1. **Одним git-merge** (22.07, `b1bfc6c`) — первая половина инженерной ветки.
2. **Через боевой сервер.** Сессия готовила патч, клала его копией в
   `seo-texts/sender-patches/`, оттуда собирался zip и разворачивался на сервере
   владельца. Позже репозиторий синхронизировали ОБРАТНО с сервера
   (коммит `48ef189`, 2026-07-26) — так изменения из чужой ветки оказались
   в текущей, минуя git-merge.
3. **Копированием файлов.** Часть содержимого просто скопирована из ветки в ветку.

Поэтому вопрос «что не влито» здесь всё равно решается не одним `git log`,
а сравнением СОДЕРЖИМОГО. Этот раздел даёт готовые ответы и команды для перепроверки.

Три каталога, которые вызывают больше всего путаницы, и чем они на самом деле
являются:

| Каталог | Что это | Живой? |
|---|---|---|
| `seo-texts/sender/` | боевой код рассыльщика; синхронизирован с сервером 26.07 и с тех пор дорабатывается прямо здесь | ДА, источник правды |
| `seo-texts/sender-patches/` | 92 файла в 13 тематических подкаталогах: слепки промежуточных патчей 24–26.07, которые ехали на сервер архивом | почти весь — архив; ОДИН подкаталог используется скриптом сборки (см. ниже) |
| `seo-texts/sender-divergent/` | 4 файла: версии из репозитория, которые РАЗОШЛИСЬ с боем и были бы затёрты синхронизацией; сохранены намеренно | архив; внутри есть код, которого в пакете `sender/` больше нет (см. раздел 3 — «потеряно» ли оно на самом деле, по репозиторию не определить) |

---

## Точки входа и как запустить

Всё, что ниже, — только чтение, ничего не меняет и не трогает сервер.

### Состояние веток на origin (обязательно ls-remote, локальные refs врут)

```bash
cd /home/user/avto
git ls-remote --heads origin
```

Локальные `refs/remotes/*` показывают состояние на момент последнего `fetch`.
Ветки создают и двигают параллельные сессии, поэтому ls-remote обязателен.

### Насколько ветка впереди/позади текущей

```bash
cd /home/user/avto
for b in hopeful-galileo-n8gg7o nifty-shannon-7nw58j \
         persona-prompt-seo-sender-vi4tcq rusprom-b2b-email-templates-8rrstf \
         youthful-sagan-ny4fm6; do
  echo -n "$b: "; git rev-list --left-right --count HEAD...origin/claude/$b
done
# вывод: «<коммитов только в HEAD>	<коммитов только в ветке>»
```

### Что в ветке есть, а в текущем дереве нет (главный вопрос «что не влито»)

```bash
# A = файл есть только в ветке; M = есть в обеих, содержимое разное;
# D = есть только в HEAD
git diff --name-status HEAD origin/claude/<ветка> | awk '$1=="A"'
```

Важно: `git diff HEAD...origin/<ветка>` (три точки) покажет ГОРАЗДО больше —
это diff от точки расхождения, туда попадает всё, что потом приехало в HEAD
другим путём. Для вопроса «чего не хватает прямо сейчас» нужны ДВЕ точки.

### Кто новее по каждому спорному файлу

```bash
f=seo-texts/sender/confirm.py
git log -1 --format='HEAD:   %ci %s' HEAD -- "$f"
git log -1 --format='ВЕТКА:  %ci %s' origin/claude/persona-prompt-seo-sender-vi4tcq -- "$f"
```

### Сверка патча с боевым файлом

```bash
cd /home/user/avto/seo-texts
diff sender-patches/review-fixes-wave1/confirm.py sender/confirm.py | grep -c '^<'   # только в патче
diff sender-patches/review-fixes-wave1/confirm.py sender/confirm.py | grep -c '^>'   # только в бою
```

### Реальная проверка перед выкаткой панели (НЕ запускать в этой сессии)

```bash
python seo-texts/server/preflight_panel.py           # 0 = безопасно, 1 = затрёт живое
bash   seo-texts/server/build_panel_update.sh panel  # собирает zip и кладёт на дроп
```
`preflight_panel.py` ходит на сервер через `run_on_server`, `build_panel_update.sh`
делает `drop_client.sh up` — оба запрещены при боевом прогоне.

---

## Как устроено внутри

### 1. Ветки origin (6 штук, на 2026-07-27 15:52 UTC)

| Ветка | tip | Последний коммит | Впереди HEAD | Позади HEAD |
|---|---|---|---|---|
| `claude/seo-texts-enrichment-prompt-449lyw` | `7e2b968` | 27.07 15:52 | — (это HEAD) | — |
| `claude/youthful-sagan-ny4fm6` | `aa33864` | 27.07 10:52 | **0** | 14 |
| `claude/nifty-shannon-7nw58j` | `9e13107` | 16.07 06:48 | **0** | 571 |
| `claude/hopeful-galileo-n8gg7o` | `601b5b1` | 26.07 08:46 | 2 | 571 |
| `claude/rusprom-b2b-email-templates-8rrstf` | `78e3958` | 26.07 12:55 | 22 | 571 |
| `claude/persona-prompt-seo-sender-vi4tcq` | `4f2301e` | 27.07 03:33 | 28 | 427 |

**[ИСПРАВЛЕНО СКЕПТИКОМ]** Числа проверены — на `7e2b968` они верны все до одного
(`git rev-list --left-right --count 7e2b968...origin/claude/<b>`). Но HEAD с тех пор
уехал на `ba03097`, и колонка «Позади HEAD» стала другой: youthful-sagan 25,
nifty-shannon / hopeful-galileo / rusprom-b2b 582, persona-prompt 438.
Колонка «Впереди HEAD» (0/0/2/22/28) не изменилась — именно она отвечает на вопрос
«что не влито». Tip'ы всех шести веток на 17:00 UTC те же, что в таблице.

Локально существуют только две ветки: `claude/seo-texts-enrichment-prompt-449lyw`
(текущая, worktree `/home/user/avto`) и `claude/nifty-shannon-7nw58j`.
Стэшей нет, тегов нет, непушенных коммитов нет.

`origin` прописан как `http://local_proxy@127.0.0.1:41729/git/kirillrand4-alt/avto`
— это локальный прокси песочницы, а не прямой адрес GitHub.

---

#### 1.1 `claude/nifty-shannon-7nw58j` — ПОЛНОСТЬЮ ВЛИТА

Её tip `9e13107` — предок HEAD. Ничего уникального в ней нет.
Последний коммит: «CLAUDE.md: фактический контекст про провайдерский шлюз».
Это исходная ветка корневого проекта GSC-автоматизации; на неё до сих пор
ссылается `RUNBOOK.md:11` как на «ветку разработки» — ссылка устарела.

#### 1.2 `claude/youthful-sagan-ny4fm6` — ПОЛНОСТЬЮ ВЛИТА

Tip `aa33864` («Промпт для новой сессии: дообогащение базы продажников штатным
конвейером») — прямой предок HEAD. HEAD ушёл вперёд на 14 коммитов.
Ветка была рабочей до 27.07 10:52, дальше работа продолжилась в текущей ветке.

#### 1.3 `claude/hopeful-galileo-n8gg7o` — НЕ ВЛИТА, 2 коммита, поисковая аналитика

Расходится с `9e13107` (16.07). Два коммита:
* `c897c4f` gitignore: `__pycache__`
* `601b5b1` «Поиск prokompressor v3: контрольный прогон тех же 1000 фраз после починки»

Файлы, которых НЕТ в текущем дереве (все — `seo-texts/`):

```
build_stats_problems.py          compare_v2_v3.py       reeval_missing.py
review_v3.py                     serp_diff.py
paket-poisk-v3.zip
paket-poisk-v3/OTCHET-poisk-v3.md
paket-poisk-v3/diff-v2-v3.json
paket-poisk-v3/search-problems-core.csv
paket-poisk-v3/search-problems-serp-paste.csv
```

Пять `.py` — скрипты сравнения выдачи v2/v3 и переоценки пропущенных фраз;
`paket-poisk-v3/` — отчёт третьего прогона по 1000 фразам. В текущем дереве есть
`seo-texts/paket-poisk/` и `paket-poisk-v2/`, но **v3 отсутствует** — то есть
самый свежий поисковый прогон лежит только в этой ветке.

Остальные 5 файлов (`.gitignore`, `CLAUDE.md`, `seo-texts/.gitignore`,
`gen_provider.py`, `server/drop_server.py`) в HEAD новее — забирать из ветки
их не надо.

Забрать поисковый пакет, ничего не сломав
(**[ИСПРАВЛЕНО СКЕПТИКОМ]**: в исходной команде не хватало `paket-poisk-v3.zip` —
он идёт отдельным файлом, а не внутри каталога):
```bash
git checkout origin/claude/hopeful-galileo-n8gg7o -- \
  seo-texts/paket-poisk-v3 seo-texts/paket-poisk-v3.zip \
  seo-texts/build_stats_problems.py \
  seo-texts/compare_v2_v3.py seo-texts/reeval_missing.py \
  seo-texts/review_v3.py seo-texts/serp_diff.py
```

#### 1.4 `claude/rusprom-b2b-email-templates-8rrstf` — НЕ ВЛИТА, 22 коммита, каталог `email-templates/`

Ветка про тексты холодных писем: шаблоны КЦ v3, заходы для новостных писем,
канон подписи, правило «не-реклама», разбор пилота 20–21.07, конвейер регенерации.

Каталог `email-templates/` лежит **в корне репозитория**, а не в `seo-texts/`,
и в текущем дереве его нет вообще (`ls email-templates` → No such file).
14 файлов:

```
email-templates/FIRST-TOUCH-NOTES.md          выжимка практик первого касания
email-templates/KC-SHABLONY-V3.md             шаблоны КЦ v3 (юр-рамка 38-ФЗ)
email-templates/NEWS-ZAHODY.md                10 заходов для новостных писем
email-templates/PANEL-INTEGRATION-SPEC.md     инженерная спека вшивания в ядро панели
email-templates/PILOT-2026-07-20-RAZBOR.md    разбор пилота
email-templates/PIPELINE-PROCESS.md           процесс генерации партии 49 писем
email-templates/PROMPT-DLYA-VETKI-DVIZHKA.md  промпт-задание ветке движка
email-templates/kc-regen-49.json              49 регенерированных писем
email-templates/kc-templates-engine.json      шаблоны в машинном виде
email-templates/pilot-deep-review.json        глубокое ревью 61 письма
email-templates/samples-10-human.json         10 калибровочных образцов
email-templates/pipeline/regen_kc.py          регенерация
email-templates/pipeline/send_stream.py       отправка потоком
email-templates/pipeline/stream_regen.py      стриминговая регенерация
```

Отношение к боевому коду: `PANEL-INTEGRATION-SPEC.md` и
`PROMPT-DLYA-VETKI-DVIZHKA.md` — это ЗАДАНИЕ на вшивание генератора в ядро
панели. Генератор в ядре с тех пор появился (`seo-texts/sender/ai_letter.py`,
94 КБ). **ПРЕДПОЛОЖЕНИЕ:** спека выполнена, но пофразовой сверки спеки с
`ai_letter.py` я не делал — это отдельная задача.

Три `pipeline/*.py` — самостоятельные скрипты вне пакета `sender`; в текущем
дереве вызывающих у них нет (их там нет физически). Внутри боевого дерева тем
же занимается `sender/ai_letter.py` + `sender/ai_quota.py`.

#### 1.5 `claude/persona-prompt-seo-sender-vi4tcq` — «инженерная ветка» рассыльщика, 28 коммитов

Самая содержательная и самая опасная для интерпретации. 28 коммитов включают:
почтовый браузер по 14 ящикам, подпись менеджера, смоук 14 ящиков, редиректор
доменов-двойников, DMARC на 13 доменов, гейт направлений КЦ/Meyer, ручную живую
отправку, `HANDOFF-2026-07-24.md`.

**Почти всё это УЖЕ В HEAD.** **[ИСПРАВЛЕНО СКЕПТИКОМ]** приехало ДВУМЯ путями,
а не одним: (а) обычным git-merge `b1bfc6c` от 22.07 — вся ветка по коммит
`ff78ddf` включительно (это и есть merge-base с HEAD); (б) остальное —
синхронизацией с боевого сервера (`48ef189`).
Проверено по датам: для КАЖДОГО из 56 файлов, которые различаются, последний
коммит в HEAD новее последнего коммита в ветке (HEAD — 26–27.07, ветка — 20–24.07).
Ни одного файла, где ветка новее, нет — перепроверено скептиком поимённо.

Дата коммита сама по себе не доказывает, что содержимое ветки поглощено, поэтому
скептик продиффил два самых спорных файла ПОСТРОЧНО:

* `sender/confirm.py`: строк, которые есть в ветке и нет в HEAD, — 33. Все до одной
  оказались старыми редакциями: `def approve(self, review_id, *, operator="")`
  против `confirm.py:356` (`operator`, `force`, `actor_user_id`),
  `_fallback_mailbox()` без параметров против `confirm.py:583`
  (`*, inn=None, prefer_mailbox=None`). Функции `_division_blocked`,
  `_division_flags`, `_send_live` на месте (`confirm.py:145`, `:102`, `:450`).
* `sender/sender.py`: 50 «веточных» строк, та же картина — `manual=`,
  `division_block`, `_daily_limit`, `can_send_now` все присутствуют в HEAD.

Потерянного содержимого в этих двух файлах нет.

**Не влито ровно 9 файлов** (`git diff --name-status HEAD origin/... | awk '$1=="A"'`):

| Файл | Что это | Стоит ли забирать |
|---|---|---|
| `seo-texts/sender/config/mailboxes.kc.yaml` | раскладка 14 боевых ящиков: division kc, `password_env` BOX1..BOX14 | **да, важно** — см. «Грабли» |
| `seo-texts/sender/deploy/redirects-nginx.conf` | готовый nginx-конфиг редиректов доменов-двойников | да, если редиректор ещё нужен |
| `seo-texts/sender/deploy/setup-redirects.sh` | установщик редиректов одной командой | да, вместе с conf |
| `seo-texts/site-pages/dozhimnye-stantsii-article.html` | вёрстка статьи «Дожимные станции» для сайта | да, это готовый продукт |
| `seo-texts/site-pages/photos-dozhimnye/*.webp` (5 шт.) | реальные фото из ТЗ к статье | да, вместе со статьёй |

Каталога `seo-texts/site-pages/` в текущем дереве нет; из всех веток он есть
только в этой (`git ls-tree -r --name-only <branch> -- seo-texts/site-pages`).

Файл `mailboxes.kc.yaml` есть ТОЛЬКО в этой ветке (проверено перебором всех
`refs/remotes`), при этом на него ссылаются документы, лежащие в HEAD:
`sender/BOXES-SMOKE.md:4`, `sender/MAILBOXES-SETUP.md:100`,
`sender/HANDOFF-2026-07-24.md:25`, `sender/BASEMERGE-DRYRUN.md:96`.
В `.gitignore` он не попадает (`git check-ignore` молчит) — то есть это не
«секрет, специально не закоммиченный», а просто не доехавший файл.
Пароли в нём не лежат, только имена env-переменных.

---

### 2. `seo-texts/sender-patches/` — 92 файла, 13 тематических подкаталогов

**[ИСПРАВЛЕНО СКЕПТИКОМ]** было «17 подкаталогов». Фактически: 13 подкаталогов
первого уровня (`ls -d sender-patches/*/`), а всего каталогов внутри — 20
(у `panel-window/` своя вложенная структура `web/src/{components,api,screens}`,
`api/`, `tests/`).

#### Как это работало

Ветка `persona-prompt-seo-sender-vi4tcq` была «инженерной»: там жил рассыльщик.
Другие сессии не мержили в неё, а делали так: брали файл из инженерной ветки,
правили, клали ЦЕЛИКОМ (не diff, несмотря на имя каталога) в
`sender-patches/<тема>/`, собирали архив и разворачивали на сервере.
`sender-patches/CONFIRM-QUEUE-FIX.md:12` описывает это прямым текстом:
«файлы — копии из ветки инженера + правки, для мерджа».

Дальше 2026-07-26 коммит `48ef189` («Обновление обеих панелей через дроп»)
развернул ситуацию: сверка хэшей показала, что **репозиторий отстал от сервера**
— 11 модулей существовали только на сервере, а `confirm/sender/store/personalize/
orchestrator/infopanel/imap_watcher` в репо были на 3–20 КБ меньше живых.
Источником правды объявили сервер, забрали боевой код архивом и синхронизировали
`seo-texts/sender/`: 21 файл обновлён, 32 добавлено. Разошедшиеся старые версии
сложили в `sender-divergent/`.

**Вывод: содержимое sender-patches доехало до `seo-texts/sender/` через сервер.**

#### Проверка по каждому подкаталогу

Метод: сравнить каждый файл патча с одноимённым в `sender/`, посчитать строки
«только в патче» и «только в бою». Если «только в патче» — это старые редакции
строк, которые в бою переписаны (изменённые сигнатуры, переформулированные
комментарии), значит патч — предок боевого файла, то есть влит.

| Подкаталог | Тема | Файлов | Статус |
|---|---|---|---|
| (корень) `cli.py`, `dtos.py`, `orchestrator.py`, `store.py`, `test_*.py` | очередь подтверждений: исходящие кампаний → `confirm.submit` | 6 (+`CONFIRM-QUEUE-FIX.md` = 7 файлов) | **влито** |
| `panel-ux/` | UX/безопасность отправки A1–A4, B1 + DKIM mailru | 6 | **влито** |
| `ai-letter/` | AI-генерация писем первого касания, гейт, линзы | 7 | **влито**, кроме 2 файлов ↓ |
| `panel-window/` | настраиваемое окно авто-отправки, сессия 30 дней | 10 | **влито**, кроме теста ↓ |
| `out-of-base-toggle/` | тумблер «слать по email вне базы» (дефолт ВЫКЛ) | 5 | **влито** |
| `division-needs/` | гейт направлений по ПОТРЕБНОСТЯМ компании | 3 | **влито** |
| `meyer-gen/` | генерация писем направления Meyer | 6 | **влито** |
| `quota-ui/` | дневная квота генерации, бэкенд + фронт | 7 | **влито** |
| `panel-redesign/` | дизайн-система панели (задача 47) | 16 | **влито в бой, но исходники CSS есть только здесь** ↓ |
| `panel-pager/` | пейджер во всех списках панели (задача 52) | 7 | **влито** |
| `review-fixes-wave1/` | 5 критичных дефектов отправки/входящих | 6 | **влито** |
| `review-fixes-wave2/` | ответ клиенту: правильный ящик + ветка диалога | 5 | **влито** |
| `review-fixes-wave3/` | генерация: чужой слот, двойная подпись, дыры гейта | 3 | **влито** |
| `obzvon-pagination/` | пагинация панели обзвона (ДРУГОЕ приложение) | 4 | **живой вход скрипта сборки**; устарел был, 27.07 16:48 обновлён ↓ |

**[ИСПРАВЛЕНО СКЕПТИКОМ]** количества файлов: `panel-redesign/` — 16, а не 17;
корень — 7 файлов (6 `.py` + `CONFIRM-QUEUE-FIX.md`), а не 6. Сумма по столбцу
всё равно даёт 92, потому что эти две ошибки взаимно гасились.
Остальные 12 строк столбца «Файлов» проверены поштучно и верны.

Доказательства «влито» на примерах (можно перепроверить построчно):

* `store.mark_pending_review` из корневого патча — есть в бою:
  `seo-texts/sender/store.py:1258`
  (**[ИСПРАВЛЕНО СКЕПТИКОМ]**: было «:1160» — там другой код; метод объявлен
  на 1258-й строке. `store.py` правился после среза коммитом `e2004dc`,
  так что номер строки снова может уехать — ищите грепом).
* `Orchestrator.__init__(..., confirm=None)` — `seo-texts/sender/orchestrator.py:110`,
  сама ветка постановки в очередь — `orchestrator.py:471`.
* `TickResult.queued` — `seo-texts/sender/dtos.py:217`.
* `sender-patches/cli.py`, `sender-patches/dtos.py`,
  `panel-window/auth.py`, `panel-ux/dns.py`, `ai-letter/personalize.py`,
  `panel-redesign/{Layout.tsx,main.tsx,theme.ts,ui.tsx}`,
  `panel-pager/{Leads.tsx,Recipients.tsx,admin.tsx}`,
  `meyer-gen/{test_ai_letter_meyer.py,test_gate_fixes.py}` — **побайтно равны**
  соответствующим файлам в `sender/`.
* `division-needs/company_card.py` — строгое подмножество
  `sender/company_card.py` (в бою +40 строк: `equip_for_okved` с кэшем).
* «Только в патче» у `confirm.py`/`sender.py` — это старые сигнатуры:
  например `def approve(self, review_id, *, operator="")` в патче против
  `sender/confirm.py:356`, где у метода уже больше параметров.

#### Что из sender-patches НЕ имеет копии в `seo-texts/sender/`

Три файла. Каждый проверен: одноимённого файла в `sender/` нет, и в других
ветках origin его тоже нет.

**1. `sender-patches/ai-letter/ai_gen_quota.py`** (8,6 КБ) — операционный скрипт
для сервера: генерирует письма кампании порциями по дневной квоте.
Пути захардкожены (`sys.path.insert(0, r'C:\sender')`, `CFG = r'C:\sender\sender.yaml'`,
лог `C:\sender\ai_gen_quota.log`), запуск `python ai_gen_quota.py <кампания> <квота>`.
Модуль `sender/ai_quota.py:8` ссылается на него как на существующую вещь:
«ФАКТ берём из ai_letter_log — того же лога, что пишет скрипт ai_gen_quota.py».
То есть скрипт живёт на сервере, а в репозитории его единственная копия — здесь.
**Не мёртвый, но и не в пакете:** `build_panel_update.sh` кладёт в zip только
`.py` из `seo-texts/sender/`, поэтому этот файл на сервер архивом НЕ едет.

**2. `sender-patches/ai-letter/test_ai_letter.py`** (14 тестов) и
**3. `sender-patches/panel-window/tests/test_ai_letter.py`** (16 тестов, надмножество).

В `seo-texts/sender/tests/` файла `test_ai_letter.py` НЕТ — и его нет ни в одной
ветке origin, и во всей истории git. Скептик перепроверил тремя способами:
`git log --all --oneline -- 'seo-texts/sender/tests/test_ai_letter.py'` пуст;
`git ls-remote --heads origin` даёт те же шесть веток, невыгруженных нет;
перебор всех `refs/heads` + `refs/remotes` через `git cat-file -e` по этому пути
не находит ничего. Единственные два коммита, где вообще фигурирует имя
`test_ai_letter.py`, — `dea833e` и `77f8d1a`, и оба кладут файл в
`sender-patches/`, а не в `sender/tests/`. Вывод подтверждён.

При этом `sender/tests/test_ai_letter_meyer.py:4` пишет:
«Идут вместе с test_ai_letter.py (компрессорные тесты не трогаем: их прохождение
и есть доказательство, что КЦ-ветка не поехала)». Ни одного из 16 имён тестов
(`test_gate_clean_letter_passes`, `test_gate_numbers_must_be_allowed`,
`test_gate_city_declension`, `test_cycle_fix_round_repairs_letter`,
`test_auto_mode_routing`, `test_window_override_applies` и т.д.)
в `sender/tests/` нет — перепроверено поимённо по всем 16.

**[ИСПРАВЛЕНО СКЕПТИКОМ]** Исходный вывод «базовое покрытие КЦ-генерации в боевом
сьюте отсутствует» — завышен. `ai_letter` в боевом сьюте покрыт, тремя файлами:

| Файл | Тестов | Что из `ai_letter` трогает |
|---|---|---|
| `tests/test_ai_letter_meyer.py` | 26 | `gate` (в т.ч. `test_kc_gate_catches_meyer_lexicon`, `test_facts_block_kc_unchanged`, `test_generate_kc_letter_has_no_meyer_lexicon`), выбор направления, `load_facts` без файла |
| `tests/test_gen_57.py` | 14 | `gen_prompt`, `_recipient_block`, `equipment_pitch`, `company_size`, ротация углов, подпись кампании |
| `tests/test_gate_fixes.py` | 4 | `gate`, `allowed_numbers` (плейсхолдеры, ИНН, цифры в названии) |

`AiLetterGen.generate()` тоже вызывается — `test_ai_letter_meyer.py:280,296,310,332`
(четыре теста на смешанные батчи, отсутствие файлов фактов, разделение промптов
по направлениям).

Что реально потеряно вместе с файлом — конкретные ВЕТКИ этих же функций, аналогов
которым в сьюте нет (проверено грепом по `sender/tests/*.py`):

* **цикл починки и верификатор.** Потерянный `test_cycle_fix_round_repairs_letter`
  подсовывал генератору три ответа подряд (брак → fix-раунд → verify ok) и
  проверял, что письмо чинится. Ни `fix_round`, ни `hopeless`, ни `verif*`
  в живых тестах не встречаются — эта ветка `AiLetterGen.generate` не проверяется
  ничем, хотя в коде она есть (`ai_letter.py:1164`, `vf_prompt` на `:776`);
* **`mode: "auto"`** (маршрутизация auto → NEWS/GENERIC) и **`window_override`** —
  не встречаются нигде;
* **КЦ-варианты гейта**, которые в живом сьюте есть только в meyer-редакции
  (`test_meyer_gate_clean_letter_passes`, `test_meyer_stamp_limits_are_own`,
  `test_load_facts_missing_meyer_file_fallback`): сам код общий, так что ветки
  исполняются, но именно КЦ-набор данных через них не гоняется.

`test_store_settings_roundtrip` потерян не полностью: `panel_settings` покрыт
`tests/test_ai_quota.py` (21 тест).

#### `obzvon-pagination/` — единственный ЖИВОЙ вход; был устаревшим, 27.07 в 16:48 починен

Это не рассыльщик. Панель обзвона — отдельное приложение на сервере в
`C:\seostat\app` (FastAPI/Jinja), к `sender/` отношения не имеет.

Каталог читается скриптом сборки:
`seo-texts/server/build_panel_update.sh:18` (`PATCHES=...`),
функция `build_obzvon()` — строки 80–102, разворачивает плоские имена обратно
в каталоги (`api__routes_obzvon.py` → `api/routes_obzvon.py`).
Ещё два потребителя:
* `seo-texts/server/enrich_panel/panel_core.py:210` — копипаст `parse_money`
  оттуда как «единый канон разбора денег в проекте»;
* **[ДОБАВЛЕНО СКЕПТИКОМ]** `seo-texts/obzvon-centro/README.md:145,150-154` —
  боевой ранбук установки панели «Центробежные», который ПИШЕТ в этот каталог
  (`cp obzvon-centro/routes_centro.py sender-patches/obzvon-pagination/api__routes_centro.py`
  и ещё четыре файла) и тут же зовёт `build_panel_update.sh obzvon`.
  Появился коммитом `c21cd61` уже после среза.

**Грабля (была):** в 15:52 коммитом `7e2b968` в репозиторий положили СВЕЖИЕ
боевые исходники обзвона — `seo-texts/obzvon-src/` (11 файлов, снятые с сервера
скриптом `seo-texts/server/_ops_pull_obzvon.py`, который перечисляет реальные
пути: `api\routes_obzvon.py` → `obz__routes_obzvon.py` и т.д.).
Четыре файла пересекались, и боевые везде были больше патча:

| файл | patch (25.07) | live (27.07) |
|---|---|---|
| `api/routes_obzvon.py` | 19 924 б | 20 522 б |
| `db/models.py` | 32 571 б | 34 296 б |
| `services/callbase.py` | 39 941 б | 43 424 б |
| `templates/obzvon.html` | 9 677 б | 10 171 б |

**[ИСПРАВЛЕНО СКЕПТИКОМ] Грабля СНЯТА.** Коммит `c21cd61` (27.07 16:48,
«Панель обзвона: комплект собран; обезврежена мина в сборке пакета») заменил
все четыре файла `sender-patches/obzvon-pagination/` боевыми версиями с
`C:\seostat\app`. Сейчас (`ba03097`) они **побайтно равны** соответствующим
файлам `obzvon-src/` — проверено `cmp` по всем четырём парам. То есть вывод
«`bash build_panel_update.sh obzvon` откатит боевую панель обзвона» **больше
не верен**; переучивать `build_obzvon()` на `obzvon-src/` не нужно.
Правило при этом остаётся: `build_obzvon()` пакует ВЕСЬ каталог целиком, поэтому
перед каждой сборкой обзвона всё равно обязателен `preflight_panel.py` —
об этом же предупреждает `obzvon-centro/README.md`.

**[ИСПРАВЛЕНО СКЕПТИКОМ]** Список «есть в бою, нет в патче» был завышен.
Сверка старой версии патча (`git show 7e2b968:...services__callbase.py`)
с боевой:

* реально появились: `_backfill_region`, `_needs_derived`, `_backfill_derived`
  и ДВА индекса — `ix_cc_base_equipment`, `ix_cc_needs_backfill`;
* `_backfill` в патче БЫЛ (`def _backfill(db: Session) -> None` на строке 524),
  в бою у него сменилась сигнатура (`(db, fresh) -> int`);
* индексы `ix_cc_queue`, `ix_cc_queue_active`, `ix_cc_base_region`,
  `ix_cc_base_okved` в патче тоже БЫЛИ.

---

### 3. `seo-texts/sender-divergent/` — 4 файла, и в них есть потерянное

Создан коммитами `48ef189` и `08317d0` (26.07). Смысл, дословно из `48ef189`:
«Разошедшиеся старые версии не выброшены, а сложены в `sender-divergent/` —
вдруг там есть роут, который не переименовали, а потеряли».

| Файл | Размер | Что это |
|---|---|---|
| `api__app.py.old-2026-07-23` | 66 КБ | версия HTTP-API из репозитория до синхронизации |
| `cli.py.old-2026-07-23` | 34 КБ | версия CLI до синхронизации |
| `config.py.old-2026-07-23` | 29 КБ | версия загрузчика конфига до синхронизации |
| `web-old/Compose.tsx.old-2026-07-23` | 4 КБ | экран «Написать письмо», убран из сборки |

Я эту проверку довёл до конца — вот результат.

**Роуты.** В старом `api/app.py` 51 роут, в боевом `sender/api/app.py` 68.
Пять есть в старом и отсутствуют в боевом:

| Старый роут | Что было | Что в бою |
|---|---|---|
| `GET /campaigns/{cid}/capacity` | ёмкость по кампании | есть `GET /capacity` (без cid) |
| `POST /campaigns/{cid}/generate` | запуск генерации писем кампании | **ПРЕДПОЛОЖЕНИЕ:** заменён на `POST /ai/quota/run` |
| `GET /campaigns/{cid}/generate/{gid}` | статус прогона генерации | **ПРЕДПОЛОЖЕНИЕ:** заменён на `GET /ai/quota` |
| `POST /mailboxes` | **добавить ящик из панели** | аналога нет |
| `POST /send/manual` | ручная отправка одного письма | аналога нет |

`GET /mailboxes` не потерян, а переименован в `GET /mail/mailboxes`.

**Из пакета `sender/` ушла функциональность «добавить ящик из панели».**
Это не только роут: в `sender-divergent/config.py.old-2026-07-23` есть методы
`add_mailbox()` и `load_mailbox_overrides()` (подхватывают ящики, добавленные
из панели, из таблицы `mailbox_overrides`), а обработчик —
`sender-divergent/api__app.py.old-2026-07-23:679`.
В каталоге `seo-texts/sender/` строк `add_mailbox`, `load_mailbox_overrides`,
`mailbox_overrides`, `list_mailbox_overrides` нет ни одной (grep без фильтра
по расширению — подтверждено скептиком).

> **[ИСПРАВЛЕНО СКЕПТИКОМ] Но «живёт только в `sender-divergent/`» — неверно,
> и вывод «потеряно» делать РАНО.** Grep по всему репозиторию (а не только
> по `sender/`) даёт ещё два попадания, оба существенные:
>
> * `seo-texts/server/enrich_contacts.py:6357` — `cfg.load_mailbox_overrides(st)`.
>   Это операционный обработчик `op=smtp_selftest`, который гоняется раннером
>   НА БОЕВОМ СЕРВЕРЕ: строками 6331–6355 он делает `sys.path.insert(0, r'C:\sender')`,
>   `os.chdir(r'C:\sender')`, `from sender.config import Config`, а потом зовёт
>   `load_mailbox_overrides`. То есть код в `C:\sender\sender\config.py` этот метод,
>   по замыслу автора, имеет. Коммит `e3d9b11` от 23.07 (то есть ДО синхронизации
>   26.07) — вызов обёрнут в `try/except`, поэтому по нему нельзя сказать, жив ли
>   метод сегодня, но и «его нет» утверждать нельзя.
> * `seo-texts/email-assistant/TEMPLATE-SESSION-PROMPT.md:70` — «Конфиг ящиков
>   (imap_host/port/login/password_env) — в `sender.yaml` на сервере **и в таблице
>   `mailbox_overrides` БД панели**».
>
> Про таблицу `mailbox_overrides` в живой БД панели (`C:\sender\sender.db`)
> в этом документе не утверждается НИЧЕГО: живую БД никто не смотрел, а схему
> из репозитория читать для этого недостаточно. Проверять — на сервере, когда
> закончится боевое обогащение.

Ящики в пакете `sender/` берутся из yaml-конфига — что согласуется с тем, что
`mailboxes.kc.yaml` стал единственным источником раскладки. Осознанное это
решение или потеря — по коду не определить.

**Потеряна ручная отправка через экран «Написать письмо».**
`sender-divergent/web-old/Compose.tsx.old-2026-07-23:1-3` описывает экран как
«ручная отправка ОДНОГО письма владельцем, отправка РЕАЛЬНАЯ (SMTP, минуя
dry_run-холд массовой рассылки)». Коммит `08317d0` объясняет: «Compose.tsx в живом
бандле отсутствует и ни на что не сослан — экран старого поколения, ссылался на
исчезнувший sendManual». Ручная отправка сегодня делается иначе — через очередь
подтверждений (`POST /confirm/{rid}/decision`) и через ответ лиду
(`POST /leads/{lead_id}/reply`); документ `seo-texts/sender/MANUAL-SEND.md`.

**[ИСПРАВЛЕНО СКЕПТИКОМ]** В исходной редакции это было помечено как
«моя реконструкция, подтверждения владельца нет». Хеджирование избыточно:
`sender/MANUAL-SEND.md:3` формулирует это как правило владельца прямым текстом —
«**живьём уходит только то, что оператор одобрил руками**. Всё остальное —
оркестратор, автоответчик, регенераторы — умеет ТОЛЬКО ставить письма в очередь
подтверждений». Дальше документ расписывает, что ручная отправка обходит окно,
пейсинг и межрегиональный зазор, но НЕ обходит suppression, kill-switch и дневной
лимит. Так что замена `POST /send/manual` очередью подтверждений — задокументированная
политика, а не догадка. Открытым остаётся только вопрос, был ли осознанно удалён
сам роут.

**cli.py и config.py: набор команд и ключей совпадает.** Старый `cli.py` больше
боевого на 263 байта, старый `config.py` — на 1224 байта, но набор
`add_parser(...)` совпадает (21 команда в обоих), а вся разница `config.py` —
это как раз `add_mailbox` + `load_mailbox_overrides` (36 строк «только в старом»
против 14 «только в бою»). `store.init_schema()` при старте, который в diff
выглядит как «только в старом», на самом деле в бою есть —
`seo-texts/sender/cli.py:55` и `:497`, просто переехал; это НЕ потеря.

---

### 4. Реестр .md-документов репозитория

Всего отслеживаемых `.md` — **268** на `7e2b968` и **271** на `ba03097`
(**[ИСПРАВЛЕНО СКЕПТИКОМ]**: было «266», такого числа нет ни на одном коммите —
на `f6a7480` их 260, на `7e2b968` 268. Команда: `git ls-files '*.md' | wc -l`).
Даты ниже — дата последнего коммита,
затронувшего файл. Массовый импорт был 2026-07-16 (69 коммитов за день),
поэтому «16.07» у большинства старых файлов означает «с момента заведения репо
не менялся», а не «сделан 16-го».

Пометки актуальности:
**[ЖИВОЙ]** — описывает текущее состояние, можно доверять;
**[ОТЧЁТ]** — разовый отчёт о прогоне, устареть не может, но и состояния не описывает;
**[УСТАРЕЛ]** — есть проверенное расхождение с кодом/фактами, ниже указано какое;
**[СПРАВОЧНИК]** — данные/стайлгайды, не про состояние;
**[?]** — не проверял, оцените сами.

#### Корень репозитория (6)

| Файл | Дата | Метка | Комментарий |
|---|---|---|---|
| `CLAUDE.md` | 25.07 | ЖИВОЙ | инструкции проекта, читается каждой сессией |
| `README.md` | 23.06 | ЖИВОЙ | описание корневого проекта gsc-auto-index (не seo-texts) |
| `RUNBOOK.md` | 09.07 | УСТАРЕЛ частично | `RUNBOOK.md:11` называет веткой разработки `claude/nifty-shannon-7nw58j`, а она не двигалась с 16.07 |
| `SESSION-INDEX.md` | 17.07 | УСТАРЕЛ | карта областей на 17.07: сендер помечен «генерация модулей → баг-хант» (сейчас в бою), в открытых решениях «закупка ~10 доменов + ~30 ящиков» (куплено 14 доменов, заведено 14 ящиков) |
| `WORKING-PROTOCOL.md` | 17.07 | ЖИВОЙ | протокол качества сессий, к состоянию кода не привязан |
| `PERSONA-PROMPT.md` | 17.07 | ЖИВОЙ | якорь тона для новой сессии |

#### `seo-texts/docs/` (12 отслеживаемых на срезе + 2 в работе) — новая документация

**[ИСПРАВЛЕНО СКЕПТИКОМ]**: в заголовке было «10 отслеживаемых + 3 в работе»,
что противоречило тексту ниже. На `7e2b968` отслеживаются 12 файлов (01–12),
не закоммичены два — `13` и `14`. На `ba03097` отслеживаются все 14.

`01-generaciya-tekstov.md`, `02-baza-znaniy.md`, `03-revyuery.md`,
`04-kraulery-dannye.md`, `05-media-foto.md`, `06-stati-gostevye.md`,
`07-kp-i-klienty.md`, `08-obogashchenie-yadro.md`, `09-runner-i-panel.md`,
`10-novosti-lidy.md` — все 27.07, **[ЖИВОЙ]**.
`11-rassylshchik.md` и `12-kornevoy-proekt.md` закоммичены в `7e2b968`;
`13-infrastruktura.md` на момент среза не закоммичен (`git status` → `??`).
Этот файл — `14-vetki-i-sostoyanie.md`.

#### `seo-texts/sender/` (27 файлов в корне пакета + 2 в `deploy/`) — документация рассыльщика

| Файл | Дата | Метка | Комментарий |
|---|---|---|---|
| `SENDER-ARCHITECTURE.md` (187 КБ) | 20.07 | **УСТАРЕЛ** | `SENDER-ARCHITECTURE.md:5` заявляет «Покрытие: 29/29 модулей». Модулей в `sender/` сейчас 44. Не описаны 15, включая всю подсистему подтверждений и генерации: `ai_letter`, `ai_quota`, `company_card`, `confirm`, `confirm_cli`, `infopanel`, `mailbrowser`, `reply_pipeline`, `wiring`, `ramp`, `regions`, `snyatye`, `tokens`, `dnscore`, `assemble_arch` |
| `SENDER-STATE.md` (57 КБ) | 22.07 | УСТАРЕЛ | «состояние и как продолжить» на 22.07; после этого была синхронизация с сервером и 4 волны ревью |
| `SITE-DESIGN.md` (108 КБ) | 20.07 | [?] | дизайн панели; после редизайна (задача 47) не обновлялся |
| `CONTRACT.md` (41 КБ) | 18.07 | [?] | контракт интерфейсов 12 модулей; модулей сейчас 44 |
| `RUNBOOK-DEPLOY.md` (36 КБ) | 20.07 | УСТАРЕЛ как процесс | процесс выкатки описан заново в `seo-texts/server/PANEL-DEPLOY.md` (26.07) |
| `ROADMAP.md` | 20.07 | [?] | дорожная карта |
| `HOW-IT-WORKS.md` | 20.07 | [?] | схема потока |
| `REVIEW-FINDINGS.md` + `.json` | 26.07 | ОТЧЁТ | 295 CONFIRMED / 65 PARTIAL и т.д. |
| `REVIEW-TAILS-REPORT.md` | 22.07 | ОТЧЁТ | |
| `REVIEW-CHAIN.md` | 20.07 | [?] | |
| `PARITY.md` | 22.07 | [?] | паритет CLI ↔ панель; тест `tests/test_confirm_parity.py` в дереве есть |
| `OWNER-TODO.md` | 20.07 | УСТАРЕЛ | датирован 18.07 и ссылается на ветку `persona-prompt-seo-sender-vi4tcq` как на место, где «код готовится» |
| `HANDOFF-2026-07-24.md` | 26.07 | УСТАРЕЛ по адресу | «Ветка: `claude/persona-prompt-seo-sender-vi4tcq` (всё запушено)» — работа с тех пор идёт в текущей ветке |
| `DOMAINS-SETUP.md` | 26.07 | ЖИВОЙ | 14 доменов, DMARC |
| `MAILBOXES-SETUP.md` | 26.07 | ЖИВОЙ | ранбук ящиков; ссылается на не влитый `config/mailboxes.kc.yaml` |
| `BOXES-SMOKE.md` | 26.07 | ЖИВОЙ | смоук 14 ящиков; та же ссылка |
| `BASEMERGE-DRYRUN.md` | 26.07 | ОТЧЁТ | dry-run приёмка 20 писем |
| `MANUAL-SEND.md` | 26.07 | ЖИВОЙ | ручная отправка (текущий путь, не Compose) |
| `AUTORESPONDER-ROADMAP.md` | 20.07 | [?] | |
| `REPLY-TAXONOMY.md` | 20.07 | [?] | |
| `OPEN-TRACKING-SPEC.md` | 20.07 | [?] | пиксель открытий; чинился 27.07 (`57fd48b`) |
| `MAX-NOTIFY-SPEC.md` | 20.07 | [?] | |
| `PANEL-HOWTO.md` | 20.07 | [?] | |
| `FEATURES-PLAN.md` | 17.07 | ОТЧЁТ | разбор coldy |
| `ENGINEER-FIX-PROMPT.md`, `ENGINEER-FIX-ROUND2.md`, `ENGINEER-PROMPT-2026-07-20.md` | 20–21.07 | ОТЧЁТ | задания сессиям, выполнены |
| `deploy/README.md`, `deploy/REDIRECTS-RUNBOOK.md` | 26.07 | ЖИВОЙ | ранбук редиректора; сам `setup-redirects.sh` не влит (см. 1.5) |

#### `seo-texts/sender-patches/` (7 .md)

`CONFIRM-QUEUE-FIX.md`, `panel-ux/PANEL-UX-FIXES.md`,
`panel-window/PANEL-WINDOW-SESSION.md`, `ai-letter/AI-LETTER-INTEGRATION.md`,
`meyer-gen/README.md` (20 КБ), `quota-ui/README.md`, `panel-pager/README.md`.
Все **[ОТЧЁТ]** — описывают, что было в конкретном патче. Ценность: это
единственное место, где по-русски объяснено, ЗАЧЕМ сделано то или иное
изменение в боевом коде (в частности `meyer-gen/README.md` — про направление Meyer).

#### `seo-texts/server/` (6)

| Файл | Дата | Метка |
|---|---|---|
| `PANEL-DEPLOY.md` | 26.07 | **ЖИВОЙ** — канонический процесс выкатки обеих панелей, пути на сервере, инцидент с `python -m sender.cli` |
| `ENRICH-SALES-BASE-PROMPT.md` | 27.07 | ЖИВОЙ |
| `ENRICH-ROADMAP.md` (22 КБ) | 24.07 | [?] |
| `NEWS-LEADS-PIPELINE.md` | 23.07 | [?] |
| `NIGHT-RUN-STATUS.md` | 23.07 | ОТЧЁТ |
| `RUNNER-SETUP.md` | 20.07 | [?] |
| `enrich_panel/README.md` (21 КБ) | 26.07 | ЖИВОЙ |

#### `seo-texts/email-assistant/` (26) — ранняя ветка работ по рассылке

Даты 16–26.07. Здесь лежат ЗАДАНИЯ инженеру и планы, по которым потом собран
`sender/`: `ENGINEER-TASKS-CONFIRM-SEND.md`, `ENGINEER-TASKS-WEB.md`,
`ENGINEER-TASKS-BASE-MERGE.md`, `ENGINEER-TASKS-PANEL-2FEATURES.md`,
`ENG-REVIEW-PANEL.md`, `ENG-FIXLIST.md` — **[ОТЧЁТ]**, задания выполнены.
Аналитика и планы: `OBZVON-REPORT.md` (58 КБ), `NEWS-LEADS-REPORT.md` (30 КБ),
`SENDING-DEBATE.md`, `SEGMENTATION.md`, `DOMAINS-PREP-PLAN.md`,
`DOMAINS-24-ASSIGN.md`, `DOMAINS-CHECK-2026-07-24.md`, `DNS-SETUP-CHECKLIST.md`,
`CONTACT-ENRICHMENT-PLAN.md`, `NEWS-CAMPAIGN-SETUP.md`, `NEWS-LEADS.md`,
`PLAN.md`, `PLAYBOOK.md`, `REPLY-DESK.md`, `SCENARIO-peskostruy.md`,
`TEMPLATE-SESSION-PROMPT.md`, `WEB-AUDIT.md`, `DRYRUN-REPORT.md`,
`BACKLOG-2026-07-25.md` (26.07 — самый свежий), `GEN-TODO.md` (26.07).
**Осторожно:** каталог по названию похож на действующий модуль, но кода
рассыльщика в нём нет — рассыльщик живёт в `seo-texts/sender/`.

#### `seo-texts/kb/` (84 .md + `category-ref/` 10) — **[СПРАВОЧНИК]**

**[ИСПРАВЛЕНО СКЕПТИКОМ]** разбивка была неверной: не «68 brand + 7 category»,
а **62** файла `brand-*.md` + **10** `category-*.md` + 12 сводных = 84.
62 файла `brand-*.md` (по бренду на файл: страна, серии, готовые факты,
раздел «НЕ утверждать»), 10 `category-*.md`
(`category-20-cat`, `-37-`, `-39-`, `-41-`, `-43-`, `-53-`, `-70-cat`,
`category-filtry-magistralnye`, `category-generatory-azota`, `category-resivery`),
сводки `BRENDY-SVODKA.md` (68 КБ),
`ZAVISIMOSTI.md`, `ZAVISIMOSTI-CHISTYE.md`, `KACHESTVO-DANNYH.md`,
`RASHOZHDENIYA.md`, `FILTER-PLAN.md`, `faq-ideas-*.md`, `kp-base-report.md`,
`web-search-facts.md`. Все 16.07. Это гейт достоверности для генерации текстов
(`brand_facts_lib.py`), а не документация о состоянии — «устареть» они не могут,
но новые бренды в них не добавлялись с 16.07.

#### `seo-texts/` корень (40) — почти всё **[ОТЧЁТ]** от 16.07

Крупные: `review-all-50.md` (264 КБ), `review-spot15.md` (107 КБ),
`enger-catalog-notes.md` (103 КБ), `range-mismatch.md` (55 КБ),
`review-engineer-50.md` (42 КБ). Плюс ревью по линзам
(`review-google.md`, `review-yandex.md`, `review-philolog.md`,
`review-engineer.md`, `review-manifest.md`, `schema-card-review.md`),
факты Enger v1–v6, отчёты sweep-ов, `seo-effect-report.md`, `seo-effect-v2.md`.
Свежее и живое: `MASS-ENRICH-RUN.md` (22.07), `NEWS-SOURCES-PLAN.md` (22.07),
`REMAINING-WORK.md` (21.07), `MODEL-COST-DECISION.md` (21.07),
`MODEL-EXTRACT-DECISION.md` (22.07), `KB-EXPANSION-PLAN.md` (22.07),
`KB-COVERAGE.md`, `MARKUP-ROADMAP.md`, `ZVEZDY-FIX.md` (16.07).
Стайлгайды `gen/STYLE-GUIDE*.md` (16.07) — **[СПРАВОЧНИК]**, действуют.

#### Прочие каталоги

* `seo-texts/centrifugal/` (9) — 23.07, исследование центробежных компрессоров
  по 6 линзам + `CENTRIFUGAL-CONTACTS-PLAN.md` (196 КБ). **[ОТЧЁТ]**,
  напрямую питает текущую задачу «ядро 396 ИНН».
* `seo-texts/guest-posts/` (8) — 16.07, гостевые посты. **[ОТЧЁТ]/[СПРАВОЧНИК]**.
* `seo-texts/paket-*` (**7** каталогов — **[ИСПРАВЛЕНО СКЕПТИКОМ]**, было «5»:
  `paket-baza-znaniy`, `paket-dizelnye`, `paket-el-pilot`, `paket-el-r2`,
  `paket-kachestvo`, `paket-poisk`, `paket-poisk-v2`; плюс одноимённые `.zip`) —
  разовые пакеты сдачи. **[ОТЧЁТ]**.
  `paket-poisk` и `paket-poisk-v2` здесь, **`paket-poisk-v3` — только в ветке
  `hopeful-galileo`**.
* `seo-texts/frog/` (3) — 17.07, краулинг. **[ОТЧЁТ]**.
* `seo-texts/manifest/` (1), `seo-texts/manifest-clean.md` — 16.07. **[ОТЧЁТ]**.
* `seo-texts/sender-data/README.md` — 26.07, **[ЖИВОЙ]**, объясняет, почему
  файлы фактов вынесены из пакета.

---

## Данные и где они лежат

* **Ветки и коммиты** — `/home/user/avto/.git`. Единственный remote —
  `origin` через локальный прокси песочницы.
* **Слепки патчей** — `/home/user/avto/seo-texts/sender-patches/` (92 файла,
  13 тематических подкаталогов, ~2 МБ).
* **Разошедшиеся старые версии** — `/home/user/avto/seo-texts/sender-divergent/`
  (4 файла, ~134 КБ).
* **Боевой код рассыльщика** — `/home/user/avto/seo-texts/sender/`
  (265 отслеживаемых файлов на `7e2b968`, 266 на `ba03097`).
* **Данные генератора писем** — `/home/user/avto/seo-texts/sender-data/`
  (`kc-facts.json`, `meyer-facts.json`, `product_glossary.json`,
  `meyer_glossary.json`, `okved-names.json`, `okved-pains.json`).
  Внимание: `sender/ai_letter.py:343-356` ищет их по `SENDER_DIR`
  (по умолчанию `C:\sender`), то есть РЯДОМ с пакетом, а не внутри него.
  Переопределяются env `KC_FACTS`, `MEYER_FACTS`, `KC_GLOSSARY`, `MEYER_GLOSSARY`.
* **Боевые исходники панели обзвона** — `/home/user/avto/seo-texts/obzvon-src/`
  (11 файлов, сняты 27.07 скриптом `server/_ops_pull_obzvon.py`;
  на сервере это `C:\seostat\app`).
* **Скрипты выкатки** — `seo-texts/server/build_panel_update.sh`,
  `preflight_panel.py`, `update-panel.ps1`, `update-obzvon.ps1`.
* **Не влитое** — только в git ветках origin, физически в рабочей копии
  отсутствует (см. таблицы в 1.3–1.5).

Сравнение версий файлов фактов (я сверял):
`sender-patches/meyer-gen/meyer-facts.json`, `meyer_glossary.json`,
`ai-letter/product_glossary.json` — **побайтно равны** копиям в `sender-data/`.
`sender-patches/ai-letter/kc-facts.json` (6,7 КБ) **старее**
`sender-data/kc-facts.json` (15,1 КБ): набор ключей верхнего уровня одинаков
(`clients_verified`, `published_site`, `region_counts_site_index`, `total_crm`),
но в `sender-data` заметно больше подтверждённых клиентов. Брать надо из
`sender-data/`.

---

## Ограничения и грабли

1. **`git branch -a` показывает устаревшую картину.** Ветки создают и двигают
   параллельные сессии. Только `git ls-remote --heads origin` даёт актуальное.
   За время написания этого документа HEAD переехал один раз.

2. **`git log HEAD..origin/<ветка>` вводит в заблуждение.** У
   `persona-prompt-seo-sender-vi4tcq` 28 «невлитых» коммитов, но реально
   не хватает 9 файлов — остальное приехало через сервер. Верить надо
   `git diff --name-status HEAD origin/<ветка>` (две точки) и сравнению дат.

3. **Каталог называется `sender-patches`, но там не diff'ы, а целые файлы.**
   `patch -p1` к ним неприменим. Это слепки для копирования.

4. **`sender-patches` — не источник правды.** Источник правды — боевой сервер;
   репозиторий синхронизируется С НЕГО. Перед любой выкаткой обязателен
   `python seo-texts/server/preflight_panel.py` (возврат 1 = пакет из репо
   затрёт живое). Именно эта проверка 26.07 поймала расхождение в 11 модулей.

5. ~~**`build_panel_update.sh obzvon` сейчас откатит панель обзвона.**~~
   **[ИСПРАВЛЕНО СКЕПТИКОМ: пункт снят.]** На момент среза (16:10) это было верно,
   но коммит `c21cd61` (16:48) обновил все четыре файла
   `sender-patches/obzvon-pagination/` боевыми версиями — сейчас они побайтно
   равны `obzvon-src/`. Что осталось верным и важно помнить:
   `build_obzvon()` пакует **весь каталог целиком**, поэтому любой файл,
   положенный туда «на будущее», уедет на сервер вместе с остальными и
   перезапишет живой. Перед сборкой обзвона — всегда `preflight_panel.py`.

6. **Фронт панели пересобирается только из `sender/web/src`, и часть исходников
   там — восстановленные из sourcemap, а CSS — минифицированный.**
   `sender/web/src/tokens.css` — 8 строк минифицированного CSS с шапкой
   «Восстановлено 26.07.2026 из БОЕВОГО css-бандла»; `styles.css` — 53 строки
   в том же виде. Читаемые исходники дизайн-системы (333 и 958 строк
   с комментариями) есть ТОЛЬКО в `sender-patches/panel-redesign/tokens.css`
   и `styles.css`. Править дизайн по минифицированному файлу почти невозможно —
   берите читаемую версию из патча и сверяйте.
   Проверка из коммита `08317d0`: пересборка из восстановленных исходников
   дала CSS байт в байт равный боевому (`index-RCOtdBt0.css`, 34 704 б).

7. **`build_panel_update.sh` по умолчанию НЕ кладёт фронт** (`WITH_WEB=1`
   включает), и когда кладёт — всегда пересобирает. Это защита после инцидента
   26.07: готовый `dist` из репозитория затёр `index.html` и дал белый экран
   на подтверждении отправки при живом бэкенде (проверка живости смотрела на
   бэкенд и ничего не заметила).

8. **`python -m sender.cli` не работает** — в `cli.py` нет `if __name__`,
   импорт и тихий выход. Точка входа — `python -m sender`
   (`seo-texts/server/PANEL-DEPLOY.md`, раздел «CLI панели»).

9. **Проверка живости панели считает успехом всё, кроме 5xx.** 401 —
   штатная Basic-авторизация. Выкатку пагинации однажды откатили именно из-за
   неверной трактовки 401 (`48ef189`).

10. **Один и тот же файл лежит в патчах в 5–6 редакциях.**
    `store.py` есть в корне `sender-patches/`, в `panel-ux/`, `panel-window/`,
    `review-fixes-wave1/`; `sender.py` — в `panel-window/`, `division-needs/`,
    `review-fixes-wave1/2/3`. Самая свежая редакция из патчей — та, у которой
    меньше всего строк «только в патче» относительно `sender/`, но правильнее
    просто брать `sender/`.

---

## Что сломано или устарело

**Мёртвый код (нет вызывающих):**

* Всё в `seo-texts/sender-patches/`, **кроме** `obzvon-pagination/`, — архив.
  Ценность архива — не код, а `.md`-объяснения и три файла без копий
  (`ai_gen_quota.py`, два `test_ai_letter.py`).

  **[ИСПРАВЛЕНО СКЕПТИКОМ]** Перечень ссылок в исходной редакции был неполон.
  Полный `grep -rn "sender-patches"` (без фильтра по расширению, включая
  `.ts/.tsx/.yaml/.html`) на `ba03097` даёт:
  `server/build_panel_update.sh:18,84,96` (обзвон),
  `server/enrich_panel/panel_core.py:210` и `enrich_panel/README.md:43`
  (копипаст `parse_money`), `sender-data/README.md:8` (историческая ссылка),
  **`obzvon-centro/README.md:145,150-154`** (ранбук, который КЛАДЁТ файлы в
  `obzvon-pagination/` перед сборкой — появился коммитом `c21cd61` после среза),
  `sender-patches/quota-ui/README.md:4` и `sender-patches/panel-ux/PANEL-UX-FIXES.md:44`
  (внутренние перекрёстные ссылки, существовали и на срезе),
  а также `docs/04-kraulery-dannye.md:462`, `docs/09-runner-i-panel.md:505`,
  `docs/13-infrastruktura.md:315,658`.
  Вывод «ни один СКРИПТ, кроме `build_panel_update.sh`, эти файлы не читает»
  остаётся верным; неверен был список ссылок как таковой.
* Всё в `seo-texts/sender-divergent/` — архив по определению.
  Ссылки: `server/PANEL-DEPLOY.md:92` и (появились после среза)
  `docs/11-rassylshchik.md:639,755,760`.
* `seo-texts/sender/gen_module_docs.py` и `assemble_arch.py` — рабочие, но не
  запускались с 20.07 (`module-docs.json` содержит 29 модулей из 44).
  Оба ходят в провайдерский API (`gen_module_docs.py:50`, `assemble_arch.py:69`),
  запуск стоит квоты.

**Ушло из пакета `sender/` (подтверждено грепом по всему `sender/`):**

* Добавление ящика из панели: `POST /mailboxes` + `Config.add_mailbox` +
  `Config.load_mailbox_overrides`.
  **[ИСПРАВЛЕНО СКЕПТИКОМ]** формулировка «живёт только в `sender-divergent/`»
  снята: `server/enrich_contacts.py:6357` зовёт `cfg.load_mailbox_overrides(st)`
  у боевого `C:\sender`, а `email-assistant/TEMPLATE-SESSION-PROMPT.md:70`
  описывает таблицу `mailbox_overrides` как часть БД панели. Есть ли метод и
  таблица в живом `C:\sender` сегодня — **НЕ ПРОВЕРЕНО**, живую БД не смотрели.
  Классифицировать как «утрату» до проверки на сервере нельзя.
* Ручная отправка одного письма через экран Compose (`POST /send/manual`).
  Заменена очередью подтверждений — это задокументированная политика владельца
  (`sender/MANUAL-SEND.md:3`), а не догадка. **[ИСПРАВЛЕНО СКЕПТИКОМ]**
* Тесты КЦ-генерации `tests/test_ai_letter.py` (14–16 тестов).
  Нет ни в дереве, ни в одной ветке origin, ни в истории git — перепроверено
  скептиком тремя способами. Но `ai_letter` не голый: его покрывают 44 теста в
  `test_ai_letter_meyer.py` / `test_gen_57.py` / `test_gate_fixes.py`.
  Без покрытия остались `verifier`, цикл починки письма, `auto_mode`,
  `window_override` (см. раздел 2).

**Файлы, на которые ссылаются живые документы, но которых в дереве нет:**

* `seo-texts/sender/config/mailboxes.kc.yaml` — ссылки из 4 документов;
  есть только в `origin/claude/persona-prompt-seo-sender-vi4tcq`.

**Устаревшая документация с проверенным расхождением:**

* `sender/SENDER-ARCHITECTURE.md` — покрывает 29 модулей из 44.
* `SESSION-INDEX.md` — состояние на 17.07 (сендер «в баг-ханте», домены «купить»).
* `RUNBOOK.md:11`, `sender/OWNER-TODO.md`, `sender/HANDOFF-2026-07-24.md` —
  указывают ветки, в которых работа больше не идёт.
* `sender/RUNBOOK-DEPLOY.md` (20.07) против `server/PANEL-DEPLOY.md` (26.07):
  два описания выкатки, актуально второе.

**Не сломано, но легко принять за поломку:**

* В git из `sender/web/dist/` отслеживается только `index.html` (433 б) — бандл
  в `sender/web/.gitignore` (`dist/`). Собранного фронта в репозитории нет и
  быть не должно. **[ИСПРАВЛЕНО СКЕПТИКОМ]**: на диске каталог сейчас НЕ пуст —
  параллельная сессия собрала фронт в 16:39, и рядом лежит неотслеживаемый
  `dist/assets/` (`index-B5Ru9v7m.js` + `.js.map` + `index-CT4LU7v5.css`).
  Это локальная сборка, git её не видит.
* `sender/tests/` содержит 69 тестовых файлов на `7e2b968` и 70 на `ba03097`
  (коммит `e2004dc` добавил `test_dialog_threads.py`), но `test_ai_letter.py`
  среди них нет (см. выше) — это не забытая чистка, файла не было никогда.

---

## Что не проверено

1. **Ни автор, ни скептик не запускали pytest.** Утверждения о покрытии сделаны
   по грепу и по чтению тестов, а не по прогону. **[УТОЧНЕНО СКЕПТИКОМ]**
   гипотеза «часть проверок дублируется под другими именами» подтвердилась
   частично: `gate`/`allowed_numbers`/`gen_prompt`/`load_facts` покрыты
   (44 теста в трёх файлах), а `verifier`, цикл починки, `auto_mode` и
   `window_override` — нет ни под какими именами. Формулировка в разделе 2
   исправлена. Прогон pytest всё равно нужен, чтобы узнать, зелёные ли эти 44.

2. **Я не сверял содержимое боевого сервера.** Всё «в бою» в этом документе
   означает «в каталоге `seo-texts/sender/` текущей ветки», который был
   синхронизирован с сервером 26.07 и с тех пор правился ещё 41 + 32 коммитами.
   Реально ли на `C:\sender` лежит то же самое — проверяется только
   `preflight_panel.py`, а его запуск при боевом обогащении запрещён.

3. **Замена роутов — предположение.** Что `POST /campaigns/{cid}/generate`
   заменён на `POST /ai/quota/run`, а `GET /campaigns/{cid}/generate/{gid}` —
   на `GET /ai/quota`, я вывел по смыслу имён и по тому, что квота генерации
   появилась позже. Обработчики построчно не сравнивал.

4. **Осознанность потери `POST /mailboxes` не установлена.** Возможно, ящики
   намеренно перевели на yaml-конфиг. Я показал только факт отсутствия кода.

5. **Ветка `rusprom-b2b-email-templates-8rrstf`: выполнена ли её спека.**
   `PANEL-INTEGRATION-SPEC.md` и `PROMPT-DLYA-VETKI-DVIZHKA.md` — задание на
   вшивание генератора в ядро. Генератор в ядре есть, но я НЕ сверял пункты
   спеки с `ai_letter.py`. Возможно, часть требований не реализована.
   Так же не проверял, не устарели ли 49 писем в `kc-regen-49.json`.

6. **Ветка `hopeful-galileo-n8gg7o`: качество поискового пакета v3.**
   Я установил только, что файлов нет в текущем дереве. Что именно показал
   «контрольный прогон тех же 1000 фраз после починки» — не читал.

7. **Актуальность 40 `.md` в корне `seo-texts/` и 26 в `email-assistant/`
   проверена только по дате и заголовку.** Метки `[?]` в реестре означают
   ровно это: я не сверял их содержимое с кодом. Для `sender/SITE-DESIGN.md`,
   `CONTRACT.md`, `ROADMAP.md`, `HOW-IT-WORKS.md` это особенно существенно —
   документы большие и на них могут ссылаться.

8. **84 файла `seo-texts/kb/*.md` я не читал** — открыл один
   (`BRENDY-SVODKA.md`) для понимания формата. Утверждение «данные, а не
   документация о состоянии» основано на формате этого одного файла и на
   `CLAUDE.md`.

9. **Я не проверял, нет ли работы вне git.** На дропе владельца
   (`DROP_URL`) лежат тяжёлые исходники и результаты, которых в репозитории
   нет по определению. `bash seo-texts/server/drop_client.sh list` я не
   запускал — на сервере идёт боевое обогащение, а правила сессии запрещают
   операции с дропом кроме чтения кода.

10. **Репозиторий менялся во время съёмки.** Коммит `7e2b968` (15:52) добавил
    `obzvon-src/` и два раздела документации уже после того, как я начал
    считать. Числа файлов и размеры каталогов могли сдвинуться ещё раз.
    Все выводы стоит перепроверять на своём HEAD.

11. **Причины, по которым ветки почти не мержились, мне неизвестны.** Возможно,
    это осознанная политика (каждая сессия — своя ветка, слияние через сервер),
    возможно — накопившийся долг. Один merge всё-таки был (`b1bfc6c`, 22.07),
    то есть инструмент не запрещён. Решение о слиянии принимает владелец.

---

## Что проверил скептик (2026-07-27, HEAD `ba03097`)

**Подтвердилось без правок:** 9 невлитых файлов ветки `persona-prompt` (и что
`mailboxes.kc.yaml` есть только в ней — перебор всех refs); отсутствие
`test_ai_letter.py` во всей истории git и во всех ветках origin; счёт роутов
51 старых / 68 боевых и ровно 5 «только старых»; `SENDER-ARCHITECTURE.md` — 29
модулей из 44 и все 15 недокументированных имён; побайтное равенство 14 пар
патч↔бой, включая `theme.ts` (`web/src/lib/`) и `ui.tsx` (`web/src/components/`);
`division-needs/company_card.py` — строгое подмножество (+40 строк в бою);
дельты `sender-divergent` (263 и 1224 байта, 21 команда `add_parser` в обеих
версиях, `init_schema` на `cli.py:55` и `:497`); строки CSS (8/53 против 333/958);
все 17 проверенных размеров файлов в реестре `.md`; 10 файлов ветки
`hopeful-galileo` и 14 файлов ветки `rusprom-b2b`; `48ef189` = 21 M + 32 A
в `sender/`; `RUNBOOK.md:11`, `ai_quota.py:8`, `ai_letter.py:343-356`,
`CONFIRM-QUEUE-FIX.md:12`, `panel_core.py:210`, `test_ai_letter_meyer.py:4`,
`PANEL-DEPLOY.md:92`; отсутствие тегов и стэшей; `python -m sender.cli` не
работает (в `cli.py` нет `if __name__`, точка входа — `sender/__main__.py`).

**Скептик тоже НЕ проверял:**

* боевой сервер (`C:\sender`, `C:\seostat\app`) и живую БД панели — идёт боевое
  обогащение, `run_on_server`/`preflight_panel.py` запрещены. Всё «в бою» в этом
  документе по-прежнему означает «в каталоге репозитория»;
* дроп владельца (`drop_client.sh list` не запускался);
* прогон pytest;
* содержимое ветки `hopeful-galileo` (что показал контрольный прогон 1000 фраз);
* пофразовую сверку `PANEL-INTEGRATION-SPEC.md` с `sender/ai_letter.py`;
* содержимое документов с меткой `[?]` (`SITE-DESIGN.md`, `CONTRACT.md`,
  `ROADMAP.md`, `HOW-IT-WORKS.md` и остальные) — метки оставлены как были;
* наличие/отсутствие pull-request'ов на GitHub (`gh` в среде нет, `origin` —
  локальный прокси).
