import { afterEach, expect, it, vi } from "vitest";
import { streamAssistant } from "../lib/api.js";

afterEach(() => vi.unstubAllGlobals());
function respond(text, split = 7) {
  const bytes = new TextEncoder().encode(text);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      body: new ReadableStream({
        start(controller) {
          for (let i = 0; i < bytes.length; i += split)
            controller.enqueue(bytes.slice(i, i + split));
          controller.close();
        },
      }),
    })),
  );
}
it("parses fragmented SSE, Vietnamese UTF8, comments and session completion", async () => {
  respond(
    ': ping\r\n\r\nevent: token\r\ndata: {"type":"token","content":"Xin chào"}\r\n\r\ndata: {"type":"done","session_id":"s1"}\r\n\r\n',
  );
  const onEvent = vi.fn();
  await streamAssistant({ message: "hello", onEvent });
  expect(onEvent.mock.calls.map(([e]) => e.type)).toEqual(["token", "done"]);
  expect(onEvent.mock.calls[0][0].content).toBe("Xin chào");
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({
    message: "hello",
    customer_id: 2,
  });
});
it("sends WAV multipart with the session and handles backend errors", async () => {
  respond('data: {"type":"error","message":"ASR failed"}\n\n');
  await expect(
    streamAssistant({ audio: new Blob(["wav"]), sessionId: "s1", onEvent: vi.fn() }),
  ).rejects.toThrow("ASR failed");
  const body = fetch.mock.calls[0][1].body;
  expect(body.get("audio").name).toBe("recording.wav");
  expect(body.get("session_id")).toBe("s1");
});
it("reports a truncated stream", async () => {
  respond('data: {"type":"token","content":"partial"}\n\n');
  await expect(streamAssistant({ message: "hi", onEvent: vi.fn() })).rejects.toThrow(
    "Kết nối bị ngắt",
  );
});

it("sends the current quick transfer list for both chat and microphone requests, including an empty list", async () => {
  const quickRecipients = [
    { bank: "MB Bank", account: "123456789", recipient: "LE MINH", nickname: "Minh" },
  ];
  respond('data: {"type":"done","session_id":"s1"}\n\n');
  await streamAssistant({ message: "chuyển tiền cho Minh 5tr", quickRecipients, onEvent: vi.fn() });
  expect(JSON.parse(fetch.mock.calls[0][1].body).quick_recipients).toEqual(quickRecipients);
  respond('data: {"type":"done","session_id":"s1"}\n\n');
  await streamAssistant({ audio: new Blob(["wav"]), quickRecipients: [], onEvent: vi.fn() });
  expect(JSON.parse(fetch.mock.calls[0][1].body.get("quick_recipients"))).toEqual([]);
});

it("shows FastAPI validation details as readable text", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: false,
      status: 422,
      json: async () => ({ detail: [{ msg: "Field required" }] }),
    })),
  );
  await expect(streamAssistant({ message: "hi", onEvent: vi.fn() })).rejects.toThrow(
    "Field required",
  );
});
