"""The weekly league-chat post (src/sleeper_dash/chat.py; owner 2026-10-05): the message, posting each week at most
once (Thursday reruns and repeated runs included), dry-run mode, the GroupMe request, and the workflow job that runs
it. No network: GroupMe is replaced by a fake, and the bot ID is a made-up value set only inside the tests.
"""

import io
import json
import urllib.error
from pathlib import Path

import pandas as pd
import pytest
import yaml

from sleeper_dash import chat
from sleeper_dash.config import PROJECT_ROOT, load_config
from sleeper_dash.transform import PROCESSED_DIR
from sleeper_dash.validate import load_tables
from test_config import VALID, write

PARAMS = {"mode": "dry-run", "awards": ["top_score", "heartbreaker", "blowout"], "page_url": "https://example.test/page/"}
FAKE_BOT = "fake-bot-id-0000"


def league(week=2, heartbreaker=True, names=None):
    """Four teams over two weeks. Week 2: team 3 rises 2 to #1, team 1 falls 2 to #3 (week 1 has no movement)."""
    names = names or {1: "Alpha", 2: "Bravo", 3: "Charlie", 4: "Delta"}
    ranks = {1: {1: 1, 2: 2, 3: 3, 4: 4}, 2: {3: 1, 2: 2, 1: 3, 4: 4}}
    power = pd.DataFrame([{"season": 2026, "week": w, "roster_id": r, "rank": k,
                           "rank_change": float("nan") if w == 1 else ranks[1][r] - k, "power_score": 60.0 - 5 * k}
                          for w in (1, 2) for r, k in ranks[w].items()])
    awards = [{"season": 2026, "week": w, "award": "top_score", "award_name": "Top score", "roster_id": 3, "value": 150.0,
               "caption": "Put up 150.0, the best of the week."} for w in (1, 2)]
    if heartbreaker:
        awards.append({"season": 2026, "week": 2, "award": "heartbreaker", "award_name": "Heartbreaker", "roster_id": 4,
                       "value": 140.0, "caption": "Scored 140.0, 2nd-best of the week, and still lost."})
    awards += [{"season": 2026, "week": 2, "award": "blowout", "award_name": "Blowout", "roster_id": r, "value": 40.0,
                "caption": f"Beat someone by 40.0 (team {r})."} for r in (1, 2)]  # co-winners
    teams = pd.DataFrame({"season": 2026, "roster_id": list(names), "team_name": list(names.values())})
    return {"power_rankings": power[power["week"] <= week], "teams": teams, "awards": pd.DataFrame(awards)}


# --- the message ---------------------------------------------------------------------------------------

def test_the_message_has_the_top_3_the_movers_two_awards_and_the_link():
    message = chat.compose(league(), 2026, PARAMS)
    assert message["season"] == 2026 and message["week"] == 2
    assert message["text"].split("\n") == [
        "Week 2 power rankings",
        "1. Charlie (55.0)", "2. Bravo (50.0)", "3. Alpha (45.0)",
        "Biggest riser: Charlie, up 2 to #1",
        "Biggest faller: Alpha, down 2 to #3",
        "Top score: Charlie. Put up 150.0, the best of the week.",
        "Heartbreaker: Delta. Scored 140.0, 2nd-best of the week, and still lost.",
        "Full rankings: https://example.test/page/",
    ]


def test_week_1_has_no_movers_and_a_missing_award_falls_through_to_the_next_choice():
    first = chat.compose(league(week=1), 2026, PARAMS)["text"]
    assert "Biggest" not in first and first.count("Top score:") == 1
    text = chat.compose(league(heartbreaker=False), 2026, PARAMS)["text"]
    assert "Heartbreaker" not in text
    assert "Blowout: Alpha and Bravo, tied at 40.0" in text    # co-winners share a line, without captions


