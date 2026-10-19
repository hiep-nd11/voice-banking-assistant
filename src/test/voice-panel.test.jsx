import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import VoicePanel from "../components/VoicePanel.jsx";

const original = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
afterEach(() => {
  if (original) Object.defineProperty(navigator, "mediaDevices", original);
  else delete navigator.mediaDevices;
});

function mockMicrophone(getUserMedia) {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia },
  });
}

it("opens the microphone, stops it, and releases it when closed", async () => {
  const user = userEvent.setup();
  const stop = vi.fn();
  const getUserMedia = vi
    .fn()
    .mockResolvedValue({ getTracks: () => [{ stop }] });
  mockMicrophone(getUserMedia);
  const { unmount } = render(<VoicePanel close={() => {}} />);
  await user.click(screen.getByRole("button", { name: /Bắt đầu nói/ }));
  expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
  expect(screen.getByRole("status").textContent).toContain("Micro đang bật");
  await user.click(screen.getByRole("button", { name: /Dừng nói/ }));
  expect(stop).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: /Bắt đầu nói/ }));
  unmount();
  expect(stop).toHaveBeenCalledTimes(2);
});

it("releases microphone access granted after closing the panel", async () => {
  const user = userEvent.setup();
  const stop = vi.fn();
  let grant;
  mockMicrophone(
    () =>
      new Promise((resolve) => {
        grant = resolve;
      }),
  );
  const { unmount } = render(<VoicePanel close={() => {}} />);
  await user.click(screen.getByRole("button", { name: /Bắt đầu nói/ }));
  unmount();
  await act(async () => grant({ getTracks: () => [{ stop }] }));
  expect(stop).toHaveBeenCalledOnce();
});
