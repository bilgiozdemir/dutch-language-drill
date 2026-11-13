#!/usr/bin/env python3
"""Dutch A1 spaced-repetition drill for Telegram, designed to run on GitHub Actions.

Modes:  lesson  - morning: send today's 10 words (Dutch, pronunciation, English)
        quiz    - evening: quiz today's words as Telegram quiz polls
        weekly  - Sunday: mini-test built from the words missed this week
        collect - only read your answers and update progress
Every mode reads new answers first. Progress lives in state.json.
"""
import csv
import html
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
WORDS_FILE = ROOT / "words.csv"
STATE_FILE = ROOT / "state.json"
TZ = ZoneInfo("Europe/Amsterdam")
DAILY_COUNT = 10
WEEKLY_MAX = 15
INTERVALS = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}   # Leitner box -> days until next review
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DRY_RUN = os.environ.get("DRY_RUN") == "1"     # print instead of calling Telegram
_fake_id = [1000]


def today() -> date:
    return datetime.now(TZ).date()


# ---------- Telegram ----------
def api(method: str, **params):
    if DRY_RUN:
        if method == "getUpdates":
            f = os.environ.get("FAKE_UPDATES")
            return json.loads(Path(f).read_text()) if f and Path(f).exists() else []
        print(f"[dry-run] {method}: {json.dumps(params, ensure_ascii=False)[:300]}")
        _fake_id[0] += 1
        return {"poll": {"id": str(_fake_id[0])}}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Telegram error on {method}: {e.read().decode()}")
    if not body.get("ok"):
        raise SystemExit(f"Telegram error on {method}: {body}")
    return body["result"]


def send(state, text):
    api("sendMessage", chat_id=state["chat_id"], text=text, parse_mode="HTML")


# ---------- data ----------
def load_words():
    with open(WORDS_FILE, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="|"))
    return {r["dutch"]: r for r in rows if r.get("dutch")}


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"chat_id": None, "offset": 0, "cards": {}, "today": {"date": "", "ids": []},
            "polls": {}, "missed": [], "streak": {"last": "", "days": 0}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------- reading answers ----------
def grade(state, info, chosen):
    correct = chosen == info["correct"]
    wid = info["word"]
    if info["kind"] == "daily":
        card = state["cards"].setdefault(wid, {"box": 0, "due": ""})
        card["box"] = min(card["box"] + 1, 5) if correct else 1
        card["due"] = (today() + timedelta(days=INTERVALS[card["box"]])).isoformat()
        t = today().isoformat()
        if state["streak"]["last"] != t:
            yesterday = (today() - timedelta(days=1)).isoformat()
            state["streak"]["days"] = state["streak"]["days"] + 1 if state["streak"]["last"] == yesterday else 1
            state["streak"]["last"] = t
    if not correct and wid not in state["missed"]:
        state["missed"].append(wid)


def collect(state):
    env_chat = os.environ.get("TELEGRAM_CHAT_ID")
    if env_chat:
        state["chat_id"] = int(env_chat)
    updates = api("getUpdates", offset=state["offset"], timeout=0,
                  allowed_updates=["message", "poll_answer"])
    for u in updates:
        state["offset"] = max(state["offset"], u["update_id"] + 1)
        if "message" in u and state["chat_id"] is None:
            state["chat_id"] = u["message"]["chat"]["id"]   # first chat to write to the bot owns it
            send(state, "Hoi! 👋 Your Dutch drill is connected. Words arrive every morning, "
                        "the quiz every evening, and a mini-test on Sunday.")
        elif "poll_answer" in u:
            pa = u["poll_answer"]
            info = state["polls"].pop(pa["poll_id"], None)
            if info and pa.get("option_ids"):
                grade(state, info, pa["option_ids"][0])
    cutoff = (today() - timedelta(days=8)).isoformat()
    state["polls"] = {k: v for k, v in state["polls"].items() if v["sent"] >= cutoff}


