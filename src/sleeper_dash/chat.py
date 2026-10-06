"""The weekly league-chat post (Phase 5, owner 2026-10-05): a short message to the league's GroupMe group after each
successful update, through a GroupMe bot. The bot's ID is the one approved secret (CLAUDE.md rule 7): it lives only
in the GitHub Actions secret GROUPME_BOT_ID, is read from the environment when sending, and is never printed or saved.

Run with:
  python -m sleeper_dash.chat preview            # print this week's message (nothing is sent or recorded)
  python -m sleeper_dash.chat claim [--dry-run]  # decide whether to post; record the week first when posting
  python -m sleeper_dash.chat send               # post the claimed message (needs GROUPME_BOT_ID)
  python -m sleeper_dash.chat release            # un-record the week after a failed send, so the next run retries

config.yaml chat.mode decides what the weekly workflow does: "off", "dry-run" (print the message in the run's log
and summary, send nothing, record nothing), or "on". A week is posted at most once: data/chat_posts.csv (committed)
lists the weeks already posted, and a week is recorded and pushed *before* it is sent, so a rerun, the Thursday
run, or a failure part-way can never post it again. If the send fails, `release` removes the record (the run fails
and GitHub emails the owner); if even that fails, the week stays recorded and simply isn't posted.
"""

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from sleeper_dash.config import PROJECT_ROOT

POSTED_PATH = PROJECT_ROOT / "data" / "chat_posts.csv"
MESSAGE_PATH = PROJECT_ROOT / "data" / "cache" / "chat_message.json"  # gitignored; written by claim, read by send
GROUPME_URL = "https://api.groupme.com/v3/bots/post"
SECRET = "GROUPME_BOT_ID"
MAX_LENGTH = 1000  # GroupMe's limit for one message
MODES = ("off", "dry-run", "on")
POSTED_FIELDS = ["season", "week", "posted_at"]


class ChatError(Exception):
    """The post can't be made; the message says why and what to do."""


def check_params(params):
    problems = []
    if params.get("mode") not in MODES:
        problems.append(f"chat.mode must be one of {', '.join(MODES)}")
    if not isinstance(params.get("awards"), list) or not params.get("awards"):
        problems.append("chat.awards must list award keys, in order of preference")
    if not str(params.get("page_url", "")).startswith("https://"):
        problems.append("chat.page_url must be the page's https:// address")
    if problems:
        raise ChatError("config.yaml: " + "; ".join(problems))


# --- The message ------------------------------------------------------------------------------------

def _names(teams):
    return " and ".join(teams)


def _movers(rows, names, direction):
    """'Biggest riser: Team, up 4 to #5'; ties: 'Biggest risers: A (to #2), B (to #6) and C (to #7), up 1 each';
    None when nobody moved that way (e.g. week 1)."""
    moved = rows[rows["rank_change"] * direction > 0]
    if moved.empty:
        return None
    best = int((moved["rank_change"] * direction).max())
    top = moved[moved["rank_change"] * direction == best].sort_values("rank")
    word, label = ("up", "Biggest riser") if direction > 0 else ("down", "Biggest faller")
    if len(top) == 1:
        r = top.iloc[0]
        return f"{label}: {names[r.roster_id]}, {word} {best} to #{int(r['rank'])}"
    each = [f"{names[r.roster_id]} (to #{int(r.rank)})" for r in top.itertuples()]
    return f"{label}s: {', '.join(each[:-1])} and {each[-1]}, {word} {best} each"


def _award_lines(week_awards, names, wanted, how_many=2, captions=True):
    """The first `how_many` awards in chat.awards that were given this week: 'Top score: Team. Put up 168.4, …'
    (without captions: 'Top score: Team')."""
    from sleeper_dash.dashboard.build import award_value

    lines = []
    for award in wanted:
        winners = week_awards[week_awards["award"] == award]
        if winners.empty:
            continue  # e.g. no Heartbreaker in a week without a losing team; the next choice is used
        name = winners["award_name"].iloc[0]
        if len(winners) == 1:
            w = winners.iloc[0]
            lines.append(f"{name}: {names[w.roster_id]}" + (f". {w.caption}" if captions else ""))
        else:
            lines.append(f"{name}: {_names(names[r] for r in winners['roster_id'])}, tied at "
                         f"{award_value(award, winners['value'].iloc[0])}")
        if len(lines) == how_many:
            break
    return lines


def compose(tables, season, params):
    """{"season", "week", "text"} for the latest week of `season`: the top 3, the biggest riser and faller, two
    awards, and the link. Pure: tables in (power_rankings, teams, awards; every season stacked), message out."""
    power = tables["power_rankings"][tables["power_rankings"]["season"] == season]
    if power.empty:
        raise ChatError(f"No power rankings for {season} yet, so there is nothing to post.")
    week = int(power["week"].max())
    rows = power[power["week"] == week].sort_values("rank")
    teams = tables["teams"]
    names = teams[teams["season"] == season].set_index("roster_id")["team_name"].to_dict()
    awards = tables["awards"]
    awards = awards[(awards["season"] == season) & (awards["week"] == week)]

    def text(captions):
        lines = [f"Week {week} power rankings"]
        lines += [f"{int(r.rank)}. {names[r.roster_id]} ({r.power_score:.1f})" for r in rows.head(3).itertuples()]
        lines += [line for line in (_movers(rows, names, 1), _movers(rows, names, -1)) if line]
        lines += _award_lines(awards, names, params["awards"], captions=captions)
        lines.append(f"Full rankings: {params['page_url']}")
        return "\n".join(lines)

    message = text(captions=True)
    if len(message) > MAX_LENGTH:  # never seen: it would take very long team names. Drop the award captions first.
        message = text(captions=False)
    if len(message) > MAX_LENGTH:
        raise ChatError(f"The week {week} message is {len(message)} characters, over GroupMe's {MAX_LENGTH}.")
    return {"season": season, "week": week, "text": message}


