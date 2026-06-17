"use client";

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import type { Msg } from "./lib/useCall";

// ── Streaming text ────────────────────────────────────────────────────────
// Reveals its text character-by-character on mount, so each new line types
// itself out instead of popping in whole. New messages are fresh elements, so
// only the newest one animates; earlier ones stay fully shown.
function StreamingText({ text }: { text: string }) {
  const [shown, setShown] = useState("");
  useEffect(() => {
    let i = 0;
    const id = setInterval(() => {
      i++;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, 18);
    return () => clearInterval(id);
  }, [text]);
  return <>{shown}</>;
}

// ── Transcript ────────────────────────────────────────────────────────────
// Outside the phone, left of the stage. Plain text, no bubbles, anchored to the
// bottom: newest at the bottom, older gently fading upward. All lines are
// left-aligned; the speaker is clear from the FONT — the user in DM Sans, the
// bot in Instrument Serif, which types itself out.
export function Transcript({ messages }: { messages: Msg[] }) {
  const n = messages.length;
  return (
    <div
      style={{
        height: "600px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-end",
        overflow: "hidden",
        padding: "0 10px",
        width: "100%",
      }}
    >
      {messages.map((m, i) => {
        const fromBottom = n - 1 - i; // 0 = newest
        // Gentle fade upward, but keep old lines (the greeting) clearly legible.
        const opacity = Math.max(0.35, 1 - fromBottom * 0.1);

        // Interrupted — a thin "you cut in" divider, no phone icon. Set apart
        // from the call lifecycle notes (connected/ended/declined).
        if (m.role === "system" && m.kind === "interrupted") {
          return (
            <div
              key={i}
              style={{
                alignSelf: "stretch",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                margin: "8px 0",
                opacity: Math.max(0.3, opacity - 0.15),
                transition: "opacity 0.4s ease",
                color: "#9a94a2",
                fontFamily: "var(--font-dm-sans)",
                fontSize: "10.5px",
                fontWeight: 500,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              }}
            >
              <span style={{ flex: 1, height: "1px", background: "currentColor", opacity: 0.4 }} />
              interrupted
              <span style={{ flex: 1, height: "1px", background: "currentColor", opacity: 0.4 }} />
            </div>
          );
        }

        // System notes (connected / ended / declined) — centered, muted, w/ icon.
        if (m.role === "system") {
          const down = m.kind === "declined" || m.kind === "ended"; // phone-down icon
          const color = m.kind === "declined" ? "#c2334d" : m.kind === "ended" ? "#8a8594" : "#2f9e54";
          return (
            <div
              key={i}
              style={{
                alignSelf: "center",
                display: "flex",
                alignItems: "center",
                gap: "7px",
                margin: "14px 0",
                opacity,
                transition: "opacity 0.4s ease",
                fontSize: "12px",
                fontWeight: 600,
                letterSpacing: "0.04em",
                textTransform: "uppercase",
                color,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"
                style={{ transform: down ? "rotate(133deg)" : "none" }}>
                <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z" />
              </svg>
              {m.text}
            </div>
          );
        }

        const isAI = m.role === "assistant";
        return (
          <p
            key={i}
            style={{
              // All on the left — speaker told apart by FONT, not side. Tight,
              // even spacing between lines (the wider gap read as uncanny).
              margin: "6px 0",
              maxWidth: "60ch",
              opacity,
              transition: "opacity 0.4s ease",
              lineHeight: 1.4,
              alignSelf: "flex-start",
              textAlign: "left",
              // Bot: Instrument Serif — types itself out. User: DM Sans, dark.
              fontFamily: isAI ? "var(--font-instrument-serif)" : "var(--font-dm-sans)",
              fontWeight: 400,
              fontSize: isAI ? "20px" : "18px",
              letterSpacing: isAI ? "0.2px" : "-0.2px",
              color: isAI ? "#4a4452" : "#15151c",
            }}
          >
            {isAI ? <StreamingText text={m.text} /> : m.text}
          </p>
        );
      })}
    </div>
  );
}

// ── Waveform ──────────────────────────────────────────────────────────────
// Reacts to the CALLER's actual mic level (0..1, streamed from the backend).
// Loud -> tall bars, silence -> flat. Center-weighted so it looks like a voice
// envelope; a per-bar offset keeps it from moving as one solid block.
function Waveform({ level }: { level: number }) {
  const N = 32;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "3px", height: "80px" }}>
      {Array.from({ length: N }).map((_, i) => {
        const envelope = 1 - Math.abs(i - (N - 1) / 2) / ((N - 1) / 2); // 0 edges, 1 middle
        const jitter = 0.6 + 0.4 * Math.abs(Math.sin(i * 1.7));
        const scale = 0.1 + level * (0.35 + 0.65 * envelope) * jitter;
        return (
          <span
            key={i}
            style={
              {
                width: "3px",
                height: "60px",
                borderRadius: "2px",
                background: "#fff",
                transformOrigin: "center",
                transform: `scaleY(${Math.max(0.06, Math.min(1, scale))})`,
                transition: "transform 0.09s ease-out",
              } as CSSProperties
            }
          />
        );
      })}
    </div>
  );
}

// ── Phone call screen ─────────────────────────────────────────────────────
// Inside the phone: name, a running call timer (no state words), the caller
// waveform, and the red hang-up button whose icon swings slant -> horizontal
// when the call ends.
export function PhoneCall({
  contact,
  state,
  level,
  ended,
  onHangup,
}: {
  contact: { name: string };
  state: string;
  level: number;
  ended: boolean;
  onHangup: () => void;
}) {
  // Waveform only reflects the caller — go flat when it isn't their turn.
  const activeLevel = state === "listening" ? level : 0;

  const [secs, setSecs] = useState(0);
  useEffect(() => {
    if (state === "calling" || ended) return;
    const id = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [state, ended]);
  const mmss = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;

  return (
    <div
      style={{
        flex: 1,
        background: "linear-gradient(180deg, #1b1b2a 0%, #2b2b3d 100%)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        color: "#fff",
        padding: "30px 0 22px",
      }}
    >
      <div style={{ fontSize: "23px", fontWeight: 600, letterSpacing: "-0.3px" }}>{contact.name}</div>
      <div style={{ fontSize: "14px", color: "#a6a6b8", marginTop: "5px" }}>
        {state === "calling" ? "calling…" : mmss}
      </div>

      <div style={{ flex: 1, display: "flex", alignItems: "center" }}>
        <Waveform level={activeLevel} />
      </div>

      <button
        onClick={onHangup}
        style={{
          width: "60px",
          height: "60px",
          borderRadius: "50%",
          background: "#ff3b30",
          border: "none",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 4px 14px rgba(255,59,48,0.45)",
        }}
      >
        <svg
          width="28"
          height="28"
          viewBox="0 0 24 24"
          fill="white"
          style={{
            // slant while live, swings to horizontal as the call ends
            transform: ended ? "rotate(0deg)" : "rotate(135deg)",
            transition: "transform 0.6s ease",
          }}
        >
          <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z" />
        </svg>
      </button>
    </div>
  );
}
