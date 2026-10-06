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
| 0:55 | Dashboard: decision signal with the surplus window shaded; the dispatch-plan issue | "Every half hour the dispatcher plans the backlog on my day-ahead prices, the way Google schedules its own data centres." |
| 1:10 | 02:00: the Flows API starts the Surge Worker; MR opens; pipeline runs | "When the wind comes, the agents work. Nobody is awake. That's the point." |
| 1:25 | MR widget: joules/request metric, carbon-blame table pointing at `app/insights.py:19`; Carbon Reviewer note | "Every merge request is measured. This line costs the most energy; the reviewer says how to fix it." |
| 1:45 | Scanners green; `cosign verify-attestation` prints the carbon receipt | "Every image carries a signed receipt. Anyone can check it." |
| 1:55 | Canary vs production joules/request; promotion | "If the new version is hungrier than the old one, it does not ship. This one is lighter." |
| 2:10 | Compliance centre: external control "Carbon budget" passing; Release Captain's "Shipped" note with ranges | "The budget is a compliance control. The issue closes with its carbon balance, including the agents' own." |
| 2:25 | Chart: run-now vs supervised vs hands-off on real GB and Spanish data | "Same work, same deadlines. Hands-off cut emissions by a quarter to a third and missed no deadline. Supervised waited for office hours and saved less. That gap is the carbon dividend of autonomy." |
| 2:45 | Region table: Finland 39 g average vs 785 g marginal | "And one more thing: averages lie. I'm clean on average, but not on the margin. Joule Thief knows the difference." |
| 2:55 | End card: repo URL, live URL | "You touched nothing. I did the timing." |

## Seeded backlog (disclosed)

To show the full loop on camera, the app contains one deliberate inefficiency, documented in
`app/insights.py` and `AGENTS.md`: `weekly_pairs` is O(n·m) where O(n+m) suffices. File the issue
"Dashboard comparison is slow" with `priority::low`; the agents find it through carbon blame and fix it
in a clean window. Real grid events (negative-price hours) are captured live during the hackathon.
