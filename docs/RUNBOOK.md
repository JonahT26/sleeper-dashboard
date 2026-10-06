# Runbook: when the weekly update looks wrong

For the owner, on a Tuesday morning. Everything here works from a web browser signed in to GitHub as JonahT26. Where a command is shown, it's an alternative: run it in PowerShell from the project folder (`cd "C:\Personal Projects\FF\Dev"` first).

**Links:** [live page](https://jonaht26.github.io/sleeper-dashboard/) · [Actions tab](https://github.com/JonahT26/sleeper-dashboard/actions) (every run, and the buttons below)

**The one thing to remember:** a failed run never publishes. The last good page stays live, so a failure is never an emergency.

---

## 1. Did this week's update work?

The update runs every **Tuesday and Thursday at 12:17 PM Eastern**. GitHub often starts it late, sometimes by an hour, so don't worry before about 1:30 PM. It takes about 4 minutes (it rebuilds every season since 2020).

Three checks, in order:

1. **The page.** Open the live page. The bar at the top should say **"Updated Tue …"** with today's date, and the heading should be the new week (e.g. "Week 4 power rankings").
2. **Your email.** GitHub emails you only when a run fails. No email is good news.
3. **The run.** On the Actions tab, the newest **Weekly refresh** run should have a green tick. Open it: the summary at the top says **"Latest completed week: 4 (new: the last run ended at week 3)"** and, at the bottom, **"Published: …"**.

Or list the last five runs:

```powershell
gh run list --workflow weekly.yml --limit 5
```

| What you see | What it means | What to do |
|---|---|---|
| Green tick, page shows the new week | It worked | Nothing |
| Green tick, but the summary says **"no new completed week since the last run"** on a Tuesday | Sleeper hadn't finished scoring Monday night's game when the run started. Not a failure | Re-run in a few hours (section 3). Thursday's run picks it up anyway |
| Red X, or a failure email | The run stopped. The page still shows the last good version | Section 2 |
| No run today, after about 2 PM | The schedule is paused (by you, or by GitHub after 60 days without new data), or GitHub is having problems | Open Weekly refresh on the Actions tab. A banner saying the workflow is disabled means it's paused: section 5. Otherwise run it by hand (section 3) |
| The page says **"The latest rankings are from week N. Next update due …"** | The page hasn't updated in more than 8 days | Look at the last few runs (check 3) and go to section 2 |

---

## 2. When a run fails

**Where to look:** click the link in the failure email, or open the red run on the Actions tab. The summary at the top says **"Build: FAILED"** and lists each step's result. The first step marked `failure` is the one that matters. Click it in the left-hand list to see its log; the reason is usually in the last 20 lines. (Summaries and logs show only when you're signed in.)

