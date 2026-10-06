# Demo — 3 minutes, narrated by the grid

The video is narrated in the first person by the electricity grid (text-to-speech is fine; no
third-party music or trademarks). Every number on screen comes from the ledger, the receipts or the
experiments; nothing is mocked. Replays of real grid data are labelled "replay".

| Time | Picture | Narration (the grid) |
|---|---|---|
| 0:00 | Black screen, then the Finnish price curve dipping below zero at 03:00 | "I'm the Finnish electricity grid. Last Tuesday at three in the morning I had more wind than anyone wanted. I paid people to take it." |
| 0:15 | Title: **Joule Thief** — the backlog is a battery | "Code generation is solved. Now every stage has an agent, and every agent burns energy. Joule Thief makes them work when I have energy to spare." |
| 0:25 | A developer files an issue "Upgrade dependencies"; Surge Intake labels it `priority::low`, `energy::dependency_upgrade`, `surge::queued` | "A human files work. An agent decides how urgent it really is." |
| 0:40 | @grid note on the issue (e.g. holding until 02:00, with the expected saving) | "I can't be cleaner right now. So I hold it, and I say why, with numbers. The deadline is safe." |
| 0:55 | Dashboard: press **▶ Replay the week**: the battery charges in the evening and drains into the shaded surplus hours while @grid's notes scroll by | "Every half hour, and whenever an issue changes, the dispatcher plans the backlog on my day-ahead prices, the way Google schedules its own data centres. Here is a real week of mine, replayed: the backlog charges at night and discharges into my surplus." |
| 1:10 | 02:00: the Flows API starts the Surge Worker; MR opens; pipeline runs | "When the wind comes, the agents work. Nobody is awake. That's the point." |
| 1:25 | MR widget: joules/request metric, carbon-blame table pointing at `app/insights.py:19`; Carbon Reviewer note | "Every merge request is measured. This line costs the most energy; the reviewer says how to fix it." |
| 1:45 | Scanners green; `cosign verify-attestation` prints the carbon receipt | "Every image carries a signed receipt. Anyone can check it." |
| 1:55 | Canary vs production joules/request; promotion | "If the new version is hungrier than the old one, it does not ship. This one is lighter." |
| 2:10 | Compliance centre: external control "Carbon budget" passing; Release Captain's "Shipped" note with ranges | "The budget is a compliance control. The issue closes with its carbon balance, including the agents' own." |
| 2:25 | Chart: run-now vs supervised vs hands-off on real GB and Spanish data | "Same work, same deadlines. Hands-off cut emissions by a quarter to nearly a third and missed no deadline. Supervised waited for office hours and saved less. That gap is the carbon dividend of autonomy." |
| 2:45 | Region table: Finland 39 g average vs 785 g marginal | "And one more thing: averages lie. I'm clean on average, but not on the margin. Joule Thief knows the difference." |
| 2:55 | End card: repo URL, live URL | "You touched nothing. I did the timing." |

## Rehearse offline: `joule demo`

`python -m joulethief.cli demo` runs the production dispatcher (`loop.tick`) every 30 minutes, plus a
webhook tick at each filing, against an in-memory GitLab over a real week of Spanish day-ahead prices
(5–9 May 2025). It prints every story issue's timeline: filing, @grid's hold with its numbers, the
release into surplus, the flow or pipeline start, and the "Shipped" carbon balance. No accounts, no LLM,
about a second. The transcript is committed as [`results/hands_off_replay.md`](results/hands_off_replay.md);
`--json docs/results/battery_replay.json` regenerates the dashboard's battery panel; `--grid gb` replays
NESO instead. Use it to rehearse the narration, and as the fallback shot (labelled "replay") if the live
grid is dull on recording day.

## Render the video: `scripts/video/make_video.py`

The video is generated, not edited by hand. Scenes are HTML (`scripts/video/film.html`), drawn as a
pure function of time and screenshotted frame by frame, so every run gives the same cut. The numbers
come from `docs/results` and from the CLI's own output (carbon blame, a freshly built receipt), and scene
lengths follow the narration. Captions are burned in and also written as `.srt` for YouTube.

```bash
pip install -r requirements-video.txt && playwright install chromium   # plus ffmpeg on PATH
python scripts/video/make_video.py                    # edge-tts → build/video/joule-thief.mp4 + .srt (~10 min)
python scripts/video/make_video.py --voice en-GB-SoniaNeural --rate=-5%
python scripts/video/make_video.py --tts kokoro --kokoro-dir ~/kokoro   # offline open-weights voice
python scripts/video/make_video.py --clip hold=rec/issue-10.mp4 --clip loop=rec/flow-session.mp4
python scripts/video/make_video.py --stills-only --still title@14 --still battery   # cover and README images
```

The narration lives at the top of `make_video.py` (the grid speaks in the first person, about 420 words,
just under three minutes). Once the project runs on GitLab, record the real thing (Surge Intake labelling
an issue, @grid's note, the Duo flow session, the MR widget, `cosign verify-attestation`) and pass the
recordings with `--clip scene=file`. They replace that scene's picture and keep its narration. Judges
weigh real Duo Agent Platform footage most, so swap in at least `hold` and `loop`.

## Seeded backlog (disclosed)

To show the full loop on camera, the app contains one deliberate inefficiency, documented in
`app/insights.py` and `AGENTS.md`: `weekly_pairs` is O(n·m) where O(n+m) suffices. File the issue
"Dashboard comparison is slow" with `priority::low`; the agents find it through carbon blame and fix it
in a clean window. Real grid events (negative-price hours) are captured live during the hackathon.