# ---------- choosing words ----------
def ensure_today(state, words):
    t = today().isoformat()
    if state["today"]["date"] == t:
        return [w for w in state["today"]["ids"] if w in words]
    due = sorted((w for w, c in state["cards"].items() if w in words and c["due"] <= t),
                 key=lambda w: (state["cards"][w]["due"], state["cards"][w]["box"]))
    ids = due[:DAILY_COUNT]
    for w in words:                      # fill up with new words, in file order
        if len(ids) >= DAILY_COUNT:
            break
        if w not in state["cards"]:
            state["cards"][w] = {"box": 0, "due": t}
            ids.append(w)
    state["today"] = {"date": t, "ids": ids}
    return ids


def send_poll(state, words, wid, kind, reverse=False):
    """reverse=False: Dutch -> English.  reverse=True: English -> Dutch."""
    w = words[wid]
    ask, ans = ("english", "dutch") if reverse else ("dutch", "english")
    pool = list({x[ans] for x in words.values() if x[ans] != w[ans]})
    options = random.sample(pool, 3) + [w[ans]]
    random.shuffle(options)
    correct = options.index(w[ans])
    expl = f"{w['dutch']} [{w['pron']}] = {w['english']}"
    if w["example"]:
        expl += f"\n{w['example']} — {w['example_en']}"
    question = (f"How do you say in Dutch: {w['english']}" if reverse
                else f"What does this mean?  {w['dutch']}  [{w['pron']}]")
    res = api("sendPoll", chat_id=state["chat_id"], question=question[:300],
              options=[{"text": o[:100]} for o in options], type="quiz",
              correct_option_id=correct, is_anonymous=False, explanation=expl[:200])
    state["polls"][res["poll"]["id"]] = {"word": wid, "correct": correct, "kind": kind,
                                         "sent": today().isoformat()}
    time.sleep(0 if DRY_RUN else 0.4)


# ---------- modes ----------
def lesson(state, words):
    ids = ensure_today(state, words)
    if not ids:
        return send(state, "🎉 Nothing due today and no new words left. Add more rows to words.csv!")
    lines = [f"🇳🇱 <b>Dutch for {today():%A %d %B}</b>\n"]
    for i, wid in enumerate(ids, 1):
        w = words[wid]
        tag = " 🆕" if state["cards"][wid]["box"] == 0 else ""
        lines.append(f"{i}. <b>{html.escape(w['dutch'])}</b>{tag}\n"
                     f"    🔊 {html.escape(w['pron'])}\n    → {html.escape(w['english'])}")
        if w["example"]:
            lines.append(f"    <i>{html.escape(w['example'])}</i> — {html.escape(w['example_en'])}")
    learned = sum(1 for c in state["cards"].values() if c["box"] >= 3)
    lines.append(f"\n🔥 Streak: {state['streak']['days']} days · ✅ {learned}/{len(words)} words solid"
                 f"\nQuiz comes this evening.")
    send(state, "\n".join(lines))


def quiz(state, words):
    ids = ensure_today(state, words)
    if not ids:
        return
    send(state, f"🧠 <b>Evening quiz</b> — {len(ids)} questions. Tap the right meaning.")
    for wid in random.sample(ids, len(ids)):
        send_poll(state, words, wid, "daily")


def weekly(state, words):
    missed = [w for w in state["missed"] if w in words][:WEEKLY_MAX]
    state["missed"] = []                 # wrong answers in this test go back on the list
    if not missed:
        return send(state, "🏆 <b>Weekly test</b>: you missed nothing this week. Goed gedaan!")
    send(state, f"📝 <b>Weekly mini-test</b> — the {len(missed)} words you missed this week, "
                f"this time English → Dutch.")
    for wid in random.sample(missed, len(missed)):
        send_poll(state, words, wid, "weekly", reverse=True)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "collect"
    if not TOKEN and not DRY_RUN:
        raise SystemExit("Set the TELEGRAM_BOT_TOKEN secret first.")
    words, state = load_words(), load_state()
    collect(state)
    if mode != "collect":
        if state["chat_id"] is None:
            me = api("getMe") if not DRY_RUN else {}
            print(f"No chat yet. This token belongs to the bot @{me.get('username')}. "
                  f"Open exactly that bot in Telegram, send /start, then run again.")
        else:
            {"lesson": lesson, "quiz": quiz, "weekly": weekly}[mode](state, words)
    save_state(state)


if __name__ == "__main__":
    main()
