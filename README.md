# Pipeline Attribution

Every GTM org eventually asks "which plays actually sourced pipeline". This engine answers it with no black box: every dollar of credit is a row that names the touch_id that earned it, the opportunity it came from, the model that assigned it, and the exact weight.

The thesis: an attribution number nobody can audit is a number nobody should move budget on. So the models are simple rules with the math in plain sight, the report shows all three side by side, and a small rule table turns the numbers into "do more of this, less of that" with the rule that fired printed next to each line.

## How it works

```
touches.csv ───────┐
  (touch_id, account, timestamp,        ┌──────────────── SQLite ─────────────────┐
   play, channel, cost)                 │ touchpoints   (upsert by touch_id)      │
                   ├─► ingest ─────────►│ opportunities (upsert by opp_id)        │
opportunities.csv ─┘                    │ attributions  (rebuilt: 1 row per       │
  (opp_id, account, created_at,         │               model x opp x touch_id)   │
   amount)                              └───────────────────┬─────────────────────┘
                                                            │
                         attribute: first-touch, last-touch, position-based
                                                            │
                         readout:  per-play table ─► three-model comparison
                                   ─► rule table (more / less / hold / keep)
                                   ─► before/after narrative ─► credit ledger
                                                            │
                                                       report.md
```

1. **Ingest** a touchpoint stream and the opportunities it produced. Plays are normalized (`Paid Search` and `paid-search` both become `paid_search`). Malformed rows are skipped with a stderr warning, never fatal.
2. **Attribute** every opportunity under all three models at once and store each credit as its own row. Attributions are a pure function of touches and opportunities, so they are rebuilt in one transaction on every ingest.
3. **Report** under the model you pick: touches, cost, pipeline credited, cost per pipeline dollar, a role for each play, a verdict, and a ledger listing each opportunity's touch path with every touch's share.

## The three models (all of the math)

For an opportunity with amount `A` created at time `C`, the eligible path is that account's touches with `C - lookback <= timestamp <= C` (default lookback 90 days), ordered by `(timestamp, touch_id)`. Call them `t_1 .. t_n`. Every model is a weight vector with `sum(w_i) = 1`, and `credit(t_i) = A * w_i`.

| Model | Weights | What it answers |
|---|---|---|
| First-touch | `w_1 = 1`, all others 0 | Which play opened the conversation? |
| Last-touch | `w_n = 1`, all others 0 | Which play was there when it converted? |
| Position-based | `n = 1`: `w_1 = 1`. `n = 2`: `1/2, 1/2`. `n >= 3`: `w_1 = w_n = 2/5`, each middle `w_i = (1/5) / (n - 2)` | Credit the opener and the closer, and pay the assists something |

Worked example, a $100,000 opportunity with path outbound, outbound, website visit, paid search, paid search:

| Touch | First-touch | Last-touch | Position-based |
|---|---|---|---|
| t1 outbound | $100,000 | | 40% = $40,000 |
| t2 outbound | | | 6.67% = $6,667 |
| t3 website | | | 6.67% = $6,667 |
| t4 paid search | | | 6.67% = $6,667 |
| t5 paid search | | $100,000 | 40% = $40,000 |

Weights are exact `Fraction`s (stored as text like `1/15`), so they sum to exactly 1 and no rounding dollar goes missing. Zero-weight touches are not stored. An opportunity with no touches in the window is reported as **unattributed** rather than guessed at. All of it lives in `src/pipeline_attribution/attribution.py`, about 60 lines.

## The readout rule table

Verdicts, first match wins, evaluated under the selected model (`rules.py`). "Blended" is total spend divided by total attributed pipeline.

| Rule | Condition | Verdict |
|---|---|---|
| R1 undercounted | First- or last-touch view, play has spend, position-based credits it at least 1.5x more | Hold: do not cut on this view |
| R2 no-pipeline | Spend > 0, $0 credited | Less |
| R3 organic | No spend (website visits, demo requests) | Keep: route fast, nothing to reallocate |
| R4 efficient | Cost per pipeline $ at or under 0.5x blended | More |
| R5 expensive | Cost per pipeline $ at or above 2x blended | Less |
| R6 in-range | Anything else | Hold |

