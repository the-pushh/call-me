"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AsYouType,
  getCountries,
  getCountryCallingCode,
  parsePhoneNumber,
  type CountryCode,
} from "libphonenumber-js";

import { PhoneCall, Transcript } from "./CallScreen";
import { placeCall, hangupCall, submitFeedback } from "./lib/backend";
import { useCall } from "./lib/useCall";

// Accent on the "." of "call me." — Apple green, tying it to the call action.
const ACCENT = "#30D158";

type EndReason = "user" | "limit";

// ISO alpha-2 -> the 🇺🇸-style flag emoji (each letter maps to a regional
// indicator symbol). Avoids shipping 250 flag images.
function flagOf(iso: string): string {
  return String.fromCodePoint(...[...iso.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
}

// Every country libphonenumber knows, with its dial code + English name. Built
// once. `regionNames` turns "US" -> "United States" for the searchable list.
type Country = { iso: CountryCode; name: string; dial: string; flag: string };

function buildCountries(): Country[] {
  const regionNames = new Intl.DisplayNames(["en"], { type: "region" });
  return getCountries()
    .map((iso) => ({
      iso,
      name: regionNames.of(iso) ?? iso,
      dial: `+${getCountryCallingCode(iso)}`,
      flag: flagOf(iso),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

// E.164 ("+14155552671") if `raw` is a valid number for `iso`, else null. One
// gate for both "is the call allowed" and "what to dial".
function toE164(raw: string, iso: CountryCode): string | null {
  try {
    const p = parsePhoneNumber(raw, iso);
    return p && p.isValid() ? p.number : null;
  } catch {
    return null;
  }
}

const contacts = [
  { 
    name: "Eve Ryder", 
    role: "Rolling Stone", 
    initials: "ER", 
    color: "#ec4899", 
    description: "Eve is your go-to voice for a laid-back, rock-and-roll vibe. She's a curious soul who loves classic rock, poetry, and going down random tech rabbit holes, always bringing warmth and natural color to the conversation.", 
    personality: "Laid-back · Warm · Curious", 
    responseType: "Conversational & colorful",
    personaCode: "eve"
  },
  { 
    name: "Siddhartha", 
    role: "Spiritual Guide", 
    initials: "S", 
    color: "#14b8a6", 
    description: "Siddhartha is your go-to voice for deep calm and spiritual grounding. Unaffected by the chaos of the world, he approaches every conversation with peaceful acceptance, gentle warmth, and a quiet sense of wonder.", 
    personality: "Peaceful · Grounded · Gentle", 
    responseType: "Slow & mindful",
    personaCode: "siddhartha"
  },
  { 
    name: "Jeremiah Sterling", 
    role: "Record Executive", 
    initials: "JS", 
    color: "#eab308", 
    description: "Jeremiah is your go-to voice for business and elegance. As a sharp executive running a record label, he brings a sophisticated, polished confidence to discussions about finances, networking, and the mechanics of success.", 
    personality: "Sophisticated · Confident · Pragmatic", 
    responseType: "Smooth & calculated",
    personaCode: "jeremiah"
  },
  { 
    name: "Billie Hayes", 
    role: "Analytical Scientist", 
    initials: "BH", 
    color: "#8b5cf6", 
    description: "Billie is your go-to voice for science and hyper-enthusiastic intellect. She's a brilliant, endearing nerd who processes the world through logic, systems, and highly precise facts, always eager to share her discoveries.", 
    personality: "Analytical · Enthusiastic · Precise", 
    responseType: "Fact-based & eager",
    personaCode: "billie"
  },
  { 
    name: "Avni Desai", 
    role: "Tech Founder", 
    initials: "AD", 
    color: "#f97316", 
    description: "Avni is your go-to voice for startup hustle and sharp pragmatism. A savvy tech founder from Bangalore, she moves fast and thinks critically, always analyzing the smartest, most efficient way to navigate a problem or build a solution.", 
    personality: "Shrewd · Fast-paced · Pragmatic", 
    responseType: "Quick & analytical",
    personaCode: "avni"
  }
];

// Small green iOS-style call button used on contact rows + detail. Greys out and
// stops responding while the entered number isn't a valid one to dial.
function CallButton({ onClick, size = 34, disabled = false }: { onClick: (e: React.MouseEvent) => void; size?: number; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={disabled ? "enter a valid phone number first" : "call"}
      style={{ width: `${size}px`, height: `${size}px`, borderRadius: "50%", background: disabled ? "#c7c7cc" : "#34c759", border: "none", cursor: disabled ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: disabled ? "none" : "0 2px 8px rgba(52,199,89,0.4)", transition: "background 0.2s ease" }}
    >
      <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24" fill="white">
        <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z" />
      </svg>
    </button>
  );
}

// Searchable country selector — replaces the fixed 7-code <select>. Click to
// open a popover with a search box over EVERY country (name or dial code), the
// way a shadcn combobox works, just built inline to match the app's styling.
function CountryCombobox({ countries, value, onChange }: { countries: Country[]; value: CountryCode; onChange: (iso: CountryCode) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const current = countries.find((c) => c.iso === value);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    inputRef.current?.focus();
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const needle = q.trim().toLowerCase();
  const list = needle
    ? countries.filter((c) => c.name.toLowerCase().includes(needle) || c.dial.includes(needle) || c.iso.toLowerCase() === needle)
    : countries;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{ display: "flex", alignItems: "center", gap: "5px", border: "none", background: "transparent", outline: "none", fontSize: "18px", color: "#1c1c1e", cursor: "pointer", fontWeight: 600, padding: "0 2px" }}
      >
        <span style={{ fontSize: "19px", lineHeight: 1 }}>{current?.flag ?? "🏳️"}</span>
        <span>{current?.dial ?? "+?"}</span>
        <svg width="10" height="6" viewBox="0 0 12 8" fill="none" stroke="#6b6580" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }}><path d="M1 1.5L6 6.5L11 1.5" /></svg>
      </button>

      {open && (
        <div
          style={{
            position: "absolute", top: "calc(100% + 12px)", left: "-12px", zIndex: 90,
            width: "300px", maxWidth: "80vw",
            background: "rgba(255,255,255,0.98)", backdropFilter: "blur(12px)",
            border: "1px solid rgba(80,60,140,0.18)", borderRadius: "14px",
            boxShadow: "0 16px 44px rgba(60,40,110,0.22)", overflow: "hidden",
          }}
        >
          <div style={{ padding: "10px", borderBottom: "1px solid #efeaf8" }}>
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search country or code"
              style={{ width: "100%", border: "1px solid #e2dcf0", borderRadius: "9px", padding: "8px 10px", fontSize: "14px", outline: "none", color: "#15151c", background: "#faf8ff" }}
            />
          </div>
          <div style={{ maxHeight: "260px", overflowY: "auto" }}>
            {list.map((c) => (
              <button
                key={c.iso}
                onClick={() => { onChange(c.iso); setOpen(false); setQ(""); }}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: "10px",
                  padding: "9px 14px", border: "none", cursor: "pointer", textAlign: "left",
                  background: c.iso === value ? "#f1ecfb" : "transparent",
                  fontSize: "14px", color: "#1c1c1e",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "#f6f2fe")}
                onMouseLeave={(e) => (e.currentTarget.style.background = c.iso === value ? "#f1ecfb" : "transparent")}
              >
                <span style={{ fontSize: "18px", lineHeight: 1 }}>{c.flag}</span>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                <span style={{ color: "#8e8e93", fontVariantNumeric: "tabular-nums" }}>{c.dial}</span>
              </button>
            ))}
            {list.length === 0 && (
              <div style={{ padding: "16px 14px", fontSize: "13px", color: "#8e8e93", textAlign: "center" }}>No match</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ContactDetail({ contact, onBack, onCall, canCall }: { contact: (typeof contacts)[0]; onBack: () => void; onCall: () => void; canCall: boolean }) {
  return (
    <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", padding: "10px 16px 6px", borderBottom: "0.5px solid #e5e5ea" }}>
        <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: "4px", color: "#007AFF", fontSize: "16px", background: "none", border: "none", cursor: "pointer", padding: "4px 0" }}>
          <svg width="9" height="15" viewBox="0 0 9 15" fill="none" stroke="#007AFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M7.5 1.5L1.5 7.5L7.5 13.5" /></svg>
          Contacts
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "22px 16px 14px" }}>
        <div style={{ width: "80px", height: "80px", borderRadius: "50%", background: contact.color, display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontSize: "26px", fontWeight: "700", marginBottom: "12px", boxShadow: `0 4px 18px ${contact.color}55` }}>{contact.initials}</div>
        <div style={{ fontSize: "22px", fontWeight: "700", color: "#000", letterSpacing: "-0.4px", textAlign: "center" }}>{contact.name}</div>
        <div style={{ fontSize: "14px", color: "#8e8e93", marginTop: "3px", textAlign: "center" }}>{contact.role}</div>
      </div>

      <div style={{ display: "flex", justifyContent: "center", marginBottom: "20px" }}>
        <div
          onClick={() => canCall && onCall()}
          title={canCall ? "call" : "enter a valid phone number first"}
          style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "5px", cursor: canCall ? "pointer" : "not-allowed", opacity: canCall ? 1 : 0.55 }}
        >
          <div style={{ width: "50px", height: "50px", borderRadius: "50%", background: canCall ? "#34c759" : "#c7c7cc", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: canCall ? "0 4px 14px rgba(52,199,89,0.45)" : "none", transition: "background 0.2s ease" }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="white"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z" /></svg>
          </div>
          <span style={{ fontSize: "11px", color: canCall ? "#34c759" : "#8e8e93", fontWeight: "500" }}>{canCall ? "call" : "add number"}</span>
        </div>
      </div>

      <div style={{ margin: "0 16px 12px" }}>
        <div style={{ fontSize: "13px", fontWeight: "600", color: "#8e8e93", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "6px", paddingLeft: "4px" }}>About</div>
        <div style={{ background: "#f2f2f7", borderRadius: "12px", padding: "12px 14px" }}>
          <p style={{ margin: 0, fontSize: "14px", color: "#1c1c1e", lineHeight: "1.5" }}>{contact.description}</p>
        </div>
      </div>

      <div style={{ margin: "0 16px 20px" }}>
        <div style={{ fontSize: "13px", fontWeight: "600", color: "#8e8e93", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "6px", paddingLeft: "4px" }}>Voice Profile</div>
        <div style={{ background: "#f2f2f7", borderRadius: "12px", overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "flex-start", padding: "11px 14px", borderBottom: "0.5px solid #d1d1d6", gap: "10px" }}>
            <span style={{ fontSize: "13px", color: "#8e8e93", minWidth: "100px", paddingTop: "1px" }}>Personality</span>
            <span style={{ fontSize: "13px", color: "#1c1c1e", flex: 1, textAlign: "right" }}>{contact.personality}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", padding: "11px 14px", gap: "10px" }}>
            <span style={{ fontSize: "13px", color: "#8e8e93", minWidth: "100px" }}>Response Type</span>
            <span style={{ fontSize: "13px", color: "#1c1c1e", flex: 1, textAlign: "right" }}>{contact.responseType}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// Hover-reveal "i" in the top-right. No drawer background — the project text just
// floats in from the right edge over the page.
function InfoDrawer() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onMouseEnter={() => setOpen(true)}
        onClick={() => setOpen((o) => !o)}
        style={{
          position: "fixed", top: "22px", right: "22px", zIndex: 60,
          width: "34px", height: "34px", borderRadius: "50%",
          border: "1.5px solid rgba(60,40,110,0.55)", background: "transparent",
          color: "#3a2868", fontStyle: "italic",
          fontFamily: "Georgia, serif", fontSize: "18px", fontWeight: 700, cursor: "pointer",
        }}
      >
        i
      </button>
      <div
        onMouseLeave={() => setOpen(false)}
        style={{
          position: "fixed", top: 0, right: 0, height: "100vh", width: "340px", zIndex: 55,
          transform: open ? "translateX(0)" : "translateX(110%)",
          opacity: open ? 1 : 0,
          transition: "transform 0.45s cubic-bezier(0.22,1,0.36,1), opacity 0.35s ease",
          pointerEvents: open ? "auto" : "none",
          padding: "78px 30px 28px", color: "#241a45",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "26px", fontWeight: 800, letterSpacing: "-0.5px" }}>
          call me<span style={{ color: ACCENT }}>.</span>
        </h2>
        <p style={{ marginTop: "16px", fontSize: "14px", lineHeight: 1.6, color: "#3a2f63" }}>
          A voice-AI phone app. Pick a persona, drop your number, and the bot calls
          you for a real conversation — your voice is transcribed, run through a
          language model in character, and spoken back in its own voice, streamed
          both ways over a live phone line.
        </p>
        <p style={{ marginTop: "16px", fontSize: "14px", lineHeight: 1.6, color: "#3a2f63" }}>
          Really it&apos;s just an experiment with the voice model — I love working
          with voice and sound waves in general, and this is me playing in that
          space. It&apos;s also my attempt at building a real-time voice pipeline
          the hard way: stitching STT → LLM → TTS myself, no voice-to-voice
          modality model doing it all in one shot.
        </p>
        <p style={{ marginTop: "16px", fontSize: "12px", lineHeight: 1.7, color: "#5a4f7d" }}>
          Twilio Media Streams · Whisper STT · Llama brain · Cartesia / Kokoro TTS ·
          FastAPI + Next.js
        </p>
      </div>
    </>
  );
}

// A subtle toast in the bottom-right after a call ends: why it ended (2-min token
// cap vs hang-up) plus a one-line remark box. The owner later picks which remarks
// to feature — `may_feature` consent is implied by leaving one.
function FeedbackToast({ reason, onClose }: { reason: EndReason; onClose: () => void }) {
  const [text, setText] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      await submitFeedback({ text, may_feature: true });
    } catch {
      // A toy guestbook — never block the close on a network hiccup.
    } finally {
      setBusy(false);
      setSent(true);
    }
  };

  return (
    <div
      style={{
        position: "fixed", bottom: "54px", right: "22px", zIndex: 80,
        width: "300px", maxWidth: "calc(100vw - 44px)",
        background: "rgba(255,255,255,0.92)", backdropFilter: "blur(10px)",
        border: "1px solid rgba(80,60,140,0.18)", borderRadius: "16px",
        padding: "14px 16px 16px",
      }}
    >
      <button
        onClick={onClose}
        aria-label="dismiss"
        style={{
          position: "absolute", top: "10px", right: "10px", width: "20px", height: "20px",
          border: "none", background: "transparent", color: "#9a90b8", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", padding: 0,
        }}
      >
        <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M1 1l10 10M11 1L1 11" /></svg>
      </button>

      <div style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: ACCENT }}>
        Call ended
      </div>
      <p style={{ margin: "5px 0 0", fontSize: "12.5px", lineHeight: 1.45, color: "#4a4263", paddingRight: "14px" }}>
        {reason === "limit" ? (
          <>2-minute cap reached — these run on my own API tokens. <span style={{ whiteSpace: "nowrap" }}>buy me some? 😄</span></>
        ) : (
          <>You hung up — hope it was fun.</>
        )}
      </p>

      {sent ? (
        <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#4a4263" }}>thanks 🙏</p>
      ) : (
        <div style={{ display: "flex", alignItems: "flex-end", gap: "8px", marginTop: "12px" }}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="leave a remark…"
            rows={1}
            style={{
              flex: 1, resize: "none", border: "1px solid #e2dcf0", borderRadius: "10px",
              padding: "8px 10px", fontSize: "13px", outline: "none", fontFamily: "inherit",
              color: "#15151c", background: "#faf8ff", lineHeight: 1.4,
            }}
          />
          <button
            onClick={send}
            disabled={busy || !text.trim()}
            aria-label="send remark"
            style={{
              width: "34px", height: "34px", flexShrink: 0, borderRadius: "10px", border: "none",
              background: text.trim() ? ACCENT : "#e2dcf0", color: text.trim() ? "#06320f" : "#a99fc4",
              cursor: text.trim() ? "pointer" : "default", display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" /></svg>
          </button>
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const countries = useMemo(buildCountries, []);
  const [country, setCountry] = useState<CountryCode>("US");
  const [number, setNumber] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedContact, setSelectedContact] = useState<number | null>(null);
  const [activeCall, setActiveCall] = useState<{ index: number; callSid: string } | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const [callError, setCallError] = useState<string | null>(null);
  const [now, setNow] = useState<Date | null>(null);
  const [feedback, setFeedback] = useState<EndReason | null>(null);

  const { state, messages, level, ended, endReason, declined } = useCall(activeCall?.callSid ?? null);

  // Live local clock for the phone status bar.
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 15000);
    return () => clearInterval(id);
  }, []);

  // Detect the caller's country from their IP and preset the selector. ipapi
  // returns an ISO alpha-2 in `country_code`; only accept it if it's one we know.
  useEffect(() => {
    fetch("https://ipapi.co/json/")
      .then((r) => r.json())
      .then((d) => {
        const iso = d?.country_code as CountryCode | undefined;
        if (iso && countries.some((c) => c.iso === iso)) setCountry(iso);
      })
      .catch(() => {});
  }, [countries]);

  // Valid number for the chosen country -> the E.164 string we dial; null while
  // it's incomplete/invalid. Drives both the call buttons' disabled state and
  // what gets sent to the backend, so the two can never disagree.
  const e164 = useMemo(() => toE164(number, country), [number, country]);
  const valid = e164 !== null;

  // Format as the user types; on delete, leave their edit alone so a backspace
  // can't get "stuck" fighting the formatter.
  const onNumberChange = (input: string) => {
    if (input.length < number.length) setNumber(input);
    else setNumber(new AsYouType(country).input(input));
  };
  const onCountryChange = (iso: CountryCode) => {
    setCountry(iso);
    setCallError(null);
    setNumber((n) => new AsYouType(iso).input(n.replace(/[^\d]/g, "")));
  };

  // End sequence: swing the hang-up icon (closing), THEN collapse the transcript
  // and slide the phone back to centre (panelOpen=false animates), THEN drop the
  // phone screen to contacts and raise the feedback card. `reason` is "user" when
  // the in-app hang-up was tapped, "limit" when the backend ended it (2-min cap /
  // remote hangup). Three visible beats, not one instant cut.
  const beginEnd = useCallback((reason: EndReason | "declined") => {
    setClosing(true);
    // Hold ~1.2s with the transcript still open so the "Call ended" line is read,
    // then collapse it / slide the phone back, then drop to contacts.
    setTimeout(() => {
      setPanelOpen(false);
      setTimeout(() => {
        setActiveCall(null);
        setSelectedContact(null);
        setClosing(false);
        // A declined call had no conversation — show no "how was it?" toast.
        if (reason !== "declined") setFeedback(reason);
      }, 600);
    }, 1200);
  }, []);

  // Backend says the call is over — map its reason to the end card: the 2-min cap
  // ("limit") vs the caller hanging up ("remote" -> the same card as the in-app
  // hang-up). Only fire while a call is still active and not already tearing down.
  useEffect(() => {
    if (ended && activeCall && !closing) beginEnd(endReason === "remote" ? "user" : "limit");
  }, [ended, endReason, activeCall, closing, beginEnd]);

  // Callee never picked up — let the "declined" line show briefly, then close.
  useEffect(() => {
    if (declined && activeCall && !closing) {
      const id = setTimeout(() => beginEnd("declined"), 1100);
      return () => clearTimeout(id);
    }
  }, [declined, activeCall, closing, beginEnd]);

  const handleCall = async (index: number) => {
    if (!e164) {
      setCallError("enter a valid phone number first");
      return;
    }
    setCallError(null);
    try {
      const callSid = await placeCall(e164, contacts[index].personaCode);
      setSelectedContact(index);
      setActiveCall({ index, callSid });
      setPanelOpen(true);
    } catch {
      setCallError("couldn't place the call — is the backend running?");
    }
  };

  const q = query.trim().toLowerCase();
  const visible = contacts
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => !q || c.name.toLowerCase().includes(q) || c.role.toLowerCase().includes(q));

  const inCall = activeCall !== null;
  const clock = now ? now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "9:41";
  // Show the "doesn't look right" hint only once they've typed something real.
  const showInvalid = number.trim().length > 2 && !valid;

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center select-none"
      style={{ background: "linear-gradient(160deg, #f0ecff 0%, #e4dcf8 50%, #ede9fe 100%)", position: "relative" }}
    >
      <InfoDrawer />
      {feedback && <FeedbackToast reason={feedback} onClose={() => setFeedback(null)} />}

      {/* Bottom bar — token cap note + source link. */}
      <div
        style={{
          position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 40,
          display: "flex", alignItems: "center", justifyContent: "center", gap: "14px",
          padding: "10px 0 12px", fontSize: "12.5px", color: "#5a4f7d",
        }}
      >
        <span>Calls are capped at 2 min — they run on my own API tokens. Man API Tokens are expensive! </span>
        <a
          href="https://github.com/the-pushh/call-me"
          target="_blank"
          rel="noreferrer"
          style={{ display: "inline-flex", alignItems: "center", gap: "5px", color: "#241a45", fontWeight: 600, textDecoration: "none" }}
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z" />
          </svg>
          GitHub
        </a>
      </div>

      {/* Persistent title + a rounded pill holding the dial code selector and
          number input. */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "22px", marginBottom: "44px" }}>
        <h1 style={{ fontSize: "60px", fontWeight: 800, color: "#1c1c1e", letterSpacing: "-2.5px", lineHeight: 1 }}>
          call me<span style={{ color: ACCENT }}>.</span>
        </h1>
        <div
          style={{
            display: "flex", alignItems: "center", gap: "6px",
            background: "rgba(255,255,255,0.75)", borderRadius: "9999px",
            border: `1px solid ${showInvalid ? "rgba(224,36,94,0.5)" : "rgba(80,60,140,0.18)"}`,
            padding: "8px 10px 8px 16px",
            boxShadow: "0 8px 30px rgba(80,60,140,0.12)",
            transition: "border-color 0.2s ease",
          }}
        >
          <CountryCombobox countries={countries} value={country} onChange={onCountryChange} />
          <div style={{ width: "1px", height: "22px", background: "rgba(80,60,140,0.16)" }} />
          <input
            type="tel"
            value={number}
            onChange={(e) => onNumberChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && valid && selectedContact !== null) handleCall(selectedContact); }}
            placeholder="your number"
            style={{
              border: "none", outline: "none", background: "transparent",
              fontSize: "18px", letterSpacing: "0.5px", color: "#1c1c1e",
              padding: "4px 6px", width: "190px", fontWeight: 500,
            }}
          />
          {valid && (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={ACCENT} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "4px" }}><path d="M20 6L9 17l-5-5" /></svg>
          )}
        </div>
      </div>
      {callError ? (
        <p style={{ color: "#e0245e", fontSize: "13px", marginTop: "-30px", marginBottom: "20px", fontWeight: 500 }}>{callError}</p>
      ) : showInvalid ? (
        <p style={{ color: "#e0245e", fontSize: "13px", marginTop: "-30px", marginBottom: "20px", fontWeight: 500 }}>that doesn&apos;t look like a valid number for this country</p>
      ) : null}

      {/* Stage: transcript (left, animates in) + plenty of gap + phone (right). */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div
          style={{
            width: panelOpen ? "460px" : "0px",
            opacity: panelOpen ? 1 : 0,
            marginRight: panelOpen ? "110px" : "0px",
            overflow: "hidden",
            transition: "width 0.55s cubic-bezier(0.22,1,0.36,1), opacity 0.45s ease, margin 0.55s cubic-bezier(0.22,1,0.36,1)",
            display: "flex",
            justifyContent: "flex-end",
          }}
        >
          {activeCall && <Transcript messages={messages} ending={closing} />}
        </div>

        {/* iPhone — jolts with a hang-up bounce as the call tears down. */}
        <div
          className="relative"
          style={{
            width: "300px",
            animation: closing ? "hangup-bounce 0.62s cubic-bezier(0.28,0.7,0.4,1)" : "none",
          }}
        >
          <div style={{ position: "absolute", left: "-4px", top: "88px", width: "4px", height: "24px", background: "linear-gradient(90deg, #3a3a3c, #636366)", borderRadius: "2px 0 0 2px", boxShadow: "-2px 0 5px rgba(0,0,0,0.55)" }} />
          <div style={{ position: "absolute", left: "-4px", top: "128px", width: "4px", height: "42px", background: "linear-gradient(90deg, #3a3a3c, #636366)", borderRadius: "2px 0 0 2px", boxShadow: "-2px 0 5px rgba(0,0,0,0.55)" }} />
          <div style={{ position: "absolute", left: "-4px", top: "178px", width: "4px", height: "42px", background: "linear-gradient(90deg, #3a3a3c, #636366)", borderRadius: "2px 0 0 2px", boxShadow: "-2px 0 5px rgba(0,0,0,0.55)" }} />
          <div style={{ position: "absolute", right: "-4px", top: "148px", width: "4px", height: "58px", background: "linear-gradient(270deg, #3a3a3c, #636366)", borderRadius: "0 2px 2px 0", boxShadow: "2px 0 5px rgba(0,0,0,0.55)" }} />

          <div style={{
            borderRadius: "54px",
            background: "linear-gradient(145deg, #3a3a3c 0%, #1c1c1e 55%, #2c2c2e 100%)",
            padding: "14px",
            boxShadow: ["0 0 0 0.5px rgba(255,255,255,0.18)", "0 0 0 1.5px rgba(0,0,0,0.9)", "0 40px 100px rgba(0,0,0,0.5)", "0 10px 30px rgba(0,0,0,0.35)", "inset 0 1px 0 rgba(255,255,255,0.14)", "inset 0 -1px 0 rgba(0,0,0,0.4)"].join(", "),
          }}>
            <div style={{
              borderRadius: "42px", overflow: "hidden", background: "#ffffff", height: "592px",
              display: "flex", flexDirection: "column",
              // Apple's native system font for everything ON the phone screen.
              fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Helvetica Neue", Arial, sans-serif',
            }}>
              {/* Status bar with the Dynamic Island floating inline between the
                  time and the icons, so the screen reads full-bleed (no black bar). */}
              <div style={{ position: "relative", background: inCall ? "#1b1b2a" : "#fff", display: "flex", justifyContent: "space-between", alignItems: "center", padding: "13px 24px 7px" }}>
                <span suppressHydrationWarning style={{ fontSize: "15px", fontWeight: 600, color: inCall ? "#fff" : "#000", letterSpacing: "-0.3px" }}>{clock}</span>

                {/* Dynamic Island — centered black pill */}
                <div style={{ position: "absolute", left: "50%", top: "9px", transform: "translateX(-50%)", width: "100px", height: "29px", background: "#000", borderRadius: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 11px" }}>
                  <div style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#15151a" }} />
                  <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#0a0a0a", border: "1.5px solid #1c1c22" }} />
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                  <svg width="15" height="11" viewBox="0 0 18 14" fill={inCall ? "#fff" : "#000"}><path d="M9 10.5c-.9 0-1.6.7-1.6 1.6s.7 1.6 1.6 1.6 1.6-.7 1.6-1.6-.7-1.6-1.6-1.6zm0-4c-2.1 0-4 .9-5.4 2.3l1.5 1.5C6.1 9.3 7.5 8.7 9 8.7s2.9.6 3.9 1.6l1.5-1.5C13 7.4 11.1 6.5 9 6.5zm0-4C5.7 2.5 2.8 3.8.8 5.9l1.5 1.5C3.9 5.8 6.3 4.7 9 4.7s5.1 1.1 6.7 2.7l1.5-1.5C15.2 3.8 12.3 2.5 9 2.5z" /></svg>
                  <svg width="24" height="12" viewBox="0 0 28 14"><rect x="0.5" y="0.5" width="22" height="13" rx="3.5" stroke={inCall ? "#fff" : "#000"} strokeWidth="1" fill="none" /><rect x="2" y="2" width="16" height="10" rx="2" fill={inCall ? "#fff" : "#000"} /><path d="M24 5v4c.9-.5 1.5-1.2 1.5-2s-.6-1.5-1.5-2z" fill={inCall ? "#fff" : "#000"} /></svg>
                </div>
              </div>

              {/* Content — live call, contact detail, or contacts list */}
              {inCall ? (
                <PhoneCall contact={contacts[activeCall.index]} state={state} level={level} ended={ended || closing} onHangup={() => { hangupCall(activeCall.callSid); beginEnd("user"); }} />
              ) : selectedContact !== null ? (
                <ContactDetail contact={contacts[selectedContact]} onBack={() => setSelectedContact(null)} onCall={() => handleCall(selectedContact)} canCall={valid} />
              ) : (
                <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", padding: "14px 16px 6px" }}>
                    <h2 style={{ margin: 0, fontSize: "28px", fontWeight: "700", color: "#000", letterSpacing: "-0.5px" }}>Contacts</h2>
                    <button onClick={() => setEditMode((e) => !e)} style={{ color: "#007AFF", fontSize: "16px", background: "none", border: "none", cursor: "pointer", padding: "4px 0" }}>{editMode ? "Done" : "Edit"}</button>
                  </div>

                  <div style={{ margin: "4px 16px 10px", background: "#f2f2f7", borderRadius: "12px", padding: "8px 12px", display: "flex", alignItems: "center", gap: "6px" }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="#8e8e93"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z" /></svg>
                    <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" style={{ border: "none", outline: "none", background: "transparent", fontSize: "14px", color: "#1c1c1e", flex: 1 }} />
                  </div>

                  {visible.map(({ c, i }) => (
                    <div key={i} onClick={() => !editMode && setSelectedContact(i)} style={{ display: "flex", alignItems: "center", padding: editMode ? "10px 16px 10px 12px" : "10px 16px", borderBottom: "0.5px solid #e5e5ea", gap: "12px", cursor: editMode ? "default" : "pointer" }}>
                      {editMode && (
                        <div style={{ width: "22px", height: "22px", borderRadius: "50%", border: "2px solid #ff3b30", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          <div style={{ width: "10px", height: "2px", background: "#ff3b30", borderRadius: "1px" }} />
                        </div>
                      )}
                      <div style={{ width: "46px", height: "46px", borderRadius: "50%", background: c.color, display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontSize: "15px", fontWeight: "600", flexShrink: 0 }}>{c.initials}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: "16px", fontWeight: "500", color: "#000", letterSpacing: "-0.2px" }}>{c.name}</div>
                        <div style={{ fontSize: "13px", color: "#8e8e93", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.role}</div>
                      </div>
                      {editMode ? (
                        <svg width="8" height="14" viewBox="0 0 8 14" fill="none" stroke="#c7c7cc" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M1 1l6 6-6 6" /></svg>
                      ) : (
                        <CallButton onClick={(e) => { e.stopPropagation(); handleCall(i); }} disabled={!valid} />
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Home indicator — tap to return to the contacts list. */}
              <div onClick={() => { setSelectedContact(null); setQuery(""); }} style={{ background: inCall ? "#2b2b3d" : "#fff", display: "flex", justifyContent: "center", padding: "10px 0 14px", cursor: "pointer" }}>
                <div style={{ width: "134px", height: "5px", background: inCall ? "rgba(255,255,255,0.3)" : "rgba(0,0,0,0.18)", borderRadius: "3px" }} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
