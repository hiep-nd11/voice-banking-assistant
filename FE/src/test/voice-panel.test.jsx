import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import VoicePanel from "../components/VoicePanel.jsx";
vi.mock("../lib/audio.js", () => ({ captureAudio: vi.fn(async () => vi.fn()) }));

const original = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  if (original) Object.defineProperty(navigator, "mediaDevices", original);
  else delete navigator.mediaDevices;
});

it("renders a backend SSE reply and restores its session when reopened", async () => {
  sessionStorage.clear();
  const body = new TextEncoder().encode(
    'event: token\r\ndata: {"type":"token","content":"Xin chào từ BE"}\r\n\r\nevent: done\r\ndata: {"type":"done","session_id":"integration-session"}\r\n\r\n',
  );
  const fetchMock = vi.fn(async () => ({
    ok: true,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(body);
        controller.close();
      },
    }),
  }));
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  const { unmount } = render(<VoicePanel close={() => {}} />);
  await user.type(screen.getByLabelText("Tin nhắn cho trợ lý"), "Chào backend");
  await user.click(screen.getByRole("button", { name: "Gửi" }));
  expect(await screen.findByText("Xin chào từ BE")).toBeTruthy();
  expect(fetchMock.mock.calls[0][0]).toBe("/api/chat");
  expect(sessionStorage.getItem("vtb.assistant.session")).toBe("integration-session");
  unmount();
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({
      messages: [
        { role: "user", content: "Chào backend" },
        { role: "assistant", content: "Lịch sử từ BE" },
      ],
    }),
  });
  render(<VoicePanel close={() => {}} />);
  expect(await screen.findByText("Lịch sử từ BE")).toBeTruthy();
  expect(fetchMock.mock.calls[1][0]).toBe("/api/sessions/integration-session/messages");
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
  const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] });
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

it("plays each reply once while collapsed without replaying when reopened", () => {
  const play = vi.fn().mockResolvedValue();
  const pause = vi.fn();
  const AudioMock = vi.fn(function () {
    this.play = play;
    this.pause = pause;
  });
  vi.stubGlobal("Audio", AudioMock);
  const reply = { id: "reply-1", audio: { format: "audio/wav", data: "AAAA" } };
  const { rerender, unmount } = render(
    <VoicePanel close={() => {}} collapsed externalReply={reply} />,
  );
  expect(play).toHaveBeenCalledTimes(1);
  expect(AudioMock).toHaveBeenCalledWith("data:audio/wav;base64,AAAA");
  rerender(<VoicePanel close={() => {}} externalReply={{ ...reply }} />);
  rerender(<VoicePanel close={() => {}} collapsed externalReply={{ ...reply }} />);
  expect(play).toHaveBeenCalledTimes(1);
  rerender(<VoicePanel close={() => {}} collapsed externalReply={{ ...reply, id: "reply-2" }} />);
  expect(play).toHaveBeenCalledTimes(2);
  unmount();
  expect(pause).toHaveBeenCalledTimes(2);
});
