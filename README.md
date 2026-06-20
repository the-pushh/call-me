# call-me 📞

Ever wanted to *actually* call someone who isn't real and have a genuine, real-time conversation? That's this project.

`call-me` rings your phone, and on the other end is an AI persona — like **Eve**, a Led Zeppelin-loving, slightly chaotic friend who talks like she's texting you out loud. You talk, she listens, she thinks, she talks back — live, so it feels like a real phone call instead of a slow chatbot back-and-forth. The screen even looks like your iPhone's call screen while it's happening.

It feels alive because everything streams: as soon as she's said one sentence, the next is already on its way — no waiting for a wall of text, just a conversation.

## Try it

Head to **[callme.thepushh.com](https://callme.thepushh.com)**, pick a persona, drop in your number, and pick up when it rings.

## What's inside

- **`backend/`** — the engine room: takes the call, listens to you, figures out what to say in character, and says it back, all in real time.
- **`frontend/`** — the iPhone-style call screen you use to start a call and watch it unfold.

## How a call flows

```
you talk → phone → Twilio → backend
   listen → detect you stopped → transcribe → think (in character) → speak
backend → Twilio → phone → you hear the reply
```

Each sentence is spoken the moment it's ready, while the next one is still being written — that overlap is what kills the lag.

## Tech stack

**The call itself**
- **Twilio** — places the real phone call and streams audio both ways over a WebSocket.

**The voice pipeline** (backend, Python)
- **FastAPI + Uvicorn** — the server, with WebSockets carrying the live audio.
- **Silero VAD** — listens for when *you* stop talking, so the bot knows it's its turn.
- **Whisper** (`large-v3-turbo`, via OpenRouter) — turns your speech into text.
- **Llama 3.1 8B** (via OpenRouter) — the "brain" that writes in-character replies sentence by sentence.
- **Cartesia** — the primary voice (TTS); streams phone-ready audio with no conversion step.
- **Kokoro** (via OpenRouter) — the always-on backup voice if Cartesia hiccups.

**The screen** (frontend)
- **Next.js + React + TypeScript**, styled with **Tailwind**, with a live WebSocket feed so the transcript appears as the call happens.

**Where it runs**
- Backend on **Google Cloud Run** (behind a load balancer, secrets in Secret Manager, deploys via Cloud Build).
- Frontend on **Vercel**.