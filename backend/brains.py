import threading
import re
import queue
from openai import OpenAI
import config

# LLM Setup -------------------------------

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=config.OPENROUTER_API_KEY
)

MODEL = "meta-llama/llama-3.1-8b-instruct"
PROVIDER_OPTS = {"sort": "throughput"}
PERSONAS = {
    "eve": "personas/eve.md",
    "siddhartha": "personas/siddhartha.md",
    "jeremiah": "personas/jeremiah.md",
    "billie": "personas/billie.md",
    "avni": "personas/avni.md"
}

def _load_persona(path):
    with open(path) as f:
        return f.read()

# Input Cleaning: required because input text is coming from the transcript and may contain junk on silence ------------------------

SILENCE_ARTIFACTS = ["", "[blank_audio]", "(silence)", "[silence]", "...", ".", "thank you.", "thanks for watching"]

def clean_stt(text):
    """Clean the input signal to get rid of noise"""
    if text is None:
        return None
    t = text.strip()
    if not t:
        return None
    if t.lower() in SILENCE_ARTIFACTS:
        return None
    return t

# Sentence boundry detection so that a sentence can be detected an stream as soon as completed and not wait for the whole deal

_TERMINAL = re.compile(r'(.+?[.!?]+["\')\]]*)(\s+|$)', re.DOTALL)
_EAGER = re.compile(r'(.+?[.!?,\u2014]+["\')\]]*)(\s+|$)', re.DOTALL)


# The main brain class

class Brain:
    def __init__(self, persona="eve", model=MODEL, max_turns=10, soft_limit=240):
        self.model = model
        self.max_turns = max_turns # this is the memory for the call last <max_turns> turns context is remembered
        self.soft_limit = soft_limit # chars before forced safety flush
        self.persona = persona
        self.system_prompt = _load_persona(PERSONAS[persona])
        self.messages = [{"role": "system", "content": self.system_prompt}] # keeps system prompt at index 0 for context of the model. Also this list will be used to store the history of conversation

    def switch_persona(self, name, keep_history=False):
        self.system_prompt = _load_persona(PERSONAS[name])
        self.persona = name
        if keep_history:
            self.messages[0] = {"role": "system", "content": self.system_prompt}
        else:
            self.messages = [{"role": "system", "content": self.system_prompt}]

    def reset(self):
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def add_assistant_message(self, text):
        """Record something the bot said WITHOUT generating it (e.g. the spoken
        greeting), so it becomes part of the history the model sees next turn."""
        if text and text.strip():
            self.messages.append({"role": "assistant", "content": text.strip()})

    def _trim_history(self):
        """Keep the system prompt + the most recent max_turns exchanges.

        helps in cost and latency. Note the list-building: [system_msg] is a
        one-item list we ADD to the recent slice. Writing system_msg + slice
        (without the brackets) would try to add a dict to a list and crash.
        """
        max_msgs = 1 + self.max_turns * 2
        if len(self.messages) > max_msgs:
            self.messages = [self.messages[0]] + self.messages[-(self.max_turns * 2):]

    def _force_cut(self, buffer):
        """if the model generates longer sentence without any punctations then we deliberately break it to stream and keep the voice flowing"""
        window = buffer[:self.soft_limit]
        idx = max(window.rfind(". "), window.rfind("\u2014 "), window.rfind(" "))
        if idx <= 0:
            return None
        return buffer[:idx + 1].strip(), buffer[idx + 1:]


    # Real brains
    def respond(self, user_text, stop_event=None, eager_first=True):
        """Generator"""
        cleaned = clean_stt(user_text)
        if cleaned is None:
            return

        self.messages.append({"role": "user", "content": cleaned})
        self._trim_history()

        stream = client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            extra_body={"provider": PROVIDER_OPTS},
            stream=True
        )

        buffer = ""
        full = ""
        yielded = []
        first_sent = False
        interrupted = False

        for chunk in stream:
            if stop_event is not None and stop_event.is_set():
                interrupted = True
                break

            if not chunk.choices:
                continue
            
            delta = chunk.choices[0].delta.content
            if not delta:
                continue

            buffer += delta
            full += delta

            while True:
                pattern = _EAGER if (eager_first and not first_sent) else _TERMINAL
                m = pattern.match(buffer)
                if not m:
                    break
                chunk_text = m.group(1).strip()
                buffer = buffer[m.end():]
                if chunk_text:
                    first_sent = True
                    yielded.append(chunk_text)
                    yield chunk_text

                if len(buffer) > self.soft_limit:
                    cut = self._force_cut(buffer)
                    if cut:
                        chunk_text, buffer = cut
                        if chunk_text:
                            first_sent = True
                            yielded.append(chunk_text)
                            yield chunk_text

        if not interrupted:
            tail = buffer.strip()
            if tail:
                yielded.append(tail)
                yield tail

        if interrupted:
            spoken = " ".join(yielded).strip()
            if spoken:
                self.messages.append({"role": "assistant", "content": spoken })
            else:
                self.messages.pop()
        else:
            self.messages.append({"role": "assistant", "content": full.strip()})

    def respond_async(self, user_text, stop_event=None, eager_first=None):
        """Returns a queue.Queue. Sentences arrive on it as they're ready;
            a None sentinel marks the end. The LLM runs in a BACKGROUND THREAD,
            so it keeps generating sentence N+1 while your main thread is busy
            playing sentence N through TTS. THIS is what makes it feel real-time
            rather than stop-start.

            Consume it like:
            q = brain.respond_async(text)
            while True:
                s = q.get()
                if s is None:
                    break
                tts.speak(s)        # blocking is fine — producer runs separately
        """
        q = queue.Queue()

        def producer():
            try:
                for sentence in self.respond(user_text, stop_event=stop_event, eager_first=eager_first):
                    q.put(sentence)
            except Exception as e:
                q.put(("__error__", str(e)))
            finally:
                q.put(None)

        threading.Thread(target=producer, daemon=True).start()
        return q


