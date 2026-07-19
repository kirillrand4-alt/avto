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

        campaign_in = CampaignIn(
            name=args.name,
            legal_entity=legal.entity,
            legal_inn=legal.inn,
        )

        campaign_id = store.create_campaign(campaign_in)
        print(f"Campaign created: {campaign_id}")
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

        suppression = Suppression(store)
        gates = Gates(config, store)
        sender = Sender(config, store, suppression, gates, dry_run=args.dry_run)
        cadence = Cadence(config, store, suppression)
        personalizer = Personalizer(config)
        warmup = Warmup(config, store, sender)
        analytics = Analytics(store)

        # reply-desk: тёплый ответ → своя очередь лидов (LeadDesk), опционально
        # с дальнейшим пробросом в Bitrix (если задан вебхук). LeadDesk — своя
        # очередь с назначением/SLA; Bitrix — внешняя CRM поверх неё.
        from sender.leaddesk import LeadDesk
        bitrix_sink = None
        if os.getenv("BITRIX_WEBHOOK_URL"):
            from sender.bitrix import BitrixSink
            bitrix_sink = BitrixSink(config, store)
        reply_desk = LeadDesk(config, store, bitrix_sink=bitrix_sink)

        imap_watcher = ImapWatcher(config, store, suppression, reply_desk)

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
                mailbox_id = mb_cfg.email
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
                mailbox_id = mb_cfg.email
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
                mailbox_id = mb_cfg.email
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


def _cmd_serve_api(args: argparse.Namespace) -> int:
    """Запустить HTTP API веб-панели (uvicorn)."""
    config = _load_config(args)
    store = _open_store(config)
    try:
        import uvicorn
        from sender.api.app import make_app, build_deps
    except ImportError as e:
        print(f"Error: API requires fastapi+uvicorn ({e})", file=sys.stderr)
        return 1
    app = make_app(build_deps(config, store))
    print(f"Panel API on http://{args.host}:{args.port}", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


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

    # serve-api (веб-панель, Фаза 2.1)
    p_api = subparsers.add_parser("serve-api", help="Запустить HTTP API веб-панели")
    p_api.add_argument("--host", default="127.0.0.1")
    p_api.add_argument("--port", type=int, default=8090)

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