def test_tied_movers_are_listed_together():
    tables = league()
    tables["power_rankings"].loc[(tables["power_rankings"]["week"] == 2) & (tables["power_rankings"]["roster_id"] == 2),
                                 ["rank_change"]] = 2.0
    assert "Biggest risers: Charlie (to #1) and Bravo (to #2), up 2 each" in chat.compose(tables, 2026, PARAMS)["text"]


def test_a_message_too_long_for_groupme_drops_the_captions_then_stops():
    long = {1: "A" * 110, 2: "B" * 110, 3: "C" * 110, 4: "D" * 110}  # 1,043 characters with captions, 957 without
    text = chat.compose(league(names=long), 2026, PARAMS)["text"]
    assert len(text) <= chat.MAX_LENGTH and "Put up" not in text and "Top score: " + "C" * 110 in text
    with pytest.raises(chat.ChatError, match="over GroupMe's 1000"):
        chat.compose(league(names={r: n * 3 for r, n in long.items()}), 2026, PARAMS)


def test_this_seasons_message_matches_the_saved_tables():
    config = load_config()
    tables = load_tables(PROCESSED_DIR, names=["power_rankings", "teams", "awards"])
    message = chat.compose(tables, config.season, {**config.chat, "page_url": config.dashboard["page_url"]})
    power = tables["power_rankings"][tables["power_rankings"]["season"] == config.season]
    week = power["week"].max()
    names = tables["teams"][tables["teams"]["season"] == config.season].set_index("roster_id")["team_name"]
    top = power[power["week"] == week].sort_values("rank").head(3)
    lines = message["text"].split("\n")
    assert message["week"] == week and lines[0] == f"Week {week} power rankings"
    assert lines[1:4] == [f"{r.rank}. {names[r.roster_id]} ({r.power_score:.1f})" for r in top.itertuples()]
    assert lines[-1] == f"Full rankings: {config.dashboard['page_url']}" and len(message["text"]) <= chat.MAX_LENGTH
    assert sum(line.split(":")[0] in {"Top score", "Heartbreaker", "Blowout", "Bench blunder"} for line in lines) == 2


# --- posting each week at most once ---------------------------------------------------------------------

@pytest.fixture
def paths(tmp_path):
    return {"posted_path": tmp_path / "chat_posts.csv", "message_path": tmp_path / "chat_message.json"}


def message(week=2, season=2026):
    return {"season": season, "week": week, "text": f"Week {week} power rankings"}


