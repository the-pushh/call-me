"use client";

import { useState } from "react";

const contacts = [
  {
    name: "Alex Rivera",
    role: "Tech Visionary",
    initials: "AR",
    color: "#3b82f6",
    description: "Alex is your go-to voice for all things tech. Sharp, fast-paced, and always up to date with the latest in AI, startups, and innovation.",
    personality: "Analytical · Direct · Energetic",
    responseType: "Concise & data-driven",
  },
  {
    name: "Zara Moon",
    role: "Pop Sensation",
    initials: "ZM",
    color: "#a855f7",
    description: "Zara brings the vibes. Whether it's music, culture, or just keeping things light and fun, she keeps the conversation trendy and full of energy.",
    personality: "Playful · Expressive · Trendy",
    responseType: "Casual & conversational",
  },
  {
    name: "Marcus Cole",
    role: "Business Legend",
    initials: "MC",
    color: "#22c55e",
    description: "Marcus speaks the language of growth. With decades of boardroom wisdom, he cuts through the noise and helps you think like an executive.",
    personality: "Confident · Strategic · Authoritative",
    responseType: "Structured & actionable",
  },
  {
    name: "Priya Shah",
    role: "Wellness Guru",
    initials: "PS",
    color: "#f43f5e",
    description: "Priya is your calm in the chaos. She blends mindfulness, science, and warmth to help you feel grounded, heard, and inspired.",
    personality: "Warm · Thoughtful · Calming",
    responseType: "Empathetic & reflective",
  },
  {
    name: "Jake Storm",
    role: "Adventure Creator",
    initials: "JS",
    color: "#f97316",
    description: "Jake lives for the next big thing. High energy, spontaneous, and always ready to push limits — he's the voice that gets you moving.",
    personality: "Bold · Spontaneous · Adventurous",
    responseType: "Enthusiastic & action-oriented",
  },
];

