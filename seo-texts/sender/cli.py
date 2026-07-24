"""CLI-интерфейс сервиса рассылки.

Тонкая обёртка над модулями движка для запуска через `python -m sender`.
"""

import argparse
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sender.analytics import Analytics
from sender.cadence import Cadence
from sender.config import Config
from sender.gates import Gates
from sender.imap_watcher import ImapWatcher
from sender.importer import import_csv, import_suppression, validate_recipients
from sender.notify import Notifier
from sender.orchestrator import Orchestrator
from sender.personalize import Personalizer
from sender.sender import Sender
from sender.store import (
    CampaignIn,
    ConfigError,
    SequenceStepIn,
    SenderError,
    Store,
    StoreError,
)
from sender.suppression import Suppression
from sender.warmup import Warmup


def _load_config(args: argparse.Namespace) -> Config:
    """Загружает конфигурацию из аргумента --config или переменной окружения."""
    config_path = args.config or os.getenv("SENDER_CONFIG", "./sender.yaml")
    return Config.load(config_path, env=os.environ)


def _open_store(config: Config) -> Store:
    """Создаёт Store из db_path конфига."""
    db_path = config.get("service.db_path", "sender.db")
    return Store(db_path)


def _cmd_init_db(args: argparse.Namespace) -> int:
    """Инициализирует схему БД."""
    try:
        config = _load_config(args)
        db_path = config.get("service.db_path", "sender.db")
        store = Store(db_path)
        store.init_schema()
        print(f"Database initialized: {Path(db_path).resolve()}")
        return 0
    except (ConfigError, StoreError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_import(args: argparse.Namespace) -> int:
    """Импортирует получателей из CSV."""
    try:
        config = _load_config(args)
        store = _open_store(config)

        column_map = None
        if args.map:
            column_map = {}
            for pair in args.map.split(","):
                k, v = pair.split("=", 1)
                column_map[k.strip()] = v.strip()

        result = import_csv(
            store,
            args.csv_path,
            column_map=column_map,
            limit=args.limit,
            progress_cb=None,
        )

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ConfigError, StoreError, FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_suppress_import(args: argparse.Namespace) -> int:
    """Импортирует записи в suppress-список."""
    try:
        config = _load_config(args)
        store = _open_store(config)

        count = import_suppression(
            store, args.file_path, scope=args.scope, reason=args.reason
        )

        print(f"Imported {count} suppression entries (scope={args.scope})")
        return 0
    except (ConfigError, StoreError, FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_validate(args: argparse.Namespace) -> int:
    """Валидирует email получателей."""
    try:
        config = _load_config(args)
        store = _open_store(config)

        result = validate_recipients(
            store,
            config,
            limit=args.limit,
            only_unknown=not args.all,
            progress_cb=None,
        )

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ConfigError, StoreError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_campaign_create(args: argparse.Namespace) -> int:
    """Создаёт новую кампанию."""
    try:
        config = _load_config(args)
        store = _open_store(config)
        legal = config.legal()

        segment = (getattr(args, "segment", None) or "").strip()
        cfg = {"segment": segment} if segment else {}
        send_order = getattr(args, "send_order", None)
        if send_order:
            cfg["send_order"] = send_order
        if getattr(args, "min_priority_max", None) is not None:
            cfg["min_priority_max"] = args.min_priority_max
        campaign_in = CampaignIn(
            name=args.name,
            legal_entity=legal.entity,
            legal_inn=legal.inn,
            config=cfg,
        )

        campaign_id = store.create_campaign(campaign_in)
        tail = f" (segment={segment})" if segment else " (вся база!)"
        print(f"Campaign created: {campaign_id}{tail}")
        return 0
    except (ConfigError, StoreError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_campaign_add_step(args: argparse.Namespace) -> int:
    """Добавляет шаг в кампанию."""
    try:
        config = _load_config(args)
        store = _open_store(config)

        body_path = Path(args.body_file)
        if not body_path.exists():
            raise FileNotFoundError(f"Body file not found: {body_path}")

        body_text = body_path.read_text(encoding="utf-8")

        step_in = SequenceStepIn(
            campaign_id=args.campaign,
            step_index=args.index,
            subject_tmpl=args.subject,
            body_tmpl=body_text,
            delay_hours=args.delay_hours,
            include_legal=True,
            engagement_gate=args.gate,
        )

        step_id = store.add_step(step_in)
        print(f"Step {args.index} added to campaign {args.campaign}: step_id={step_id}")
        return 0
    except (ConfigError, StoreError, FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_campaign_activate(args: argparse.Namespace) -> int:
    """Активирует кампанию."""
    try:
        config = _load_config(args)
        store = _open_store(config)
        store.set_campaign_status(args.campaign, "active")
        print(f"Campaign {args.campaign} activated")
        return 0
    except (ConfigError, StoreError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_campaign_pause(args: argparse.Namespace) -> int:
    """Ставит кампанию на паузу."""
    try:
        config = _load_config(args)
        store = _open_store(config)
        store.set_campaign_status(args.campaign, "paused")
        print(f"Campaign {args.campaign} paused")
        return 0
    except (ConfigError, StoreError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_run(args: argparse.Namespace) -> int:
    """Запускает оркестратор рассылки."""
    try:
        config = _load_config(args)
        store = _open_store(config)

        # P2 №6: ядро графа (suppression/gates/sender/leaddesk+bitrix/warmup/
        # analytics) собирает единый композиционный корень sender.wiring —
        # тот же, что у веб-панели. Здесь остаётся только run-loop-специфика.
        from sender.wiring import build_deps
        deps = build_deps(config, store, dry_run=args.dry_run)
        suppression = deps.suppression
        gates = deps.gates
        sender = deps.sender
        warmup = deps.warmup
        analytics = deps.analytics
        cadence = Cadence(config, store, suppression)
        personalizer = Personalizer(config)

        imap_watcher = ImapWatcher(config, store, suppression, deps.leaddesk,
                                   reply_pipeline=deps.reply_pipeline)

        # Опциональный Telegram-нотификатор
        notifier = None
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if telegram_token:
            notifier = Notifier(config)

        orchestrator = Orchestrator(
            config=config,
            store=store,
            sender=sender,
            cadence=cadence,
            gates=gates,
            imap=imap_watcher,
            warmup=warmup,
            analytics=analytics,
            personalizer=personalizer,
            notifier=notifier,
            cards=deps.cards,
        )

        # Определяем активные кампании
        if args.campaigns:
            orchestrator.active_campaign_ids = [
                int(cid.strip()) for cid in args.campaigns.split(",")
            ]
        else:
            orchestrator.active_campaign_ids = config.get(
                "orchestrator.active_campaigns", []
            )

        orchestrator.bootstrap()

        if args.once:
            # Однократный тик
            result = orchestrator.tick(now=datetime.now())
            print(json.dumps(result.__dict__, default=str, ensure_ascii=False, indent=2))
            return 0
        else:
            # Бесконечный запуск
            stop_event = threading.Event()

            def signal_handler():
                print("\nStopping orchestrator...", file=sys.stderr)
                stop_event.set()

            try:
                orchestrator.run(
                    interval_sec=args.interval, dry_run=args.dry_run, stop=stop_event
                )
            except KeyboardInterrupt:
                signal_handler()

            return 0
    except (ConfigError, StoreError, SenderError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_status(args: argparse.Namespace) -> int:
    """Выводит статус ящиков и кампаний."""
    try:
        config = _load_config(args)
        store = _open_store(config)

        print("=== Mailbox Status ===")
        mailboxes = config.mailboxes()
        if not mailboxes:
            print("No mailboxes configured")
        else:
            for mb_cfg in mailboxes:
                mailbox_id = mb_cfg.mailbox_id
                state = store.get_mailbox_state(mailbox_id)
                if state:
                    paused_str = "PAUSED" if state.paused else "active"
                    print(
                        f"{mailbox_id}: {paused_str}, "
                        f"sent_today={state.sent_today}/{state.daily_limit}, "
                        f"ramp_day={state.ramp_day}"
                    )
                else:
                    print(f"{mailbox_id}: not initialized")

        print("\n=== Campaign Status ===")
        # Простой перебор известных кампаний (предполагаем ID 1..N)
        found = False
        for cid in range(1, 101):
            campaign = store.get_campaign(cid)
            if campaign:
                found = True
                print(f"Campaign {cid}: {campaign.name} [{campaign.status}]")
        if not found:
            print("No campaigns found")

        return 0
    except (ConfigError, StoreError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_pause(args: argparse.Namespace) -> int:
    """Ставит ящики на паузу."""
    try:
        config = _load_config(args)
        store = _open_store(config)

        if args.scope == "global":
            mailboxes = config.mailboxes()
            for mb_cfg in mailboxes:
                mailbox_id = mb_cfg.mailbox_id
                store.set_mailbox_paused(mailbox_id, True, args.reason)
            print(f"All {len(mailboxes)} mailboxes paused: {args.reason}")
        elif args.scope == "mailbox":
            if not args.target:
                print("Error: --target required for mailbox scope", file=sys.stderr)
                return 1
            store.set_mailbox_paused(args.target, True, args.reason)
            print(f"Mailbox {args.target} paused: {args.reason}")

        return 0
    except (ConfigError, StoreError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_resume(args: argparse.Namespace) -> int:
    """Снимает ящики с паузы."""
    try:
        config = _load_config(args)
        store = _open_store(config)

        if args.target:
            store.set_mailbox_paused(args.target, False, None)
            print(f"Mailbox {args.target} resumed")
        else:
            mailboxes = config.mailboxes()
            for mb_cfg in mailboxes:
                mailbox_id = mb_cfg.mailbox_id
                store.set_mailbox_paused(mailbox_id, False, None)
            print(f"All {len(mailboxes)} mailboxes resumed")

        return 0
    except (ConfigError, StoreError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_stats(args: argparse.Namespace) -> int:
    """Выводит статистику кампаний."""
    try:
        config = _load_config(args)
        store = _open_store(config)
        analytics = Analytics(store)

        if args.campaign:
            report = analytics.campaign_report(args.campaign)
        else:
            report = analytics.dashboard()

        if args.json:
            print(json.dumps(report, default=str, ensure_ascii=False, indent=2))
        else:
            # Читаемый вывод
            if args.campaign:
                print(f"=== Campaign {args.campaign} ===")
            else:
                print("=== Dashboard ===")

            for key, value in report.items():
                if isinstance(value, dict):
                    print(f"{key}:")
                    for k, v in value.items():
                        print(f"  {k}: {v}")
                else:
                    print(f"{key}: {value}")

        return 0
    except (ConfigError, StoreError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_user_create(args: argparse.Namespace) -> int:
    """Создать пользователя веб-панели. Пароль — из env, не из argv."""
    config = _load_config(args)
    store = _open_store(config)
    from sender.auth import Auth
    password = os.getenv(args.password_env)
    if not password:
        print(f"Error: set password in env {args.password_env}", file=sys.stderr)
        return 1
    info = Auth(store).create_user(
        username=args.username, password=password, role=args.role,
        email=args.email, enable_2fa=args.enable_2fa)
    out = {"user_id": info["user_id"], "username": info["username"], "role": info["role"]}
    if "totp_uri" in info:
        out["totp_uri"] = info["totp_uri"]  # показать один раз для привязки в приложении
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_user_rotate_2fa(args: argparse.Namespace) -> int:
    """Перевыпустить TOTP-секрет пользователя (кейс: старый секрет засветился).

    Старый секрет перестаёт действовать сразу; новый totp_uri печатается ОДИН
    раз — привязать в приложении-аутентификаторе. Факт ротации пишется в аудит.
    """
    config = _load_config(args)
    store = _open_store(config)
    from sender.auth import Auth
    user = store.get_user_by_username(args.username)
    if user is None:
        print(f"Error: user not found: {args.username}", file=sys.stderr)
        return 1
    info = Auth(store).enable_2fa(user.id)
    store.append_audit(action="user.rotate_2fa", entity_type="user",
                       entity_id=user.id, detail={"username": user.username})
    print(json.dumps({"user_id": user.id, "username": user.username,
                      "totp_uri": info["totp_uri"]}, ensure_ascii=False, indent=2))
    return 0


def _cmd_serve_api(args: argparse.Namespace) -> int:
    """Запустить HTTP API веб-панели (uvicorn).

    Без ``--static-dir`` — только API (в dev SPA раздаёт Vite). С ``--static-dir``
    (путь к ``web/dist``) — сайт+API одним процессом: API под /api, SPA статикой
    с client-side-fallback (см. ``make_site_app``). Удобно для стейджинга/смоука
    без nginx; в проде за TLS обычно ставят nginx (RUNBOOK-DEPLOY §2).
    """
    config = _load_config(args)
    store = _open_store(config)
    try:
        import uvicorn
        from sender.api.app import make_app, make_site_app, build_deps
    except ImportError as e:
        print(f"Error: API requires fastapi+uvicorn ({e})", file=sys.stderr)
        return 1
    deps = build_deps(config, store)
    static_dir = getattr(args, "static_dir", None)
    if static_dir:
        try:
            app = make_site_app(deps, static_dir)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(f"Panel site+API on http://{args.host}:{args.port} "
              f"(static: {static_dir})", file=sys.stderr)
    else:
        app = make_app(deps)
        print(f"Panel API on http://{args.host}:{args.port}", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _confirm_backend(args):
    """Общий бекенд confirm-send (Задача 4: CLI и веб зовут ОДИН модуль)."""
    from sender.wiring import build_deps
    config = _load_config(args)
    store = _open_store(config)
    store.init_schema()
    deps = build_deps(config, store)
    return deps


def _cmd_confirm_queue(args: argparse.Namespace) -> int:
    """Очередь подтверждений (список pending)."""
    from sender.confirm_cli import render_queue_text
    deps = _confirm_backend(args)
    rows = deps.confirm.pending(campaign_id=args.campaign, limit=args.limit)
    print(render_queue_text(rows, deps.confirm.counts()))
    return 0


def _cmd_confirm_show(args: argparse.Namespace) -> int:
    """Полная инфо-панель одного письма (текстовый рендер тех же JSON-полей)."""
    from sender.confirm_cli import render_panel_text
    deps = _confirm_backend(args)
    row = deps.confirm.get(args.review_id)
    if row is None:
        print(f"Error: review {args.review_id} не найден", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(row, ensure_ascii=False, indent=1, default=str))
    else:
        print(render_panel_text(row))
    return 0


def _cmd_confirm_decide(args: argparse.Namespace) -> int:
    """approve|edit|skip|stoplist — решения оператора из CLI."""
    from sender.confirm import ConfirmBlockedError
    deps = _confirm_backend(args)
    operator = args.operator or os.getenv("USER", "cli")
    try:
        if args.action == "approve":
            done = deps.confirm.approve(args.review_id, operator=operator)
        elif args.action == "edit":
            body = None
            if args.body_file:
                body = Path(args.body_file).read_text(encoding="utf-8")
            done = deps.confirm.edit(args.review_id, subject=args.subject,
                                     body=body, operator=operator)
        elif args.action == "skip":
            done = deps.confirm.skip(args.review_id, reason=args.reason or "",
                                     operator=operator)
        else:  # stoplist
            done = deps.confirm.stoplist(args.review_id,
                                         reason=args.reason or "",
                                         operator=operator)
    except ConfirmBlockedError as e:
        print(f"ЗАБЛОКИРОВАНО: {e}", file=sys.stderr)
        return 2
    if done:
        row = deps.confirm.get(args.review_id)
        print(f"#{args.review_id} -> {row['status']}"
              + (f" ({row['reason']})" if row.get("reason") else ""))
        return 0
    print(f"#{args.review_id} уже решён ранее (решение неизменно)")
    return 0


def _cmd_confirm_golden(args: argparse.Namespace) -> int:
    """Выгрузка золотых пар (правки с дифами) для калибровки промптов."""
    deps = _confirm_backend(args)
    pairs = deps.confirm.golden_pairs(limit=args.limit)
    payload = json.dumps(pairs, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"золотых пар: {len(pairs)} -> {args.out}")
    else:
        print(payload)
    return 0


def _cmd_confirm_run(args: argparse.Namespace) -> int:
    """Интерактивная калибровка: панель → клавиша → следующее письмо.

    [Enter] отправить, [e] править (тема/тело через $EDITOR-файл не городим —
    правка через confirm-decide edit --body-file), [s] скип, [x] стоп-лист,
    [q] выход. Идентичный результат даёт веб-экран (Задача 4).
    """
    from sender.confirm import ConfirmBlockedError
    from sender.confirm_cli import render_panel_text
    deps = _confirm_backend(args)
    operator = args.operator or os.getenv("USER", "cli")
    done_n = 0
    while True:
        rows = deps.confirm.pending(campaign_id=args.campaign, limit=1)
        if not rows:
            print(f"Очередь пуста. Решено за сессию: {done_n}")
            return 0
        row = rows[0]
        print("\n" + render_panel_text(row))
        try:
            key = input("[Enter/e/s/x/q] > ").strip().lower()
        except EOFError:
            return 0
        try:
            if key == "":
                if (row.get("panel") or {}).get("stop_flags"):
                    ok = input("  Есть стоп-флаги! Отправить всё равно? "
                               "[yes/N] > ").strip().lower()
                    if ok != "yes":
                        continue
                deps.confirm.approve(row["id"], operator=operator)
                print(f"  #{row['id']} approved")
            elif key == "e":
                print("  правка: sender confirm-decide edit "
                      f"{row['id']} --body-file изменённое.txt")
                continue
            elif key == "s":
                reason = input("  причина скипа > ").strip() or "оператор"
                deps.confirm.skip(row["id"], reason=reason, operator=operator)
                print(f"  #{row['id']} skipped")
            elif key == "x":
                reason = input("  причина (конкурент/нерелевант/плохие данные/"
                               "по запросу) > ").strip()
                deps.confirm.stoplist(row["id"], reason=reason,
                                      operator=operator)
                print(f"  #{row['id']} stoplist")
            elif key == "q":
                print(f"Выход. Решено за сессию: {done_n}")
                return 0
            else:
                continue
            done_n += 1
        except (ConfirmBlockedError, SenderError) as e:
            print(f"  ОТКАЗ: {e}", file=sys.stderr)


def main(argv: Optional[list[str]] = None) -> int:
    """Основная точка входа CLI."""
    parser = argparse.ArgumentParser(
        prog="sender",
        description="CLI сервиса рассылки",
    )
    parser.add_argument(
        "--config",
        help="Путь к конфигурации (default: $SENDER_CONFIG или ./sender.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-db
    subparsers.add_parser("init-db", help="Инициализировать БД")

    # import
    p_import = subparsers.add_parser("import", help="Импортировать получателей из CSV")
    p_import.add_argument("csv_path", help="Путь к CSV-файлу")
    p_import.add_argument("--limit", type=int, help="Лимит строк")
    p_import.add_argument(
        "--map", help="Маппинг колонок (email=Col1,inn=Col2,...)"
    )

    # suppress-import
    p_suppress = subparsers.add_parser(
        "suppress-import", help="Импортировать suppress-список"
    )
    p_suppress.add_argument("file_path", help="Путь к файлу")
    p_suppress.add_argument(
        "--scope", required=True, choices=["inn", "domain"], help="Тип записей"
    )
    p_suppress.add_argument(
        "--reason", default="competitor", help="Причина подавления"
    )

    # validate
    p_validate = subparsers.add_parser("validate", help="Валидировать email")
    p_validate.add_argument("--limit", type=int, help="Лимит получателей")
    p_validate.add_argument(
        "--all", action="store_true", help="Валидировать все, не только unknown"
    )

    # campaign-create
    p_create = subparsers.add_parser("campaign-create", help="Создать кампанию")
    p_create.add_argument("--name", required=True, help="Название кампании")
    p_create.add_argument(
        "--segment",
        help="Целевой сегмент базы (например кц/meyer); без него — ВСЯ база",
    )
    p_create.add_argument(
        "--send-order", choices=["pilot_asc", "priority_desc"], dest="send_order",
        help="Порядок отправки по PxR: pilot_asc (обкатка, малые первыми) | "
             "priority_desc (боевая, приоритетные первыми); без него — по id",
    )
    p_create.add_argument(
        "--min-priority-max", type=int, dest="min_priority_max",
        help="Порог «Макс. балл по связке»: получатели с баллом ниже не планируются",
    )

    # campaign-add-step
    p_step = subparsers.add_parser("campaign-add-step", help="Добавить шаг в кампанию")
    p_step.add_argument("--campaign", type=int, required=True, help="ID кампании")
    p_step.add_argument("--index", type=int, required=True, help="Индекс шага")
    p_step.add_argument("--subject", required=True, help="Тема письма")
    p_step.add_argument("--body-file", required=True, help="Путь к файлу с телом")
    p_step.add_argument("--delay-hours", type=int, default=0, help="Задержка в часах")
    p_step.add_argument(
        "--gate",
        default="all",
        choices=["all", "not_bounced", "engaged"],
        help="Условие гейта",
    )

    # campaign-activate
    p_activate = subparsers.add_parser("campaign-activate", help="Активировать кампанию")
    p_activate.add_argument("--campaign", type=int, required=True, help="ID кампании")

    # campaign-pause
    p_pause_c = subparsers.add_parser("campaign-pause", help="Остановить кампанию")
    p_pause_c.add_argument("--campaign", type=int, required=True, help="ID кампании")

    # run
    p_run = subparsers.add_parser("run", help="Запустить оркестратор")
    p_run.add_argument(
        "--interval", type=int, default=60, help="Интервал между тиками (сек)"
    )
    p_run.add_argument("--dry-run", action="store_true", help="Режим dry-run")
    p_run.add_argument("--once", action="store_true", help="Выполнить один тик")
    p_run.add_argument("--campaigns", help="Список ID кампаний через запятую")

    # status
    subparsers.add_parser("status", help="Показать статус ящиков и кампаний")

    # pause
    p_pause = subparsers.add_parser("pause", help="Поставить на паузу")
    p_pause.add_argument(
        "--scope",
        required=True,
        choices=["global", "mailbox"],
        help="Область паузы",
    )
    p_pause.add_argument("--target", help="Целевой mailbox_id (для scope=mailbox)")
    p_pause.add_argument("--reason", required=True, help="Причина паузы")

    # resume
    p_resume = subparsers.add_parser("resume", help="Снять с паузы")
    p_resume.add_argument(
        "--target", help="Целевой mailbox_id (если не указан — все)"
    )

    # stats
    p_stats = subparsers.add_parser("stats", help="Показать статистику")
    p_stats.add_argument("--campaign", type=int, help="ID кампании")
    p_stats.add_argument("--json", action="store_true", help="Вывод в JSON")

    # user-create (bootstrap первого owner для веб-панели)
    p_user = subparsers.add_parser("user-create", help="Создать пользователя панели")
    p_user.add_argument("--username", required=True)
    p_user.add_argument("--password-env", default="SENDER_NEW_USER_PASSWORD",
                        help="env-переменная с паролем (не в командной строке)")
    p_user.add_argument("--role", choices=["owner", "manager"], default="manager")
    p_user.add_argument("--email")
    p_user.add_argument("--enable-2fa", action="store_true")

    # user-rotate-2fa (перевыпуск TOTP-секрета, печатает новый totp_uri)
    p_rot = subparsers.add_parser(
        "user-rotate-2fa", help="Перевыпустить TOTP-секрет пользователя")
    p_rot.add_argument("--username", required=True)

    # confirm-* (режим «подтвердить отправку», Задачи 1/4)
    p_cq = subparsers.add_parser("confirm-queue", help="Очередь подтверждений")
    p_cq.add_argument("--campaign", type=int, help="Фильтр по кампании")
    p_cq.add_argument("--limit", type=int, default=50)

    p_cs = subparsers.add_parser("confirm-show",
                                 help="Инфо-панель письма (текст или --json)")
    p_cs.add_argument("review_id", type=int)
    p_cs.add_argument("--json", action="store_true",
                      help="Сырой JSON (те же поля, что рендерит веб)")

    p_cd = subparsers.add_parser("confirm-decide", help="Решение оператора")
    p_cd.add_argument("action", choices=["approve", "edit", "skip", "stoplist"])
    p_cd.add_argument("review_id", type=int)
    p_cd.add_argument("--subject", help="Новая тема (edit)")
    p_cd.add_argument("--body-file", help="Файл с новым телом (edit)")
    p_cd.add_argument("--reason", help="Причина (skip/stoplist)")
    p_cd.add_argument("--operator", help="Имя оператора (default: $USER)")

    p_cg = subparsers.add_parser("confirm-golden",
                                 help="Выгрузить золотые пары правок (дифы)")
    p_cg.add_argument("--out", help="Файл вывода (default: stdout)")
    p_cg.add_argument("--limit", type=int, default=500)

    p_cr = subparsers.add_parser("confirm-run",
                                 help="Интерактивная калибровка очереди")
    p_cr.add_argument("--campaign", type=int, help="Фильтр по кампании")
    p_cr.add_argument("--operator", help="Имя оператора (default: $USER)")

    # serve-api (веб-панель, Фаза 2.1)
    p_api = subparsers.add_parser("serve-api", help="Запустить HTTP API веб-панели")
    p_api.add_argument("--host", default="127.0.0.1")
    p_api.add_argument("--port", type=int, default=8090)
    p_api.add_argument(
        "--static-dir",
        help="Путь к собранному SPA (web/dist) — раздавать сайт+API одним процессом",
    )

    args = parser.parse_args(argv)

    commands = {
        "init-db": _cmd_init_db,
        "import": _cmd_import,
        "suppress-import": _cmd_suppress_import,
        "validate": _cmd_validate,
        "campaign-create": _cmd_campaign_create,
        "campaign-add-step": _cmd_campaign_add_step,
        "campaign-activate": _cmd_campaign_activate,
        "campaign-pause": _cmd_campaign_pause,
        "run": _cmd_run,
        "status": _cmd_status,
        "pause": _cmd_pause,
        "resume": _cmd_resume,
        "stats": _cmd_stats,
        "user-create": _cmd_user_create,
        "user-rotate-2fa": _cmd_user_rotate_2fa,
        "confirm-queue": _cmd_confirm_queue,
        "confirm-show": _cmd_confirm_show,
        "confirm-decide": _cmd_confirm_decide,
        "confirm-golden": _cmd_confirm_golden,
        "confirm-run": _cmd_confirm_run,
        "serve-api": _cmd_serve_api,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            return handler(args)
        except KeyboardInterrupt:
            print("\nInterrupted", file=sys.stderr)
            return 130
        except Exception as e:  # noqa: BLE001
            # Идентичности исключений в дереве разные (config/store/importer
            # держат свои классы) — CLI последний рубеж: человеческое сообщение,
            # код 1, никаких трейсбеков наружу.
            print(f"Error: {e}", file=sys.stderr)
            return 1

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1