def test_off_and_dry_run_send_nothing_and_record_nothing(paths, tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert chat.claim(message(), "off", **paths) == "off"
    assert chat.claim(message(), "dry-run", **paths) == "dry-run"
    assert "DRY RUN" in capsys.readouterr().out and "Week 2 power rankings" in summary.read_text(encoding="utf-8")
    assert not paths["posted_path"].exists() and not paths["message_path"].exists()


def test_on_records_the_week_before_sending_and_never_twice(paths, monkeypatch):
    monkeypatch.setenv(chat.SECRET, FAKE_BOT)
    assert chat.claim(message(), "on", **paths) == "send"
    assert [(r["season"], r["week"]) for r in chat.read_posted(paths["posted_path"])] == [(2026, 2)]
    assert json.loads(paths["message_path"].read_text(encoding="utf-8")) == message()
    # The Thursday run, a manual rerun, or a stat-correction run of the same week: nothing more is sent or recorded.
    assert chat.claim(message(), "on", **paths) == "already-posted"
    assert chat.claim(message(week=1), "on", **paths) == "already-posted"     # an older week, after a later one
    assert chat.claim(message(), "dry-run", **paths) == "already-posted"
    assert len(chat.read_posted(paths["posted_path"])) == 1
    assert chat.claim(message(week=3), "on", **paths) == "send"               # the next week goes out
    assert chat.claim(message(week=1, season=2027), "on", **paths) == "send"  # a new season starts again


def test_on_without_the_secret_stops_before_recording(paths):
    with pytest.raises(chat.ChatError, match="GROUPME_BOT_ID secret isn't set"):
        chat.claim(message(), "on", **paths)
    assert not paths["posted_path"].exists()


def test_release_un_records_only_the_failed_week(paths, monkeypatch):
    monkeypatch.setenv(chat.SECRET, FAKE_BOT)
    for week in (1, 2):
        chat.claim(message(week), "on", **paths)
    chat.release(message(2), paths["posted_path"])
    assert [r["week"] for r in chat.read_posted(paths["posted_path"])] == [1]
    assert chat.claim(message(2), "on", **paths) == "send"                    # so the next run tries again


# --- the GroupMe request ----------------------------------------------------------------------------------

class FakeGroupMe:
    def __init__(self, status=202, error=None):
        self.status, self.error, self.requests = status, error, []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        if self.status >= 400:
            raise urllib.error.HTTPError(request.full_url, self.status, "error", {}, io.BytesIO(b""))
        response = io.BytesIO(b"")
        response.status = self.status
        return response


def test_send_posts_the_text_through_the_bot(capsys):
    groupme = FakeGroupMe()
    chat.send(message(), FAKE_BOT, opener=groupme)
    request = groupme.requests[0]
    assert request.full_url == "https://api.groupme.com/v3/bots/post" and request.get_method() == "POST"
    assert json.loads(request.data) == {"bot_id": FAKE_BOT, "text": "Week 2 power rankings"}
    assert FAKE_BOT not in capsys.readouterr().out                            # the secret is never printed


@pytest.mark.parametrize("groupme, words", [
    (FakeGroupMe(status=404), "GroupMe answered 404; week 2 wasn't posted. The bot ID looks wrong"),
    (FakeGroupMe(status=500), "GroupMe answered 500"),
    (FakeGroupMe(error=urllib.error.URLError("down")), "Couldn't reach GroupMe"),
])
def test_a_failed_send_says_why_without_the_secret(groupme, words):
    with pytest.raises(chat.ChatError, match=words) as raised:
        chat.send(message(), FAKE_BOT, opener=groupme)
    assert FAKE_BOT not in str(raised.value)
    with pytest.raises(chat.ChatError, match="secret isn't set"):
        chat.send(message(), None, opener=groupme)


# --- settings and the workflow ----------------------------------------------------------------------------

def test_the_chat_settings_are_checked(tmp_path):
    assert load_config(write(tmp_path, VALID)).chat == {"mode": "off"}        # no section: off
    assert load_config().chat["mode"] in chat.MODES
    for bad in ("chat:\n  mode: off\n", "chat:\n  mode: maybe\n"):            # a bare off reads as false
        with pytest.raises(ValueError, match="chat.mode"):
            load_config(write(tmp_path, VALID + bad))
    with pytest.raises(chat.ChatError, match="chat.awards"):
        chat.check_params({"mode": "on", "awards": [], "page_url": "https://x"})


def test_the_workflow_posts_only_after_publishing_and_records_before_sending():
    workflow = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "weekly.yml").read_text(encoding="utf-8"))
    post = workflow["jobs"]["post"]
    assert post["needs"] == ["build", "deploy"] and post["permissions"] == {"contents": "write"}
    steps = {s.get("name"): s for s in post["steps"]}
    order = [s.get("name") for s in post["steps"]]
    assert order.index("Record the week before sending") < order.index("Send to the league chat")
    assert steps["Record the week before sending"]["if"] == "steps.claim.outputs.send == 'true'"
    assert steps["Un-record after a failed send"]["if"] == "failure() && steps.send.outcome == 'failure'"
    secret = "${{ secrets.GROUPME_BOT_ID }}"
    uses_secret = [s.get("name") for job in workflow["jobs"].values() for s in job["steps"]
                   if secret in json.dumps(s.get("env", {}))]
    assert uses_secret == ["Chat post (decide)", "Send to the league chat"]   # nowhere else, and never in `run`
    assert all(secret not in s.get("run", "") for job in workflow["jobs"].values() for s in job["steps"])