Roles compare first-touch and last-touch share of pipeline, so a play keeps its role whichever model the report uses: **Sourcer** (first share at least 5% and at least 1.5x last), **Closer** (the mirror image), **Assist** (position-based share beats both), otherwise **Balanced**.

R1 exists because of the mistake this project is built to catch: on a last-touch view, sourcing plays show $0 and look like the first thing to cut.

## Demo

```bash
python3 -m venv .venv && .venv/bin/pip install pytest mypy && .venv/bin/pip install -e .   # dev only; runtime is stdlib
python scripts/gen_fixtures.py     # 184 touches, 40 accounts, 90 days, 22 opportunities (seeded)
pipeline-attribution ingest --touches fixtures/touches.csv --opportunities fixtures/opportunities.csv
pipeline-attribution report --model last-touch --output last-touch.md
pipeline-attribution report --model position-based --output report.md
pipeline-attribution trace --opp OPP-004
```

Without installing: `PYTHONPATH=src python -m pipeline_attribution <command>`. Every command takes `--db` (default `pipeline_attribution.db`). `ingest` also takes `--lookback-days`. Touches and opportunities can be ingested in separate runs.

The fixtures follow journey archetypes: outbound opens deals that paid search closes, pure search inbound, ABM warming accounts that a demo request closes, cheap referrals, outbound that books meetings directly, and 18 accounts where spend never became pipeline.

**Before (last-touch):** paid search looks like the clear winner.

| Play | Touches | Cost | Pipeline credited | Share | Cost per $1 pipeline | Verdict |
|---|---|---|---|---|---|---|
| Paid search | 28 | $11,200 | $792,000 | 62% | $0.014 | More |
| Demo request | 7 | $0 | $396,000 | 31% | $0.000 | Keep |
| Outbound sequence | 67 | $10,050 | $96,000 | 7% | $0.105 | Hold (R1) |
| Paid social / ABM | 31 | $13,950 | $0 | 0% | n/a | Hold (R1) |
| Referral | 3 | $4,500 | $0 | 0% | n/a | Hold (R1) |
| Website visit | 48 | $0 | $0 | 0% | n/a | Keep |

**After (position-based):** the same $1,284,000 of pipeline, credited across the path.

| Play | Touches | Cost | Pipeline credited | Share | Cost per $1 pipeline | Verdict |
|---|---|---|---|---|---|---|
| Paid search | 28 | $11,200 | $489,540 | 38% | $0.023 | Hold |
| Outbound sequence | 67 | $10,050 | $296,120 | 23% | $0.034 | Hold |
| Demo request | 7 | $0 | $172,800 | 13% | $0.000 | Keep |
| Website visit | 48 | $0 | $143,140 | 11% | $0.000 | Keep |
| Referral | 3 | $4,500 | $110,400 | 9% | $0.041 | Hold |
| Paid social / ABM | 31 | $13,950 | $72,000 | 6% | $0.194 | Less |

The narrative the report generates from those numbers (computed, not hardcoded):

> **Before (last-touch):** Paid search looks like the winner with $792,000, 62% of attributed pipeline. It was the last touch on 13 opportunities.
>
> **After (first-touch and position-based):** of the $792,000 last-touch hands to Paid search, Outbound sequence was the first touch on $372,000. Outbound sequence sourced 47% of it. Position-based splits those same opportunities 62% Paid search, 24% Outbound sequence.
>
> **So what:** a last-touch dashboard says move budget into Paid search. Cutting Outbound sequence on that view would cut the play that opened 47% of Paid search's pipeline.

And `trace` shows exactly where one opportunity's credit went:

