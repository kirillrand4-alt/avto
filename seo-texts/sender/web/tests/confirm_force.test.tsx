// Ревью #48: force («обход всех заслонов») НЕ шлётся вслепую первым кликом.
//
// До фикса: при любых стоп-флагах карточки (включая ЖЁЛТЫЙ «вне базы,
// отправка разрешена тумблером») кнопка «Отправить» после одного диалога слала
// force=true — а force на бэке снимает ВСЕ заслоны разом, в том числе отписку,
// появившуюся ПОСЛЕ постановки письма в очередь, о которой оператор не знал.
// Теперь первый запрос всегда force=false; если заслон реально действует,
// бэкенд отвечает 409 с настоящей причиной, и только диалог с ЭТОЙ причиной
// (второе подтверждение) повторяет запрос с force=true.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, fireEvent, waitFor, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "../src/components/Toast";
import { Confirm } from "../src/screens/Confirm";
import { setTokenGetter } from "../src/api/client";

const pendingRow = {
  id: 5,
  email: "lead@zavod.ru",
  subject: "вопрос по азоту",
  body: "Добрый день!\n\nС уважением,",
  inn: "4201000625",
  campaign_id: 1,
  status: "pending",
  // жёлтый флаг «вне базы» ставит confirm_hold, но НЕ является блоком
  panel: {
    actions: { confirm_hold: true },
    stop_flags: [{ code: "out_of_base_allowed", severity: "yellow",
                   label: "ИНН вне базы обзвона — отправка РАЗРЕШЕНА тумблером" }],
  },
  send_as: { mailbox_id: "box1@rusprom.ru", from_name: "", email: "",
             source: "подбор", options: [] },
  sent: { ever: false, last_ts: null, replied: false, within_90d: false },
};

function jsonRes(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    text: async () => JSON.stringify(body),
  } as Response;
}

describe("Confirm: force только после 409 с настоящей причиной", () => {
  const decisions: Array<{ force?: boolean; action: string }> = [];
  const confirmSpy = vi.fn((..._args: unknown[]) => true);

  beforeEach(() => {
    decisions.length = 0;
    confirmSpy.mockClear();
    setTokenGetter(() => "tok");
    vi.stubGlobal("confirm", confirmSpy);
    vi.stubGlobal("fetch", vi.fn(async (url: string, opts?: RequestInit) => {
      const u = String(url);
      if (u.includes("/confirm/queue")) {
        return jsonRes(200, { pending: [pendingRow],
                              counts: { pending: 1 }, live: true });
      }
      if (u.includes("/confirm/5/decision")) {
        const body = JSON.parse(String(opts?.body || "{}"));
        decisions.push(body);
        if (decisions.length === 1) {
          // заслон, появившийся ПОСЛЕ постановки в очередь
          return jsonRes(409, {
            detail: "отправка запрещена (suppressed:unsubscribe) — письмо остаётся на решении",
          });
        }
        return jsonRes(200, { ok: true, decided: true, review: pendingRow });
      }
      return jsonRes(200, {});
    }));
  });

  it("первый клик шлёт force=false; после 409 диалог показывает причину и шлёт force=true", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <ToastProvider>
        <QueryClientProvider client={qc}>
          <Confirm />
        </QueryClientProvider>
      </ToastProvider>,
    );

    const btn = await screen.findByRole("button", { name: /Отправить/ });
    fireEvent.click(btn);

    await waitFor(() => expect(decisions.length).toBe(2));
    // ДО ФИКСА здесь force=true уже на первом запросе (красный тест):
    // жёлтый флаг карточки превращался в слепой обход всех заслонов.
    expect(decisions[0]).toMatchObject({ action: "approve", force: false });
    // второе подтверждение — с НАСТОЯЩЕЙ причиной из 409, не с флагами карточки
    const escalation = confirmSpy.mock.calls
      .map((c) => String(c[0] ?? ""))
      .find((t) => t.includes("suppressed:unsubscribe"));
    expect(escalation).toBeTruthy();
    expect(decisions[1]).toMatchObject({ action: "approve", force: true });
  });
});
