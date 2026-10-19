import { afterEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import base from "../../public/app-config.json";
import { config, configureApp, loadAppConfig } from "../lib/config.js";

afterEach(() => {
  configureApp(structuredClone(base));
  vi.unstubAllGlobals();
});

it("loads config at runtime without caching", async () => {
  const custom = structuredClone(base);
  custom.user.name = "CONFIG USER";
  const fetch = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => custom });
  vi.stubGlobal("fetch", fetch);
  await loadAppConfig();
  expect(fetch).toHaveBeenCalledWith("/app-config.json", { cache: "no-store" });
  expect(config.user.name).toBe("CONFIG USER");
});

it("uses configured profile, balance, account and history throughout the UI", async () => {
  const custom = structuredClone(base);
  custom.user = {
    id: "another-user",
    name: "CUSTOM PROFILE",
    bank: "MB Bank",
    account: "123400005678",
    balance: 7654321,
  };
  custom.transactions = [
    { name: "CONFIG TRANSACTION", date: "Demo date", amt: 12345 },
  ];
  configureApp(custom);
  const { default: App } = await import("../App.jsx");
  render(<App />);
  expect(screen.getByText(/CUSTOM PROFILE/)).toBeTruthy();
  expect(screen.getByText("7.654.321 ₫")).toBeTruthy();
  expect(screen.getByText("MB Bank · 1234 •••• 5678")).toBeTruthy();
  expect(screen.getByText("CONFIG TRANSACTION")).toBeTruthy();
});

it("reports configuration load failures", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
  await expect(loadAppConfig()).rejects.toThrow("HTTP 404");
});

it.each(["user", "banks", "transfer"])("rejects missing section %s", (key) => {
  const value = structuredClone(base);
  delete value[key];
  expect(() => configureApp(value)).toThrow("Cấu hình không hợp lệ");
});
