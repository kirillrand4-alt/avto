import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { api, ApiError, setTokenGetter } from "../src/api/client";

// Мокаем fetch — проверяем, что клиент шлёт правильные роуты/заголовки и
// корректно разбирает 409/400 (CAS-конфликт «Взять»).

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  setTokenGetter(() => "tok123");
});
afterEach(() => vi.restoreAllMocks());

function jsonRes(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    text: async () => JSON.stringify(body),
  } as Response;
}

describe("api client", () => {
  it("шлёт Bearer и правильный роут login", async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(200, { token: "T" }));
    const r = await api.login("kirill", "secret");
    expect(r.token).toBe("T");
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/login");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ username: "kirill", password: "secret", totp_code: undefined });
  });

  it("строит query-параметры /leads", async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(200, { leads: [], stats: {} }));
    await api.leads({ status: "new", reply_kind: "hot", limit: 50 });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/leads?status=new&reply_kind=hot&limit=50");
  });

  it("take → 409 бросает ApiError(409) (истинная гонка CAS)", async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(409, { detail: "lead already taken" }));
    await expect(api.takeLead(5)).rejects.toMatchObject({ status: 409 });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/leads/5/take");
  });

  it("take → 400 (уже taken) тоже ApiError с detail", async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(400, { detail: "lead 5 not takeable in status taken" }));
    const err = await api.takeLead(5).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.detail).toContain("not takeable");
  });

  it("401 бросает ApiError(401)", async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(401, { detail: "not authenticated" }));
    await expect(api.me()).rejects.toMatchObject({ status: 401 });
  });

  it("DELETE suppression с reason в query", async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(200, { ok: true }));
    await api.removeSuppression(9, "operator removal");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/suppression/9?reason=operator+removal");
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
  });
});
