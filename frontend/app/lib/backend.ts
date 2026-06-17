// The browser's link to the FastAPI backend: place a call, then derive the
// WebSocket URL it watches that call's events on.
//
// Local dev defaults to localhost:8000 (browser and backend on the same
// machine). Twilio reaches the backend through ngrok; the BROWSER does not —
// it talks to the backend directly, so this stays the local origin. Override
// with NEXT_PUBLIC_BACKEND_URL when the backend lives elsewhere.
export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

// POST /call {to, persona} -> the Twilio call SID. `to` is the number the bot
// dials (the user's own number — "call me"); persona picks the character.
export async function placeCall(to: string, persona: string): Promise<string> {
  const res = await fetch(`${BACKEND_URL}/call`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to, persona }),
  });
  if (!res.ok) throw new Error(`call failed: ${res.status}`);
  const data = await res.json();
  return data.call_sid as string;
}

// POST /hangup/{callSid} — actually end the live Twilio call (the in-app red
// button). Fire-and-forget: the UI closes regardless, this just makes sure the
// real phone call drops too instead of staying up.
export async function hangupCall(callSid: string): Promise<void> {
  try {
    await fetch(`${BACKEND_URL}/hangup/${callSid}`, { method: "POST" });
  } catch {
    // Best-effort; the call also has a carrier-side time cap as a backstop.
  }
}

// POST /feedback — a post-call remark. `may_feature` is the visitor's consent to
// be quoted; the owner still picks which entries actually get showcased.
export type FeedbackPayload = {
  text: string;
  name?: string;
  rating?: number;
  may_feature?: boolean;
};
export async function submitFeedback(fb: FeedbackPayload): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fb),
  });
  if (!res.ok) throw new Error(`feedback failed: ${res.status}`);
}

// ws(s)://.../watch/{callSid} — same origin as the API, http -> ws. The screen
// opens this right after placeCall and listens for state/transcript events.
export function watchUrl(callSid: string): string {
  const base = BACKEND_URL.replace(/^http/, "ws");
  return `${base}/watch/${callSid}`;
}
