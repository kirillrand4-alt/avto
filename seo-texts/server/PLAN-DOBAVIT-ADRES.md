# План правки: «добавить адрес получателя» в панели рассылки

> Собран рабочим потоком из пяти читателей по репозиторию 5 августа 2026.
> Заказ владельца: «в панели рассылки добавь возможность добавлять контакт»,
> объём выбран владельцем — **с привязкой к ИНН из базы обзвона**; место —
> экран «Подтвердить отправку», рядом с выпадающим списком «кому:».
> Причина: новости иногда привязываются не к тому предприятию, и адрес
> в списке оказывается неверным.
>
> **ВАЖНО ПЕРЕД ВЫКЛАДКОЙ.** Серверный `C:\sender\sender\api\app.py`
> (81 936 б, 73 маршрута) ушёл ВПЕРЁД репозиторного (73 801 б, 68 маршрутов):
> на сервере есть 5 маршрутов и фильтр направления КЦ/Meyer, которых в репо
> нет. Правки вносить в СЕРВЕРНЫЙ файл, копию снимать в репо. Обратный
> порядок затрёт чужую работу.

# ПЛАН: «добавить адрес получателя» на экране «Подтвердить отправку»

Область: только **другой контакт ТОГО ЖЕ предприятия** (ИНН карточки). Ставим НОВУЮ ручку рядом со старой; старую (`POST /confirm/{rid}/recipient` с allow-листом, confirm.py:319-327) **не ослабляем** — решение владельца о закрытом списке остаётся в силе, свободный ввод идёт отдельным, проверяемым путём с записью контакта в базу под ИНН.

---

## 1. БЭКЕНД

### 1.1 `/home/user/avto/seo-texts/sender/store.py` — два новых метода (вставить после `confirm_change_email`, т.е. после строки 2356)

```python
    def find_recipient_by_email(self, email: str) -> dict | None:
        """Строка recipients по адресу (UNIQUE(email)) или None."""
        row = <conn>.execute(
            "SELECT id, email, inn, company_name, segment, suppressed "
            "FROM recipients WHERE email=?",
            ((email or "").strip().lower(),)).fetchone()
        return dict(row) if row else None

    def confirm_update_panel(self, review_id: int, panel: dict) -> None:
        """Перезаписать panel_json карточки; только в статусе pending."""
        cur = <conn>.execute(
            "UPDATE confirm_reviews SET panel_json=?, updated_at=? "
            "WHERE id=? AND status='pending'",
            (json.dumps(panel, ensure_ascii=False), _now_iso(), review_id))
        if cur.rowcount == 0:
            raise ValidationError(f"карточка {review_id} не в статусе pending")
```

`<conn>` и `_now_iso()` — подставить идиом соседних методов (`upsert_recipient` store.py:801-850, `confirm_change_email` store.py:2326-2356). **Не установлено:** точный способ получения соединения в store — в разборе не показан.

### 1.2 `/home/user/avto/seo-texts/sender/confirm.py` — новый метод (вставить после `set_recipient_email`, т.е. после строки 337)

