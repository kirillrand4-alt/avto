# Карта областей работы (session index)

Список областей, над которыми шла работа, с ключевыми файлами и статусом. Каждая
строка = кандидат на **свою отдельную сессию** (см. `WORKING-PROTOCOL.md`).

Легенда хранения: **[git]** в репозитории (durable) · **[scratch]** в scratchpad
сессии (ЭФЕМЕРНО, копировать в git/на drop перед новой сессией) · **[drop]** на
файловом обменнике владельца.

## SEO-направление (prokompressor.ru, 759 страниц)

| Область | Ключевые файлы | Статус |
|---|---|---|
| Генерация/регенерация текстов | `seo-texts/regen_driver.py`, `qa_text.py` [git]; `regen-state.json` [scratch] | много прогонов сделано |
| Правка диапазонов чисел/фактов | `scan_ranges.py`, `patch_ranges.py`, `range-mismatch-final.md` [scratch] | применено |
| Чистка манифеста/бренд-фактов | `rewrite_manifest.py`, `brand-power-full.json` [scratch] | сделано |
| Оценка SEO-эффекта текстов | `seo-effect-report.md`, `review-spot15.md`, `ctr-curve.json` [scratch] | отчёт готов |
| Гост-посты / акцепторы | `seo-texts/frog/acceptor_value.py` [git]; `link-projects-report.md` [scratch] | ранжирование готово; пилот 5 статей — TODO (task #9) |

## Аналитика данных под ВП

| Область | Ключевые файлы | Статус |
|---|---|---|
| Ревью выгрузки под рост ВП | `build_datapack_v3.py`, `data_value_review.py`, `data-value-review-v3.json` [scratch] | v3 прогнан (6 линз вкл. скептик данных) |
| Сплит квал-лидов SEO vs Директ | **`channel-truth.json`** → скопирован в `seo-texts/email-assistant/` [git] | ЗАФИКСИРОВАН: паритет |
| «Зачем крутят показы Google» | `why-impressions.json` [scratch] | вердикт: рэнк-трекинг/скрейпинг, вред нейтрален |

## Разметка

| Область | Ключевые файлы | Статус |
|---|---|---|
| Микроразметка (звёзды + дорожная карта) | `markup-roadmap-google.json`, `-yandex.json`, `ZVEZDY-FIX.md` [scratch] | карты + фикс готовы |

## Рассылка (обзвон-база 161к)

| Область | Ключевые файлы | Статус |
|---|---|---|
| Анализ базы + письма + критики | `obzvon-letters.json`, `obzvon-critics.json`, `mx-summary.json` [scratch] | v1 писем на вычитку |
| Ревью стратегии рассылки | `dialog-review.json`, `mailing-meta-review.json` [scratch] | вердикт: НЕ готова, 1-2 нед доработки |
| Чистка базы от конкурентов | `competitors_flag.py`, `competitors-verdict.json`, `suppression-*.txt` [scratch] | 19 конкурентов подтв.; +20 «неясных» на решение владельца; ждём корп-список ИНН |
| Разведка coldy + инбоксы | `seo-texts/sender/FEATURES-PLAN.md` [git]; `coldy-*.json` [scratch] | разобрано; вывод — строим свой сендер |
| **Свой сендер-сервис** | `seo-texts/sender/` [git] — см. `SENDER-STATE.md` | генерация модулей → баг-хант |

## Мета

| Область | Файл | Статус |
|---|---|---|
| Протокол качества сессий | `WORKING-PROTOCOL.md` [git] | зафиксирован |
| Эта карта | `SESSION-INDEX.md` [git] | живой документ |

## Открытые решения владельца

- Рассылка: выбрать юр-линию (адресное B2B-предложение vs согласие) под ФЗ-38;
  принять атрибуцию ООО «Руспром» + ИНН в письме-1 (отменяет «бренд позже»).
- Конкуренты: решить по 20 «неясным» + дать корп-список ИНН конкурентов.
- Инбоксы: закупка ~10 доменов .ru + ~30 ящиков Яндекс360/VK (смета в
  `coldy-inboxes.json`).