| Step that failed | What it usually means | What to do |
|---|---|---|
| **Install** | GitHub couldn't download Python or a package. Usually a temporary outage | Re-run (section 3). If it fails twice, ask Claude |
| **Tests (committed tables)** | Something in the project itself is broken, usually after a code change. Nothing to do with Sleeper | Ask Claude |
| **Pipeline**, and the log says **"Gave up on …"** or mentions a connection or timeout | Sleeper's site was down or slow | Re-run in an hour |
| **Pipeline**, and the log says **"validation"** and names a check (e.g. "Records match Sleeper") | Sleeper's numbers didn't add up the way the checks expect. Usually Sleeper was mid-way through a stat correction, or Sleeper changed how it reports something. The check's detail starts with the season it failed in (e.g. "2023: …"): every season since 2020 is checked on every run | Re-run once in a few hours. If it fails the same way, ask Claude. If the season named is a past one, the live page is unaffected and nothing urgent is wrong |
| **Pipeline**, and the log says **"has no completed week yet"** | The settings were switched to a new season before its week 1 was scored (season rollover done too early). The last page, last season's final rankings, stays live | Ask Claude to put the previous season back in `config.yaml`, or simply wait: the switch is planned for the Tuesday after week 1 (Claude's scheduled check, Sep 14, 2027) |
| **Pipeline**, any other message (e.g. "missing", a config setting) | A settings problem, most likely around the start of a new season | Ask Claude |
| **Dashboard** | The page couldn't be built | Ask Claude |
| **Page tests (this run's tables)** | The built page didn't match the data, so it wasn't published. A bug | Ask Claude |
| **Commit refreshed tables** | Saving the new tables to GitHub clashed with another change made at the same moment | Re-run |
| **deploy** (second job) | GitHub Pages had a hiccup while publishing | Re-run |

**Asking Claude Code.** Open Claude Code in the project and paste this, with the run's link:

```text
The Weekly refresh run failed: <paste the run's link>. Read docs/HANDOFF.md and docs/RUNBOOK.md, then read that run's log with gh. Tell me in plain language which step failed, why, and whether the live page is affected. Don't change any code, data, or settings until I approve a fix.
```

If Tuesday's run worked but found no new week, and it's still missing later in the day:

```text
Tuesday's Weekly refresh succeeded but reports no new completed week. Check Sleeper's league and NFL state and tell me whether week <N> has been scored yet and when I should re-run. Don't change anything.
```

If the page published numbers that look wrong:

```text
The live page shows <what looks wrong, e.g. "Team X's record is 3–1 but Sleeper says 2–2">. Compare the page with the tables in data/processed/ and with Sleeper, and explain the difference. Don't change anything until I approve.
```

---

## 3. Run the update by hand

It's safe to run at any time. It does the same full refresh as the schedule, saves tables only if something changed, and publishes only if every check passes.

On the Actions tab: click **Weekly refresh** in the left-hand list → the **Run workflow** button on the right → leave the branch as **main** → green **Run workflow**. Refresh the page after a few seconds to see the new run. It takes about 4 minutes.

Or:

```powershell
gh workflow run weekly.yml --ref main
```

---

## 4. Put last week's page back (rollback)

Use this when the update published something wrong and you want the previous page up while it's looked into. It changes only the live page: the data and the code are untouched.

1. **Find the good run's ID.** On the Actions tab, click **Weekly refresh** and open the run that published the page you want back (e.g. last Thursday's). Its web address ends in `/actions/runs/37135777461`; that number is the run ID. Or list recent runs (the ID is the long number):
   ```powershell
   gh run list --workflow weekly.yml --limit 10
   ```
2. **Run the rollback.** Actions tab → **Roll back the live page** → **Run workflow** → paste the run ID → **Run workflow**. About a minute. Its summary says which week and "Updated" time it put back. Or:
   ```powershell
   gh workflow run rollback.yml --ref main -f run_id=RUN_ID
   ```
3. **Pause the schedule (section 5)** if the rollback should stay up. Otherwise the next Tuesday or Thursday run publishes fresh numbers again. Don't run Weekly refresh by hand either.

To undo the rollback, run Weekly refresh (section 3).

Good to know:
- The restored page keeps its original "Updated" time, so after 8 days it shows the stale-data line. That's accurate.
- Each published page is kept for 90 days. The oldest page you can restore is week 3's, from the Weekly refresh run on Sat Oct 3, 2026 at 12:19 PM ET (run ID `37136344876`). Pages from runs before it expired after a day.

---

## 5. Pause or resume the schedule

**Pause:** Actions tab → **Weekly refresh** → the **···** menu at the top right → **Disable workflow**. Or:

```powershell
gh workflow disable weekly.yml
```

While it's paused, nothing runs, the Run workflow button disappears, and the live page stays as it is. After 8 days the page says it's out of date.

**Resume:** Actions tab → **Weekly refresh** → **Enable workflow** in the banner. Or:

```powershell
gh workflow enable weekly.yml
```

GitHub pauses the schedule by itself after 60 days without new data (expected in the off-season). Resume it the same way before the next season. Whoever resumes it receives the failure emails from then on.

---

## 6. Update the pinned dependencies

Python and every package are pinned to exact versions, so GitHub runs exactly what was tested and nothing changes by surprise. Updating is a planned job for a quiet week, after a Thursday run, not a Tuesday-morning fix. The exception is a failure that is clearly about a package, such as the **Install** step failing because a version can't be found.

Ask Claude Code:

```text
Update the pinned dependencies: <which package and version, or "check what's out of date and recommend what's worth updating">. Follow docs/CODEBASE.md "Dependencies". Show me which versions change, run all the tests and the pipeline, confirm the tables and the page come out the same, then commit, push, and run the Weekly refresh once to prove it works on GitHub.
```

Heads-up: GitHub moves its machines to Ubuntu 26 from **October 19, 2026**. If the first run after that fails at **Install** or while setting up Python, that's the likely reason. Use the failure prompt in section 2.