function ContactDetail({
  contact,
  onBack,
}: {
  contact: (typeof contacts)[0];
  onBack: () => void;
}) {
  return (
    <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
      {/* Nav bar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        padding: "10px 16px 6px",
        borderBottom: "0.5px solid #e5e5ea",
      }}>
        <button
          onClick={onBack}
          style={{
            display: "flex", alignItems: "center", gap: "4px",
            color: "#007AFF", fontSize: "16px", fontWeight: "400",
            background: "none", border: "none", cursor: "pointer",
            fontFamily: "system-ui, -apple-system", padding: "4px 0",
          }}
        >
          <svg width="9" height="15" viewBox="0 0 9 15" fill="none" stroke="#007AFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M7.5 1.5L1.5 7.5L7.5 13.5" />
          </svg>
          Contacts
        </button>
      </div>

      {/* Avatar + name */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "22px 16px 14px" }}>
        <div style={{
          width: "80px", height: "80px",
          borderRadius: "50%",
          background: contact.color,
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "white", fontSize: "26px", fontWeight: "700",
          marginBottom: "12px",
          boxShadow: `0 4px 18px ${contact.color}55`,
        }}>
          {contact.initials}
        </div>
        <div style={{ fontSize: "22px", fontWeight: "700", color: "#000", letterSpacing: "-0.4px", textAlign: "center" }}>
          {contact.name}
        </div>
        <div style={{ fontSize: "14px", color: "#8e8e93", marginTop: "3px", textAlign: "center" }}>
          {contact.role}
        </div>
      </div>

      {/* Call Me button */}
      <div style={{ display: "flex", justifyContent: "center", marginBottom: "20px" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "5px", cursor: "pointer" }}>
          <div style={{
            width: "50px", height: "50px",
            borderRadius: "50%",
            background: "#34c759",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 4px 14px rgba(52,199,89,0.45)",
          }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
              <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/>
            </svg>
          </div>
          <span style={{ fontSize: "11px", color: "#34c759", fontWeight: "500" }}>call</span>
        </div>
      </div>

      {/* About section */}
      <div style={{ margin: "0 16px 12px" }}>
        <div style={{ fontSize: "13px", fontWeight: "600", color: "#8e8e93", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "6px", paddingLeft: "4px" }}>
          About
        </div>
        <div style={{
          background: "#f2f2f7",
          borderRadius: "12px",
          padding: "12px 14px",
        }}>
          <p style={{ margin: 0, fontSize: "14px", color: "#1c1c1e", lineHeight: "1.5" }}>
            {contact.description}
          </p>
        </div>
      </div>

      {/* Details section */}
      <div style={{ margin: "0 16px 20px" }}>
        <div style={{ fontSize: "13px", fontWeight: "600", color: "#8e8e93", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "6px", paddingLeft: "4px" }}>
          Voice Profile
        </div>
        <div style={{
          background: "#f2f2f7",
          borderRadius: "12px",
          overflow: "hidden",
        }}>
          <div style={{
            display: "flex", alignItems: "flex-start",
            padding: "11px 14px",
            borderBottom: "0.5px solid #d1d1d6",
            gap: "10px",
          }}>
            <span style={{ fontSize: "13px", color: "#8e8e93", minWidth: "100px", paddingTop: "1px" }}>Personality</span>
            <span style={{ fontSize: "13px", color: "#1c1c1e", flex: 1, textAlign: "right" }}>{contact.personality}</span>
          </div>
          <div style={{
            display: "flex", alignItems: "center",
            padding: "11px 14px",
            gap: "10px",
          }}>
            <span style={{ fontSize: "13px", color: "#8e8e93", minWidth: "100px" }}>Response Type</span>
            <span style={{ fontSize: "13px", color: "#1c1c1e", flex: 1, textAlign: "right" }}>{contact.responseType}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [number, setNumber] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [selectedContact, setSelectedContact] = useState<number | null>(null);

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center gap-7 select-none"
      style={{ background: "linear-gradient(160deg, #f0ecff 0%, #e4dcf8 50%, #ede9fe 100%)" }}
    >
      {/* Title above the phone */}
      <div className="text-center">
        <h1
          className="font-black tracking-tight"
          style={{
            fontSize: "60px",
            color: "#1c1c1e",
            fontFamily: "system-ui, -apple-system",
            lineHeight: 1,
            letterSpacing: "-2px",
          }}
        >
          call me
        </h1>
        <p
          className="tracking-widest uppercase mt-2"
          style={{ color: "#9b87d1", fontSize: "11px", letterSpacing: "0.25em" }}
        >
          reach anyone · anytime
        </p>
      </div>

      {/* iPhone + sticker */}
      <div className="relative">

        {/* Say Hello sticker — right side */}
        <div
          style={{
            position: "absolute",
            right: "-148px",
            top: "210px",
            transform: "rotate(4deg)",
            filter: "drop-shadow(3px 6px 12px rgba(0,0,0,0.22))",
            zIndex: 20,
          }}
        >
          {/* tape strip */}
          <div style={{
            width: "52px", height: "14px",
            background: "rgba(253,230,138,0.75)",
            borderRadius: "2px",
            margin: "0 auto",
            boxShadow: "0 1px 3px rgba(0,0,0,0.12)",
            position: "relative", zIndex: 1,
          }} />
          {/* note body */}
          <div style={{
            width: "140px",
            marginTop: "-5px",
            background: "linear-gradient(175deg, #fef08a 0%, #fde047 100%)",
            padding: "10px 12px 16px",
            borderRadius: "0 0 3px 3px",
            boxShadow: "2px 5px 14px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.45)",
          }}>
            <p style={{
              color: "#78350f", fontSize: "12px", fontWeight: "700",
              textAlign: "center", marginBottom: "9px",
              fontFamily: "system-ui, -apple-system",
            }}>
              say hello 👋
            </p>
            <input
              type="tel"
              value={number}
              onChange={e => setNumber(e.target.value)}
              placeholder="your number"
              style={{
                width: "100%", boxSizing: "border-box",
                background: "rgba(255,255,255,0.55)",
                border: "1px solid rgba(161,98,7,0.3)",
                borderRadius: "6px",
                padding: "6px 8px",
                fontSize: "12px",
                color: "#78350f",
                outline: "none",
                fontFamily: "monospace",
                textAlign: "center",
              }}
            />
          </div>
        </div>

        {/* iPhone */}
        <div className="relative" style={{ width: "300px" }}>

          {/* Mute/silent switch */}
          <div style={{
            position: "absolute", left: "-4px", top: "88px",
            width: "4px", height: "24px",
            background: "linear-gradient(90deg, #3a3a3c, #636366)",
            borderRadius: "2px 0 0 2px",
            boxShadow: "-2px 0 5px rgba(0,0,0,0.55)",
          }} />
          {/* Volume up */}
          <div style={{
            position: "absolute", left: "-4px", top: "128px",
            width: "4px", height: "42px",
            background: "linear-gradient(90deg, #3a3a3c, #636366)",
            borderRadius: "2px 0 0 2px",
            boxShadow: "-2px 0 5px rgba(0,0,0,0.55)",
          }} />
          {/* Volume down */}
          <div style={{
            position: "absolute", left: "-4px", top: "178px",
            width: "4px", height: "42px",
            background: "linear-gradient(90deg, #3a3a3c, #636366)",
            borderRadius: "2px 0 0 2px",
            boxShadow: "-2px 0 5px rgba(0,0,0,0.55)",
          }} />
          {/* Power button */}
          <div style={{
            position: "absolute", right: "-4px", top: "148px",
            width: "4px", height: "58px",
            background: "linear-gradient(270deg, #3a3a3c, #636366)",
            borderRadius: "0 2px 2px 0",
            boxShadow: "2px 0 5px rgba(0,0,0,0.55)",
          }} />

          {/* Phone frame */}
          <div style={{
            borderRadius: "54px",
            background: "linear-gradient(145deg, #3a3a3c 0%, #1c1c1e 55%, #2c2c2e 100%)",
            padding: "14px",
            boxShadow: [
              "0 0 0 0.5px rgba(255,255,255,0.18)",
              "0 0 0 1.5px rgba(0,0,0,0.9)",
              "0 40px 100px rgba(0,0,0,0.5)",
              "0 10px 30px rgba(0,0,0,0.35)",
              "inset 0 1px 0 rgba(255,255,255,0.14)",
              "inset 0 -1px 0 rgba(0,0,0,0.4)",
            ].join(", "),
          }}>

            {/* Screen */}
            <div style={{
              borderRadius: "42px",
              overflow: "hidden",
              background: "#ffffff",
              height: "592px",
              display: "flex",
              flexDirection: "column",
              fontFamily: "system-ui, -apple-system, sans-serif",
            }}>

              {/* Dynamic Island */}
              <div style={{
                background: "#000",
                display: "flex",
                justifyContent: "center",
                paddingTop: "14px",
                paddingBottom: "8px",
              }}>
                <div style={{
                  width: "124px", height: "36px",
                  background: "#000",
                  borderRadius: "20px",
                  border: "1.5px solid #222",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-around",
                  padding: "0 22px",
                }}>
                  <div style={{ width: "7px", height: "7px", borderRadius: "50%", background: "#111" }} />
                  <div style={{ width: "12px", height: "12px", borderRadius: "50%", background: "#0a0a0a", border: "2px solid #1a1a1a" }} />
                </div>
              </div>

              {/* Status bar */}
              <div style={{
                background: "#fff",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "2px 22px 4px",
              }}>
                <span style={{ fontSize: "14px", fontWeight: "600", color: "#000", letterSpacing: "-0.3px" }}>9:41</span>
                <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                  <div style={{ display: "flex", gap: "2px", alignItems: "flex-end" }}>
                    {[4, 6, 8, 11].map((h, i) => (
                      <div key={i} style={{ width: "3px", height: `${h}px`, background: "#000", borderRadius: "1px" }} />
                    ))}
                  </div>
                  <svg width="15" height="11" viewBox="0 0 18 14" fill="#000">
                    <path d="M9 10.5c-.9 0-1.6.7-1.6 1.6s.7 1.6 1.6 1.6 1.6-.7 1.6-1.6-.7-1.6-1.6-1.6zm0-4c-2.1 0-4 .9-5.4 2.3l1.5 1.5C6.1 9.3 7.5 8.7 9 8.7s2.9.6 3.9 1.6l1.5-1.5C13 7.4 11.1 6.5 9 6.5zm0-4C5.7 2.5 2.8 3.8.8 5.9l1.5 1.5C3.9 5.8 6.3 4.7 9 4.7s5.1 1.1 6.7 2.7l1.5-1.5C15.2 3.8 12.3 2.5 9 2.5z"/>
                  </svg>
                  <svg width="24" height="12" viewBox="0 0 28 14">
                    <rect x="0.5" y="0.5" width="22" height="13" rx="3.5" stroke="#000" strokeWidth="1" fill="none"/>
                    <rect x="2" y="2" width="16" height="10" rx="2" fill="#000"/>
                    <path d="M24 5v4c.9-.5 1.5-1.2 1.5-2s-.6-1.5-1.5-2z" fill="#000"/>
                  </svg>
                </div>
              </div>

              {/* App content — contacts list or detail view */}
              {selectedContact !== null ? (
                <ContactDetail
                  contact={contacts[selectedContact]}
                  onBack={() => setSelectedContact(null)}
                />
              ) : (
                <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>

                  {/* Contacts header */}
                  <div style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-end",
                    padding: "14px 16px 6px",
                  }}>
                    <h2 style={{ margin: 0, fontSize: "28px", fontWeight: "700", color: "#000", letterSpacing: "-0.5px" }}>
                      Contacts
                    </h2>
                    <button
                      onClick={() => setEditMode(e => !e)}
                      style={{
                        color: "#007AFF",
                        fontSize: "16px",
                        fontWeight: "400",
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        padding: "4px 0",
                        fontFamily: "system-ui, -apple-system",
                      }}
                    >
                      {editMode ? "Done" : "Edit"}
                    </button>
                  </div>

                  {/* Search bar */}
                  <div style={{
                    margin: "4px 16px 10px",
                    background: "#f2f2f7",
                    borderRadius: "12px",
                    padding: "8px 12px",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="#8e8e93">
                      <path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
                    </svg>
                    <span style={{ color: "#8e8e93", fontSize: "14px" }}>Search</span>
                  </div>

                  {/* Contact rows */}
                  {contacts.map((c, i) => (
                    <div
                      key={i}
                      onClick={() => !editMode && setSelectedContact(i)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        padding: editMode ? "10px 16px 10px 12px" : "10px 16px",
                        borderBottom: "0.5px solid #e5e5ea",
                        gap: "12px",
                        cursor: editMode ? "default" : "pointer",
                      }}
                    >
                      {editMode && (
                        <div style={{
                          width: "22px", height: "22px",
                          borderRadius: "50%",
                          border: "2px solid #ff3b30",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          flexShrink: 0,
                        }}>
                          <div style={{ width: "10px", height: "2px", background: "#ff3b30", borderRadius: "1px" }} />
                        </div>
                      )}

                      {/* Avatar */}
                      <div style={{
                        width: "46px", height: "46px",
                        borderRadius: "50%",
                        background: c.color,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        color: "white", fontSize: "15px", fontWeight: "600",
                        flexShrink: 0,
                      }}>
                        {c.initials}
                      </div>

                      {/* Name + role */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: "16px", fontWeight: "500", color: "#000", letterSpacing: "-0.2px" }}>
                          {c.name}
                        </div>
                        <div style={{ fontSize: "13px", color: "#8e8e93", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {c.role}
                        </div>
                      </div>

                      {/* Chevron or call button */}
                      {editMode ? (
                        <svg width="8" height="14" viewBox="0 0 8 14" fill="none" stroke="#c7c7cc" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M1 1l6 6-6 6"/>
                        </svg>
                      ) : (
                        <svg width="8" height="14" viewBox="0 0 8 14" fill="none" stroke="#c7c7cc" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M1 1l6 6-6 6"/>
                        </svg>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Home indicator */}
              <div style={{
                background: "#fff",
                display: "flex",
                justifyContent: "center",
                padding: "10px 0 14px",
              }}>
                <div style={{
                  width: "134px", height: "5px",
                  background: "rgba(0,0,0,0.18)",
                  borderRadius: "3px",
                }} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