```python
    def add_recipient_email(self, review_id: int, email: str, *,
                            note: str | None = None,
                            operator: str = "", actor_user_id=None) -> dict:
        """Добавить контакт, которого нет в карточке, привязать к ИНН этой
        карточки (база обзвона) и сделать его получателем письма."""
        row = self._require_pending(review_id)                 # confirm.py:762-766

        # (а) ВАЛИДАЦИЯ АДРЕСА — тем же нормализатором, что импортёр
        target = _normalize_email(email)          # importer.py:141-155 (имя функции
                                                  # уточнить на месте — в разборе не названо)
        if not target:
            raise ValidationError(f"некорректный адрес: {email!r}")

        # (б) SUPPRESSION по НОВОМУ адресу/домену/ИНН — тем же вызовом, что approve
        hit = self._suppression_hit(email=target, inn=row.get("inn"))   # сигнатуру взять
                                                  # с вызова confirm.py:375 (_guard/_suppression_hit)
        if hit:
            raise ConfirmBlockedError(
                f"адрес {target} в стоп-листе ({hit}) — добавить нельзя")

        # (в) ПРИВЯЗКА К ИНН БАЗЫ ОБЗВОНА
        inn = (row.get("inn") or "").strip()
        exist = self._store.find_recipient_by_email(target)
        if exist and (exist.get("inn") or "") and inn and exist["inn"] != inn:
            raise ConfirmBlockedError(
                f"адрес {target} уже закреплён за ИНН {exist['inn']}, "
                f"карточка — ИНН {inn}: адрес чужой компании добавлять нельзя")
        created = False
        if not exist:
            base = self._base_recipient(row)   # исходный получатель тем же путём, что
                                               # _send_live_inner (confirm.py:505-513):
                                               # message_id -> messages -> recipients
            self._store.upsert_recipient(RecipientIn(     # dtos.py:9-26
                email=target,
                domain=target.split("@", 1)[1],
                inn=inn,
                company_name=base.get("company_name"),
                okved=base.get("okved"),
                segment=base.get("segment"),
                contact_name=None,
                source="panel_manual",
                region=base.get("region"),
                tz=base.get("tz"),
            ))
            created = True

        # (г) АУДИТ — до подмены, без глушения (в отличие от confirm.py:330-336:
        #     там audit «не критичен», здесь меняется база получателей)
        self._store.add_audit(
            action="recipient_added", entity_type="confirm_review",
            entity_id=review_id,
            detail={"email": target, "inn": inn, "created_recipient": created,
                    "operator": operator, "note": note},
            actor_user_id=actor_user_id)

        # (д) вписать адрес в panel.emails -> он проходит allow-лист и виден в <select>
        panel = dict(row.get("panel") or {})
        emails = list(panel.get("emails") or [])
        if not any((e.get("email") or "").strip().lower() == target for e in emails):
            emails.append({"email": target, "role": "добавлен оператором",
                           "person": None, "mx_ok": None, "source": "оператор",
                           "source_url": None, "added_by": operator,
                           "added_at": datetime.now(timezone.utc).isoformat()})
            panel["emails"] = emails
            self._store.confirm_update_panel(review_id, panel)

        # (е) дальше — штатная ручка: dedup_key, статус pending, коллизия очереди
        review = self.set_recipient_email(review_id, target, operator=operator,
                                          actor_user_id=actor_user_id)
        return {"review": review, "created_recipient": created}
```

Ключевое: после (д) существующая `set_recipient_email` (confirm.py:309-337) проходит allow-лист штатно — **её код не трогаем**, тест `test_change_email_rejects_foreign` остаётся зелёным.

### 1.3 `/home/user/avto/seo-texts/sender/api/app.py`

Модель — рядом с `RecipientBody` (строки 80-81):

```python
class AddRecipientBody(BaseModel):
    email: str
    note: str | None = None
```

Эндпоинт — сразу после `confirm_set_recipient` (после строки 697):

```python
    @app.post("/confirm/{rid}/recipient/add")
    def confirm_add_recipient(rid: int, body: AddRecipientBody,
                              p: Principal = Depends(principal)):
        """Добавить новый контакт компании и сразу выбрать его получателем."""
        from sender.confirm import ConfirmBlockedError
        from sender.errors import ValidationError as _VErr
        if not deps.settings_flag("confirm.allow_manual_recipient", True):
            raise HTTPException(status_code=403, detail="ручной ввод адреса выключен")
        try:
            res = deps.confirm.add_recipient_email(
                rid, body.email, note=body.note,
                operator=p.username, actor_user_id=p.user_id)
        except ConfirmBlockedError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except _VErr as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, **res}
```

Коды разведены намеренно: **400** — синтаксис/статус/дедуп (как в старой ручке), **409** — комплаенс-блок (как approve, app.py:734-736).

Права: `Depends(principal)` — оператор уже может менять адрес и делать force-approve (app.py:686, 701). Если владелец решит, что запись в `recipients` — только его прерогатива (импорт owner-only, app.py:431), меняется одно слово на `Depends(owner)`.

`deps.settings_flag(...)` — фича-флаг для выключения без выкатки. **Не установлено:** есть ли в `deps` такой хелпер; если нет — читать из config напрямую или временно убрать проверку.

### 1.4 Обязательный довесок по ФЗ-38 (иначе фича создаёт дыру в отписке)

Отписка/bounce/жалоба суппрессят `recipient.email` из таблицы `recipients` (unsub.py:129-134, imap_watcher.py:381/426/503), а не фактический адрес доставки. Человек, которому вписали адрес руками, нажмёт «отписаться» — в стоп-лист уйдёт **базовый** адрес, а ему можно будет писать снова.

Правка: в `unsub.handle_one_click` и в трёх точках `imap_watcher` суппрессить **и** фактический адрес последней отправки из `send_log` (он там пишется верно — sender.py:720-728). **Не установлено:** схема `send_log` (в разборе видны только `email` и `inn`, есть ли `recipient_id`/`campaign_id` — не показано) — колонки уточнить в store.py перед правкой.