# ---------------------------------------------------------------------------
# STANDALONE TEXT CHAT — run `python brains.py` to talk to the persona with no
# audio at all. Best way to judge whether the character feels real before you
# wire in STT/TTS. Watch the sentences appear one at a time: that's the same
# stream your TTS will consume.
# ---------------------------------------------------------------------------


# if __name__ == "__main__":
#     import time
#     import queue
#     import threading
 
#     brain = Brain(persona="eve")
#     print(f"chatting with {brain.persona}  (ctrl-c to quit)\n")
 
#     SPEAKING_RATE = 2.5  # rough words/sec for a TTS voice — tune to taste
#     session_stats = []  # one entry per turn: {"ttft": float, "stalls": [float]}
 
#     while True:
#         try:
#             user = input("you: ")
#         except (EOFError, KeyboardInterrupt):
#             print()
#             break
 
#         start = time.time()
#         q = queue.Queue()
 
#         def producer():
#             for sentence in brain.respond(user):
#                 q.put((time.time() - start, sentence))
#             q.put(None)
 
#         threading.Thread(target=producer, daemon=True).start()
 
#         print("her: ", end="", flush=True)
#         ttft = None
#         tts_finish = 0.0
#         stalls = []
 
#         while True:
#             item = q.get()
#             if item is None:
#                 break
#             ready_at, sentence = item
 
#             if ttft is None:
#                 ttft = ready_at  # time to first chunk being ready at all
 
#             # if this chunk wasn't ready by the time the previous one
#             # finished "playing", that gap is an audible stall
#             stall = max(0.0, ready_at - tts_finish)
#             if stall > 0:
#                 stalls.append(stall)
#                 time.sleep(stall)
 
#             print(sentence, end=" ", flush=True)
 
#             dur = len(sentence.split()) / SPEAKING_RATE
#             time.sleep(dur)
#             tts_finish = time.time() - start
 
#         print("\n")
#         session_stats.append({"ttft": ttft, "stalls": stalls})
 
#     # ---- printed only on exit ----
#     if session_stats:
#         def pct(lst, p):
#             if not lst:
#                 return None
#             s = sorted(lst)
#             idx = max(0, round(p / 100 * len(s)) - 1)
#             return s[idx]
 
#         ttfts = [s["ttft"] for s in session_stats if s["ttft"] is not None]
#         all_stalls = [g for s in session_stats for g in s["stalls"]]
 
#         print("=" * 50)
#         print("SESSION STATS")
#         print("=" * 50)
#         print(f"turns: {len(session_stats)}")
#         p50, p90 = pct(ttfts, 50), pct(ttfts, 90)
#         print(f"TTFT        p50={p50:.2f}s  p90={p90:.2f}s")
#         if all_stalls:
#             p50s, p90s = pct(all_stalls, 50), pct(all_stalls, 90)
#             print(f"mid-reply stalls  p50={p50s:.2f}s  p90={p90s:.2f}s  "
#                   f"({len(all_stalls)} total — audible pauses)")
#         else:
#             print("mid-reply stalls: none — generation always stayed ahead of playback")