# --- Posted weeks (data/chat_posts.csv) -------------------------------------------------------------

def read_posted(path=None):
    path = Path(path or POSTED_PATH)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [{"season": int(r["season"]), "week": int(r["week"]), "posted_at": r["posted_at"]} for r in csv.DictReader(f)]


def write_posted(rows, path=None):
    path = Path(path or POSTED_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=POSTED_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["season"], r["week"])))


def already_posted(season, week, posted):
    """The record that rules this week out, if any: this week, or a later week of the same season, was posted."""
    return next((r for r in posted if r["season"] == season and r["week"] >= week), None)


# --- Steps the workflow runs ------------------------------------------------------------------------

def _summary(markdown):
    """Add to the GitHub Actions run summary when running there (tests clear GITHUB_STEP_SUMMARY)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")


def _output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def claim(message, mode, posted_path=None, message_path=None, now=None):
    """Decide what happens to this week's message. Returns "off", "dry-run", "already-posted", or "send".

    "send" records the week in data/chat_posts.csv (the workflow commits and pushes it before sending) and saves
    the message for `send`. Nothing is recorded in any other case.
    """
    season, week = message["season"], message["week"]
    if mode == "off":
        print("Chat post is off (config.yaml chat.mode). Nothing sent.")
        return "off"
    posted = read_posted(posted_path)
    earlier = already_posted(season, week, posted)
    if earlier:
        print(f"Week {earlier['week']} of {season} was already posted ({earlier['posted_at']}); not posting again.")
        _summary(f"**Chat post:** week {week} already posted ({earlier['posted_at']}); nothing sent.")
        return "already-posted"
    if mode == "dry-run":
        print("DRY RUN: this message would be posted to the league chat; nothing was sent or recorded.\n")
        print(message["text"])
        _summary("**Chat post (dry run, not sent):**\n\n```text\n" + message["text"] + "\n```")
        return "dry-run"
    if not os.environ.get(SECRET):  # check before recording, so a missing secret records nothing
        raise ChatError(f"chat.mode is on but the {SECRET} secret isn't set. Add it on GitHub: Settings → Secrets and "
                        "variables → Actions (docs/RUNBOOK.md section 7), or set chat.mode to dry-run.")
    stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    write_posted(posted + [{"season": season, "week": week, "posted_at": stamp}], posted_path)
    path = Path(message_path or MESSAGE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(message, ensure_ascii=False), encoding="utf-8")
    print(f"Week {week} of {season} recorded as posted; sending next.")
    return "send"


def send(message, bot_id, opener=urllib.request.urlopen):
    """Post the message through the GroupMe bot. Raises ChatError on any failure; the bot ID is never printed."""
    if not bot_id:
        raise ChatError(f"The {SECRET} secret isn't set, so the chat post can't be sent. Add it on GitHub: Settings → "
                        "Secrets and variables → Actions (docs/RUNBOOK.md section 7), or set chat.mode to dry-run.")
    body = json.dumps({"bot_id": bot_id, "text": message["text"]}).encode("utf-8")
    request = urllib.request.Request(GROUPME_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with opener(request, timeout=30) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except (urllib.error.URLError, TimeoutError) as error:
        raise ChatError(f"Couldn't reach GroupMe ({type(error).__name__}); week {message['week']} wasn't posted.") from None
    if status not in (200, 201, 202):
        hint = " The bot ID looks wrong or the bot was deleted." if status in (400, 401, 403, 404) else ""
        raise ChatError(f"GroupMe answered {status}; week {message['week']} wasn't posted.{hint}")
    print(f"Posted week {message['week']} to the league chat.")
    _summary(f"**Chat post:** week {message['week']} posted to the league chat.")


def release(message, posted_path=None):
    """Remove this week's record after a failed send, so the next run tries again."""
    posted = read_posted(posted_path)
    kept = [r for r in posted if not (r["season"] == message["season"] and r["week"] == message["week"])]
    write_posted(kept, posted_path)
    print(f"Week {message['week']} un-recorded; the next run will try to post it again.")


def _current_message(config):
    from sleeper_dash.validate import load_tables

    check_params(config.chat)
    return compose(load_tables(names=["power_rankings", "teams", "awards"]), config.season, config.chat)


def main(argv=None):
    from sleeper_dash.config import load_config

    parser = argparse.ArgumentParser(prog="python -m sleeper_dash.chat", description="The weekly league-chat post.")
    parser.add_argument("step", choices=["preview", "claim", "send", "release"])
    parser.add_argument("--dry-run", action="store_true", help="claim: print the message instead of posting it")
    args = parser.parse_args(argv)
    config = load_config()
    try:
        if args.step == "preview":
            message = _current_message(config)
            print(message["text"])
            print(f"\n({len(message['text'])} characters; chat.mode is {config.chat['mode']})")
        elif args.step == "claim":
            message = _current_message(config)
            outcome = claim(message, "dry-run" if args.dry_run else config.chat["mode"])
            _output("send", "true" if outcome == "send" else "false")
            _output("week", message["week"])
        elif args.step == "send":
            send(json.loads(MESSAGE_PATH.read_text(encoding="utf-8")), os.environ.get(SECRET))
        else:
            release(json.loads(MESSAGE_PATH.read_text(encoding="utf-8")))
    except ChatError as error:
        print(f"CHAT POST FAILED: {error}", file=sys.stderr)
        _summary(f"**Chat post: FAILED.** {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
