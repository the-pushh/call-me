# call-me 📞

Ever wanted to *actually* call someone who isn't real and have a genuine, real-time conversation? That's this project.

`call-me` dials a real phone number with Twilio, and on the other end is an AI persona — right now it's **Eve**, a Led Zeppelin-loving, slightly chaotic friend who talks like she's texting you out loud. You talk, she listens, she thinks, she talks back — all streamed live so it feels like an actual phone call, not a slow chatbot ping-pong match. The frontend even looks like you're staring at your iPhone's call screen while it happens.

Under the hood it's a full voice AI pipeline: your voice gets transcribed (STT), fed to an LLM brain that writes in-character replies sentence by sentence, and spoken back (TTS) — fast enough that the *next* sentence is already being generated while the *current* one is still playing. That's what makes it feel alive instead of laggy.

## What's inside

- **`backend/`** — FastAPI server. Handles the Twilio call, streams audio both ways, runs speech-to-text, voice activity detection, the LLM "brain," and text-to-speech.
- **`frontend/`** — Next.js app styled like an iPhone call screen, so triggering and watching a call feels native.

## Run it locally

You'll need a [Twilio](https://www.twilio.com/) account (for the phone call) and an [OpenRouter](https://openrouter.ai/) API key (for the LLM brain).

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in `backend/` with:

```
TWILLIO_SID=your_twilio_account_sid
TWILLIO_AUTH_TOKEN=your_twilio_auth_token
FROM_NUMBER=your_twilio_phone_number
PUBLIC_BASE_URL=your_public_https_url
OPENROUTER_API_KEY=your_openrouter_key
```

`PUBLIC_BASE_URL` needs to be a publicly reachable HTTPS URL (e.g. via [ngrok](https://ngrok.com/)) so Twilio can reach your machine.

Then start the server:

```bash
uvicorn main:app --reload
```

Want to chat with the persona without any phone call or audio at all? Just run:

```bash
python brains.py
```

### Frontend

```bash
cd frontend
bun install   # or npm install
bun dev       # or npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to see the call screen.
