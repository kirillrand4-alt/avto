# Фикс: исходящие письма кампаний → очередь подтверждений (2026-07-24)

Проблема (подтверждена тройным грепом по ветке инженера
`claude/persona-prompt-seo-sender-vi4tcq`): оркестратор в `tick()` отправлял
исходящие письма НАПРЯМУЮ через `sender.send()` и НИКОГДА не вызывал
`confirm.submit()`. `confirm.submit`/`pending_review` для исходящих были только
в офлайн-скриптах (`tools/calibration_dryrun.py`, `tools/dryrun_basemerge.py`).
`confirm` в `wiring` создавался и отдавался автоответчику и панели-на-чтение, но
в `Orchestrator` НЕ передавался. Итог: боевой `run` наполнял очередь подтверждений
НИКОГДА — оператор видел пустой экран «Подтвердить отправку».

## Что изменено (файлы — копии из ветки инженера + правки, для мерджа)

- **orchestrator.py**: `Orchestrator.__init__` принимает `confirm=None`; в send-loop,
  после успешного рендера и до `pick_mailbox`, если `confirm.mode()!='off'` —
  строит инфо-панель (`_build_confirm_panel`, из enrich.db + company_card),
  вызывает `confirm.submit(...)`, помечает сообщение `mark_pending_review` и
  переходит к следующему (без прямой отправки). Сбой submit → сообщение остаётся
  'sending', `recover_stale` вернёт в 'scheduled' (письмо не теряется, вслепую не
  шлётся). Добавлен счётчик `queued` в `TickResult`.
- **store.py**: `mark_pending_review(message_id)` — статус 'pending_review',
  claim_due его не берёт; approve/edit оператора вернёт в 'scheduled'.
- **cli.py**: `_cmd_run` передаёт `confirm=deps.confirm` в `Orchestrator`.
- **dtos.py**: `TickResult.queued: int = 0` (дефолт — обратная совместимость).
- **tests/test_orchestrator.py**: +2 теста (mode='all' → в очередь, не отправка;
  mode='off' → прежнее прямое поведение). Полный сьют 953 passed.

## Идемпотентность/холд

`confirm_submit` идемпотентен по `dedup_key` (`ON CONFLICT DO NOTHING`) —
повторный тик не сбрасывает одобренные. Под холдом (`confirm.live_send=false`)
approve только помечает, реального SMTP нет.

## Хвост для инженера (когда снимут холд, live_send=true)

Уточнить переход approve→send при включённом live_send: сейчас approve возвращает
message в 'scheduled', следующий тик снова положит его в pending_review (submit
идемпотентен, статус review не сбросится, но message оседает в pending_review).
Для боевого режима свести approve→немедленная отправка (`_send_live` уже есть) и
исключить повторный захват отправленных. Под холдом не критично.

Развёрнуто через дроп (`panel-update.zip`) 2026-07-24.