```
OPP-004 · globex · $60,000 · created 2026-08-20T03:00:00+00:00

| touch_id | timestamp        | play              | cost | first-touch  | last-touch   | position-based |
| T0009    | 2026-07-30 14:06 | Outbound sequence | $150 | 100% $60,000 | -            | 40% $24,000    |
| T0010    | 2026-07-30 16:56 | Outbound sequence | $150 | -            | -            | 4% $2,400      |
| T0013    | 2026-08-01 11:41 | Outbound sequence | $150 | -            | -            | 4% $2,400      |
| T0027    | 2026-08-09 07:22 | Website visit     | $0   | -            | -            | 4% $2,400      |
| T0029    | 2026-08-09 12:53 | Paid search       | $400 | -            | -            | 4% $2,400      |
| T0031    | 2026-08-11 20:43 | Website visit     | $0   | -            | -            | 4% $2,400      |
| T0049    | 2026-08-18 13:00 | Paid search       | $400 | -            | 100% $60,000 | 40% $24,000    |
```

(Channel column trimmed here for width.)

## CSV schemas

`touches.csv`: `touch_id,account_id,timestamp,play,channel,cost`. Timestamps are ISO 8601; naive ones are read as UTC. Cost is per touch, in dollars, `>= 0`.

`opportunities.csv`: `opp_id,account_id,created_at,amount`. Amount `> 0`.

Plays in the fixtures: `outbound_sequence`, `paid_search`, `paid_social_abm`, `website_visit`, `demo_request`, `referral`. Any other play name is accepted and reported.

Re-ingesting is idempotent: touches upsert by `touch_id`, opportunities by `opp_id`, and attributions are rebuilt from scratch, so running the same ingest twice leaves the database identical. A corrected cost in a re-sent CSV updates in place.

## Checks

```bash
.venv/bin/python -m pytest              # 78 tests
.venv/bin/python -m mypy --strict src   # clean
```

Tests cover each model's math on hand-computed paths, weights summing to exactly 1 for every path length, lookback and account scoping, traceability on the full fixtures (every credit row points at an eligible touch, every opportunity is allocated exactly once per model, report totals are sums of credit rows, the ledger names every credited touch), idempotent ingest, every rule in both rule tables, the before/after narrative on a hand-computed case, and the CLI end to end.

## What v1 does NOT do

- **Fixtures are synthetic.** The 40 accounts and their journeys are generated from archetypes with a seeded RNG. The patterns are realistic, but the numbers are not anyone's real funnel.
- **No integrations.** No Salesforce, HubSpot, Google Ads, LinkedIn Ads, or web analytics connectors. CSV in, Markdown out.
- **The models are rules, not learned.** First, last and 40/20/40 are conventions. Nothing here estimates causal lift, and "sourced" means "was the first recorded touch", not "caused".
- **Cost is per touch.** Spend that never produced a recorded touch (impressions with no engagement, salaries outside a sequence) is invisible unless you put it on a touch.
- **Account level only.** No contact or buying-committee view. Multiple opportunities on one account can share the same touches inside the lookback window.
- **Thresholds are reasoned defaults.** The 0.5x / 2x / 1.5x cut-offs in the rule table are constants in `rules.py`, not tuned.
- **Single-user SQLite.** No scheduling, no history of past reports.

## v2 roadmap

- Salesforce and HubSpot touchpoint sync (campaign members, activities, opportunity contact roles) behind the existing ingest boundary. The seam exists today: `sources.py` defines a `Source` protocol, the CLI ingests through `CsvSource`, and `SalesforceSource` and `HubSpotSource` are typed stubs that raise `NotImplementedError`.
- Data-driven weights (Markov removal effect or Shapley) reported alongside the rule-based models, never replacing them, with the rule-based view as the sanity check.
- Cohort views: by opportunity creation month, segment and region, plus time-decay and W-shaped models.
- Closed-won and revenue attribution, not just pipeline created, so CAC and payback can come out of the same ledger.
- Ad-platform cost ingestion so spend is reconciled to invoices rather than estimated per touch.