Пока это не сделано — компенсирующий контроль: кнопка «стоп-лист» в панели суппрессит именно текущий адрес карточки (confirm.py:736-757), плюс CLI `import_suppression` (cli.py:20). Оператору — обязательная инструкция: на любой ответ «отпишите» жать «стоп-лист», а не только помечать лид.

---

## 2. ФРОНТ

### 2.1 `/home/user/avto/seo-texts/sender/web/src/api/client.ts` — после строки 249

```ts
  confirmAddRecipient: (id: number, email: string, note?: string) =>
    req<{ ok: boolean; review: ConfirmReview; created_recipient: boolean }>(
      "POST", `/confirm/${id}/recipient/add`, { email, note }),
```

Тип возврата `review` — тот же, что у `confirmSetRecipient` (client.ts:249); имя типа подставить фактическое.

### 2.2 `/home/user/avto/seo-texts/sender/web/src/screens/Confirm.tsx`

**Состояние** — после строки 702 (`const [reason, setReason] = useState("")`):

```tsx
  const [newEmail, setNewEmail] = useState("");
```

**Мутация** — после строки 805 (сразу за `setRecipient`), в его же стиле:

```tsx
  const addRecipient = useMutation({
    mutationFn: (email: string) => api.confirmAddRecipient(current!.id, email.trim()),
    onSuccess: (_d, email) => {
      setNewEmail("");
      toast("success", `Адрес добавлен и выбран: ${email.trim()}`);
      qc.invalidateQueries({ queryKey: ["confirm-queue"] });
    },
    onError: (err) => {
      if (err instanceof ApiError) toast("error", `Новый адрес: ${err.detail}`);
      else toast("error", `Новый адрес: ${(err as Error).message}`);
    },
  });
```

**JSX** — вставить между строкой 1021 (`</label>` блока «кому:») и строкой 1022, внутрь `<div className="confirm-routing">`:

```tsx
            <label>
              новый адрес:{" "}
              <input
                type="email"
                placeholder="name@company.ru"
                value={newEmail}
                disabled={addRecipient.isPending}
                style={{ width: "18rem" }}
                onChange={(e) => setNewEmail(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    if (newEmail.includes("@")) addRecipient.mutate(newEmail);
                  }
                }}
              />
            </label>
            <button
              className="btn btn-sm"
              disabled={addRecipient.isPending || !newEmail.includes("@")}
              onClick={() => addRecipient.mutate(newEmail)}
            >
              {addRecipient.isPending ? "…" : "добавить"}
            </button>
```

Сброс поля при переключении карточки — рядом с прочими эффектами:

```tsx
  useEffect(() => { setNewEmail(""); }, [current?.id]);
```

CSS не трогаем: `.confirm-routing` — flex с `flex-wrap` (styles.css:10-14), пара input+button переносится сама; `.btn btn-sm` уже есть. Глобальные хоткеи экрана (Confirm.tsx:858-882) игнорируют ввод в `INPUT` (строки 860-863) — конфликта нет.

---

## 3. ПОРЯДОК ВЫКЛАДКИ (канон `seo-texts/server/PANEL-DEPLOY.md`)

1. Локально: `cd seo-texts/sender/web && npx tsc -b --noEmit && npm run test` (build = `tsc -b && vite build`, ошибка типов = нет бандла). Плюс pytest по затронутым: `test_confirm_recipient_sent.py`, `test_confirm_live_smtp.py`, `test_confirm_parity.py`, `test_division_gate.py`, `test_confirm.py`, `test_suppression.py`, `test_api.py`.
2. **`python seo-texts/server/preflight_panel.py`** → должен вернуть 0 (репо не старше боя). Помнить: каталог `web` он не проверяет вообще.
3. Сборка пакета — **обязательно с флагом фронта**, иначе интерфейс не поедет:
   `WITH_WEB=1 bash seo-texts/server/build_panel_update.sh`
   Скрипт сам пересоберёт фронт (`npm install && npm run build`) и проверит, что каждый `/assets/...` из `index.html` физически лежит в `dist` (иначе exit 1). Сверить `UPDATE-MANIFEST.txt` и что в zip есть `sender/` и `web/dist/`.
