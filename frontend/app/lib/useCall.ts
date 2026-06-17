"use client";

import { useEffect, useState } from "react";

import { watchUrl } from "./backend";

export type Msg = {
  role: "user" | "assistant" | "system";
  text: string;
  kind?: "connected" | "declined" | "ended" | "interrupted"; // system lines carry an icon hint
};

export type EndReason = "limit" | "remote"; // 2-min cap vs caller hung up

export type CallEvents = {
  state: string; // calling | connected | listening | thinking | speaking | declined | hangup | ended
  messages: Msg[];
  level: number; // live caller mic level 0..1 (during listening)
  ended: boolean;
  endReason: EndReason | null;
  declined: boolean; // callee never picked up
};

// One place that owns the /watch socket for a call. Both the on-screen
// transcript (left) and the phone's waveform read from this, so they stay in
// lockstep off a single connection. The events here are exactly what
// transcript_socket.push() fans out from the call's worker thread.
export function useCall(callSid: string | null): CallEvents {
  const [state, setState] = useState("calling");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [level, setLevel] = useState(0);
  const [ended, setEnded] = useState(false);
  const [endReason, setEndReason] = useState<EndReason | null>(null);
  const [declined, setDeclined] = useState(false);

  useEffect(() => {
    if (!callSid) return;
    // Fresh call -> fresh slate (the hook instance is reused across calls).
    setState("calling");
    setMessages([]);
    setLevel(0);
    setEnded(false);
    setEndReason(null);
    setDeclined(false);

    const ws = new WebSocket(watchUrl(callSid));

    // Append the one-shot "call ended" system line, then flag the end.
    const endCall = (reason: EndReason) => {
      setEndReason(reason);
      setEnded(true);
      setMessages((m) =>
        m.some((x) => x.kind === "ended")
          ? m
          : [...m, { role: "system", text: "Call ended", kind: "ended" }],
      );
    };

    ws.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.event === "state") {
        setState(ev.value);
        if (ev.value === "connected") {
          // One system line when the callee picks up.
          setMessages((m) =>
            m.some((x) => x.kind === "connected")
              ? m
              : [...m, { role: "system", text: "Call connected", kind: "connected" }],
          );
        } else if (ev.value === "declined") {
          setDeclined(true);
          setMessages((m) =>
            m.some((x) => x.kind === "declined")
              ? m
              : [...m, { role: "system", text: "Call declined", kind: "declined" }],
          );
        } else if (ev.value === "ended") {
          endCall("limit");
        } else if (ev.value === "hangup") {
          endCall("remote");
        }
      } else if (ev.event === "user_transcript") {
        setMessages((m) => [...m, { role: "user", text: ev.text }]);
      } else if (ev.event === "assistant_sentence") {
        setMessages((m) => [...m, { role: "assistant", text: ev.text }]);
      } else if (ev.event === "interrupted") {
        // Caller cut in mid-reply — mark the bot's half-spoken line as cut off.
        setMessages((m) => [...m, { role: "system", text: "interrupted", kind: "interrupted" }]);
      } else if (ev.event === "level") {
        // Live caller loudness -> waveform amplitude.
        setLevel(ev.value);
      }
    };

    return () => ws.close();
  }, [callSid]);

  return { state, messages, level, ended, endReason, declined };
}
