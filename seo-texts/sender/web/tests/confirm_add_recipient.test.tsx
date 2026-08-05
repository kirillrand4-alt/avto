// Форма «новый адрес» на экране «Подтвердить отправку».
//
// Проверяем то, что важно оператору и юристу, а не вёрстку:
//   * кнопка «добавить» шлёт адрес В ОТДЕЛЬНУЮ ручку /recipient/add — не в
//     старую /recipient (та закрыта allow-листом контактов карточки);
//   * до символа «@» кнопка неактивна: опечатка в адресе = hard bounce, а он
//     двигает kill-switch;
//   * отказ бэкенда (409 «чужая компания» / «стоп-лист») показывается ПРИЧИНОЙ,
//     а не «ошибка сервера», и адрес карточки при этом не меняется.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, fireEvent, waitFor, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "../src/components/Toast";
import { Confirm } from "../src/screens/Confirm";
import { setTokenGetter } from "../src/api/client";

const pendingRow = {
  id: 7,
  email: "office@zavod.ru",
  subject: "вопрос по компрессору",
  body: "Добрый день!",
  inn: "4201000625",
  campaign_id: 1,
  status: "pending",
  panel: { emails: [{ email: "office@zavod.ru", role: "приёмная" }] },
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

function setup(addResponse: () => Response, calls: unknown[]) {
  setTokenGetter(() => "tok");
  vi.stubGlobal("fetch", vi.fn(async (url: string, opts?: RequestInit) => {
    const u = String(url);
    if (u.includes("/confirm/queue")) {
      return jsonRes(200, { pending: [pendingRow], counts: { pending: 1 },
                            live: true });
    }
    if (u.includes("/confirm/7/recipient/add")) {
      calls.push({ url: u, body: JSON.parse(String(opts?.body || "{}")) });
      return addResponse();
    }
    if (u.includes("/confirm/7/recipient")) {
      calls.push({ url: u, body: JSON.parse(String(opts?.body || "{}")) });
      return jsonRes(200, { ok: true, review: pendingRow });
    }
    return jsonRes(200, {});
  }));
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
}

describe("Confirm: добавление нового контакта компании", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("шлёт адрес в /recipient/add, а не в старую ручку", async () => {
    const calls: any[] = [];
    setup(() => jsonRes(200, { ok: true, created_recipient: true,
                               review: { ...pendingRow, email: "snab@zavod.ru" } }),
          calls);

    const input = await screen.findByPlaceholderText("name@company.ru");
    const btn = screen.getByRole("button", { name: "добавить" });
    expect(btn).toBeDisabled();                     // пусто — нельзя

    fireEvent.change(input, { target: { value: "snab" } });
    expect(btn).toBeDisabled();                     // без «@» — нельзя

    fireEvent.change(input, { target: { value: "snab@zavod.ru" } });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);

    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].url).toContain("/confirm/7/recipient/add");
    expect(calls[0].body).toMatchObject({ email: "snab@zavod.ru" });
  });

  it("409 от бэкенда показывается причиной, адрес карточки не меняется", async () => {
    const calls: any[] = [];
    setup(() => jsonRes(409, {
      detail: "адрес dir@sosed.ru уже закреплён за ИНН 5024002119",
    }), calls);

    const input = await screen.findByPlaceholderText("name@company.ru");
    fireEvent.change(input, { target: { value: "dir@sosed.ru" } });
    fireEvent.click(screen.getByRole("button", { name: "добавить" }));

    await waitFor(() => expect(calls.length).toBe(1));
    expect(await screen.findByText(/уже закреплён за ИНН 5024002119/)).toBeTruthy();
    // карточка осталась на прежнем адресе — подмены «на всякий случай» нет
    expect((input as HTMLInputElement).value).toBe("dir@sosed.ru");
    expect(screen.getByDisplayValue("office@zavod.ru")).toBeTruthy();
  });
});