4. Заливка на дроп: скрипт сам делает `drop_client.sh up` для `panel-update.zip` и обоих `.ps1`. Проверить `bash seo-texts/server/drop_client.sh list`.
5. Выкатка — владельцу ОДНОЙ командой (без `&&`):
```powershell
$tok=(Select-String -Path C:\sender\server\runner-secrets.env -Pattern 'DROP_TOKEN=').Line.Split('=',2)[1].Trim()
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/update-panel.ps1" -Headers @{'X-Drop-Token'=$tok} -OutFile C:\sender\update-panel.ps1
powershell -ExecutionPolicy Bypass -File C:\sender\update-panel.ps1
```
   `update-panel.ps1` сам: качает zip (< 10000 б → throw), **бэкапит `C:\sender\sender` и `C:\sender\web\dist` в `C:\sender\_bak-panel-<yyyyMMdd-HHmmss>`**, `Stop-Service SenderPanel -Force` → `Expand-Archive -Force` → `Start-Service`, ждёт health `http://127.0.0.1:8091/api/health` (10 попыток × 3 с; живой = любой не-5xx, **401 — норма**), сверяет ассеты `index.html` с `C:\sender\web\dist\assets\`, при провале — **автоматический откат обеих папок и exit 1**.
   Альтернатива без владельца: раннер-оп `panel_zip_deploy` (enrich_contacts.py:8388-8462) — тот же бэкап + nssm stop/start.
6. В браузере — Ctrl+F5 (index.html отдаётся `no-store`, но кэш страницы у оператора может быть открыт).

---

## 4. ЧЕМ ПРОВЕРИМ

HTTP (Bearer оператора, база `/api`), `RID` — id pending-карточки:

| Проба | Ожидание |
|---|---|
| `POST /confirm/{RID}/recipient/add {"email":"snab@<домен той же компании>.ru"}` | **200**, `created_recipient: true`, `review.email` = новый адрес |
| повтор той же команды | **200**, `created_recipient: false` (строка в `recipients` уже есть, ИНН совпал) |
| `GET /confirm/queue` | в `panel.emails` карточки **на 1 элемент больше**, у нового `source: "оператор"`; в `<select>` «кому» он виден и выбран |
| адрес, уже закреплённый в `recipients` за другим ИНН | **409** «уже закреплён за ИНН …» |
| адрес из стоп-листа | **409** «в стоп-листе (…)» |
| `{"email":"abc"}` | **400** «некорректный адрес» |
| карточка в статусе `sent`/`skipped` | **400** «не в статусе pending» |
| адрес, уже стоящий в очереди на тот же ИНН+кампанию | **400** «адрес … уже в очереди» (store.py:2345-2352) |
| без `Authorization` | **401** |

БД на сервере (`C:\sender`, sqlite панели):
- `SELECT COUNT(*) FROM recipients WHERE email='<новый>'` → **1**; `inn` = ИНН карточки; `source='panel_manual'`.
- `SELECT COUNT(*) FROM recipients WHERE source='panel_manual'` до/после → **+1**.
- Аудит: две записи на одну операцию — `recipient_added` и `recipient_changed` (последняя из `set_recipient_email`), `entity_type='confirm_review'`, `entity_id=RID`.

Боевая проба (в рамках частичного снятия холда — ручная отправка, approve оператором):
- approve карточки при `confirm.live_send: true` → письмо приходит **на новый адрес**; в заголовках письма есть `List-Unsubscribe` и байлайн «ООО «Руспром», ИНН 2221239841».
- `send_log`: новая строка с `email` = **новый адрес**, `inn` = ИНН карточки (проверка 90-дневного заслона по обоим ключам).
- Регресс-эквивалент в тестах: `test_confirm_live_smtp.py:200` — конверт `RCPT TO` = новый адрес, старого среди получателей нет.

Порядок проб: сначала dry-run/локальный pytest, затем 400/409-негативы на бою (они ничего не отправляют), и только потом один живой approve.

---

## 5. ЧТО МОЖЕТ СЛОМАТЬСЯ / ОТКАТ

**Риски правки:**
1. `upsert_recipient` идёт `ON CONFLICT(email) DO UPDATE` с COALESCE — непустой новый `inn` **перезаписал бы** чужой. Закрыто проверкой (в) с 409; если проверку выкинуть — тихая порча базы обзвона.
2. Перезапись `panel_json`: параллельный `POST /confirm/{rid}/regenerate` (owner-only, app.py:1035) пересобирает панель и **потеряет** добавленный адрес → повторить добавление после регенерации.
3. Статистика и домённые гейты по-прежнему считают через join на исходного получателя (store.py:1355-1372, sender.py:751-755) — bounce/complaint с ручного адреса приписывается базовому домену. Этой правкой **не чинится**.
4. Провайдер-сплит берёт `recipient.mx_provider` исходной строки (sender.py:872-881), ящик подбирается до подмены (confirm.py:527) — письмо на mail.ru-адрес может уйти с яндекс-ящика. Не чинится, риск — доставляемость.
5. Отписка/bounce/жалоба — см. п. 1.4; до его выполнения фича оставляет комплаенс-дыру.
6. Опечатка оператора = hard bounce, а он двигает kill-switch (CONTRACT.md:816). MX-проверки в `sender.send` нет. Смягчение: `type="email"`, дизейбл кнопки без `@`, регексп импортёра.
7. Сборка без `WITH_WEB=1` → фронт не поедет, «фича не появилась» при зелёном деплое.

**Откат:**
- Автоматический: `update-panel.ps1:120-136` откатывает `sender` и `web\dist` из `_bak-panel-<ts>` и стартует службу при провале health/сверки ассетов.
- Ручной: `Stop-Service SenderPanel -Force` → `Copy-Item C:\sender\_bak-panel-<ts>\* -Recurse -Force` поверх → `Start-Service SenderPanel`.
- Мгновенный, без выкатки: фича-флаг `confirm.allow_manual_recipient: false` в `C:\sender\config.yaml` + `Restart-Service SenderPanel -Force` → ручка отдаёт 403, старое поведение возвращается целиком.
- Данные: удалять `recipients` НЕ вслепую — только по списку адресов из аудита `recipient_added` (`source='panel_manual'`), и лучше не удалять, а оставить: строка не вредит, она с правильным ИНН.

---

## 6. ЧЕГО ДЕЛАТЬ НЕЛЬЗЯ

1. **Не ослаблять `set_recipient_email` (confirm.py:319-327)** и не удалять/не «чинить» тест `tests/test_confirm_recipient_sent.py:74` `test_change_email_rejects_foreign` — это зафиксированное решение владельца («чтобы оператор не вписал произвольный/чужой адрес»). Новый путь его не отменяет, а обходит легально: адрес сначала проверяется и заводится в базу под ИНН, и только потом попадает в allow-лист карточки. Если этот тест покраснел — правка сделана неправильно.
2. **Не обходить стоп-лист.** Проверка на добавлении обязательна; двойная проверка в `sender.py:602` и `sender.py:689` — не трогать. Флаг `force` на новую ручку **не распространять** (в `AddRecipientBody` его нет и быть не должно).
3. **ФЗ-38/ФЗ-152 — без исключений:** атрибуция «ООО «Руспром», ИНН 2221239841» в КАЖДОМ письме и `List-Unsubscribe` one-click (HOW-IT-WORKS.md:28-29) — ручной адрес ничего из этого не отменяет. Инвариант MANUAL-SEND.md:22: **обходится только «когда», никогда — «можно ли»**.
4. **Не менять ИНН карточки и не обходить гейт направлений.** Адрес привязывается к ИНН письма, а не наоборот; `division_block` (sender.py:404-438) и `_division_flags` (confirm.py:102-143) продолжают работать по этому ИНН.
5. **Не использовать фичу для отправки на ДРУГОЕ предприятие.** Если новость привязалась не к той компании — тело письма уже отрендерено с её `company_name`/`contact_name`, и гейт пустых `{}` этого не поймает. Правильный путь: `skip` карточки + `regenerate` под верную компанию (owner-only, app.py:1035). Ручка `add_recipient` этот случай блокирует 409-й, если адрес уже закреплён за другим ИНН, но при чистом адресе не спасёт — это дисциплина оператора.
6. **Холд остаётся:** автоматическая рассылка и прогрев запрещены. Разрешена только ручная отправка через approve оператором (частичное снятие 2026-07-24).
7. **Не чистить `C:\sender\web\dist\assets` и `_bak-panel-*`** — старые бандлы и есть материал отката; по документации из бандла один раз уже восстанавливали исходники.
8. **Не заявлять паритет CLI↔панель**, пока в `confirm_cli.py` нет соответствующей команды (сейчас там нет даже смены адреса) — либо добавить `confirm-add-recipient` тем же вызовом `ConfirmSend.add_recipient_email`, либо явно записать расхождение в MANUAL-SEND.md.
9. Дыру `if allowed and target not in allowed` (confirm.py:325 — при пустом списке контактов проходит любой адрес) закрывать **отдельным шагом**, после того как новая ручка приживётся; в этой правке её не трогать, иначе сломается поток по карточкам без контактов.