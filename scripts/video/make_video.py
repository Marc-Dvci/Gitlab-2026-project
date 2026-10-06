"""Render the demo video: narration, scenes and captions, from the repository's own results.

    pip install -r requirements-video.txt && playwright install chromium
    python scripts/video/make_video.py                       # edge-tts voice → build/video/joule-thief.mp4 (+ .srt)
    python scripts/video/make_video.py --tts kokoro --kokoro-dir ~/kokoro   # offline open-weights voice
    python scripts/video/make_video.py --clip hold=rec/issue.mp4            # real GitLab footage for a scene
    python scripts/video/make_video.py --still battery --still title        # PNG stills (cover, README hero)

Scenes live in film.html and are pure functions of time: each frame is set, then screenshotted,
so the cut is identical on any machine. Scene lengths follow the narration. Every number on
screen comes from docs/results and the CLI's own output; replays are labelled as replays.
Run `joule demo --json docs/results/battery_replay.json` and the experiments first.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
RESULTS = ROOT / "docs" / "results"
MADRID = ZoneInfo("Europe/Madrid")
FPS, LEAD, TAIL = 30, 0.5, 0.9

# (scene, corner tag, narration). The grid narrates in the first person. Keep the total under ~430 words (≈3 min).
SCENES = [
    ("cold-open", "real data · OMIE",
     "I'm the Spanish electricity grid. On the fifth of May last year, from eleven in the morning until eight at "
     "night, I had more sun than anyone wanted. For most of those hours, I paid people to take it."),
    ("title", "",
     "Code generation is solved. Now every stage of delivery has an agent, and every agent burns energy. "
     "Joule Thief makes them work when I have energy to spare. The backlog is a battery."),
    ("loop", "GitLab Duo Agent Platform",
     "A human files an issue. A GitLab Duo flow triages it: how urgent, what kind of work, whether it can wait. "
     "Every half hour, and the moment an issue changes, a dispatcher plans the backlog on my day-ahead prices, "
     "under every deadline. When my window opens, it starts a Duo flow through the API. Nobody presses a button."),
    ("hold", "replay · in-memory GitLab",
     "Ten past nine on a Monday evening, someone files: dashboard comparison is slow. I can't be clean right now, "
     "so I hold it, and I say why, with numbers. At ten the next morning the sun is up and my price is below zero. "
     "The agent works, and the issue closes with its carbon balance: ninety-seven percent less."),
    ("urgent", "replay · in-memory GitLab",
     "Critical work never waits for me. A production error at twenty past eight at night runs at once, and I log "
     "what waiting would have cost: the honest price of urgency."),
    ("battery", "replay · real prices",
     "Here is that whole week, replayed on my real prices. The backlog charges in the evening and discharges into "
     "my surplus. Thirty issues, thirty shipped, not one deadline missed. Sixty percent less carbon than running "
     "each task when it was filed, and ninety-one percent of the energy came from power I would otherwise have "
     "thrown away."),
    ("verify", "CI/CD · nine stages",
     "Every merge request is measured: joules per request, down to the line of code that spends them. Every image "
     "carries a signed carbon receipt, and without a valid receipt inside the budget, nothing deploys. An energy "
     "regression is a bug: a hungrier canary does not ship."),
    ("dividend", "real data · 3 grids",
     "Now a whole season, three grids, the same work and the same deadlines. Hands-off autonomy cut emissions by a "
     "quarter to nearly a third, and missed nothing. Supervised autonomy waited for office hours, saved less, and "
     "missed up to twenty-four deadlines. That gap is the carbon dividend of autonomy, and it stayed positive in "
     "every backlog we tried."),
    ("margin", "real data · GSF, Google",
     "And averages lie. Finland is one of the cleanest grids on average, but one more kilowatt-hour there is "
     "answered by something twenty times dirtier. Joule Thief decides on the margin, and reports both."),
    ("end", "",
     "You touched nothing. I did the timing."),
]


# ── narration ────────────────────────────────────────────────────────────────────────────────────
def duration_s(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def synthesize(text: str, out_dir: Path, args) -> tuple[Path | None, float]:
    """Audio file for one scene (cached by engine, voice and text) and its length in seconds."""
    if args.tts == "none":
        return None, max(2.0, len(text.split()) / 2.6)
    key = hashlib.sha256(f"{args.tts}|{args.voice}|{args.rate}|{text}".encode()).hexdigest()[:16]
    path = out_dir / f"{key}.{'mp3' if args.tts == 'edge' else 'wav'}"
    if not path.exists():
        if args.tts == "edge":
            import edge_tts

            asyncio.run(edge_tts.Communicate(text, args.voice, rate=args.rate).save(str(path)))
        else:
            import soundfile
            from kokoro_onnx import Kokoro

            kdir = Path(args.kokoro_dir).expanduser()
            k = Kokoro(str(next(kdir.glob("kokoro-v1.0*.onnx"))), str(kdir / "voices-v1.0.bin"))
            speed = 1.0 + int(args.rate.rstrip("%")) / 100 if args.rate.rstrip("%").lstrip("+-").isdigit() else 1.0
            samples, rate = k.create(text, voice=args.voice, speed=speed, lang="en-gb" if args.voice[0] == "b" else "en-us")
            soundfile.write(str(path), samples, rate)
    return path, duration_s(path)


def _cues(sentence: str, limit: int = 96) -> list[str]:
    """Split a long sentence at the comma or colon nearest its middle, so no caption runs past two lines."""
    if len(sentence) <= limit:
        return [sentence]
    cuts = [m.end() for m in re.finditer(r"[,:;] ", sentence)]
    if not cuts:
        return [sentence]
    cut = min(cuts, key=lambda c: abs(c - len(sentence) / 2))
    return _cues(sentence[:cut].strip(), limit) + _cues(sentence[cut:].strip(), limit)


def captions(text: str, start: float, length: float) -> list[dict]:
    """Captions of at most two lines, timed in proportion to their length across the spoken span."""
    sentences = [c for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s for c in _cues(s)]
    total, t, out = sum(len(s) for s in sentences), start, []
    for s in sentences:
        d = length * len(s) / total
        out.append({"start": round(t, 3), "end": round(t + d, 3), "text": s})
        t += d
    out[-1]["end"] = round(start + length + TAIL * .8, 3)
    return out


# ── scene data, all from the repository ──────────────────────────────────────────────────────────
def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(MADRID).strftime("%a %H:%M")


def _cue_time(cues: list[dict], cue: float) -> float:
    """``2.5`` = halfway through the third narration sentence."""
    c = cues[min(int(cue), len(cues) - 1)]
    return c["start"] + (cue - int(cue)) * (c["end"] - c["start"])


def _story(replay: dict, title: str, cue_at: list[float], cues: list[dict], duration: float) -> dict:
    """One issue's real timeline from the replay, each entry timed to the narration sentence that tells it."""
    issue = next(i for i in replay["issues"] if i["title"] == title)
    events = [e for e in replay["events"] if e["iid"] == issue["iid"]]
    out = []
    for e, cue in zip(events, cue_at):
        text, state = e["text"], {"filed": "surge::queued", "note": "surge::scheduled", "shipped": "closed"}.get(e["kind"], "surge::running")
        if e["kind"] == "note":
            text = text.split(" — ", 1)[1]
            if "releasing" in text or "critical work never waits" in text:
                state = "surge::running"
        elif e["kind"] == "shipped":
            text = text.removeprefix("**Shipped** · ")
        elif e["kind"] == "filed":
            labels = [x for x in issue["labels"] if x.split("::")[0] in ("priority", "energy")]
            text = "filed. The Surge Intake flow labels it " + ", ".join(f"`{x}`" for x in labels) + "."
        out.append({"kind": e["kind"], "local": _local(e["t"]), "text": text, "state": state,
                    "at": round(_cue_time(cues, cue) / duration, 4)})
    t0 = datetime.fromisoformat(events[0]["t"]) - timedelta(hours=2)
    t1 = datetime.fromisoformat(events[-1]["t"]) + timedelta(hours=2)
    window = [p for p in replay["timeline"] if t0 <= datetime.fromisoformat(p["t"]) <= t1]

    def nearest(t: datetime) -> int:
        return min(range(len(window)), key=lambda i: abs(datetime.fromisoformat(window[i]["t"]) - t))

    filed = datetime.fromisoformat(events[0]["t"])
    marks = [{"i": nearest(filed), "label": f"filed {_local(events[0]['t'])[4:]}", "color": "ink", "at": out[0]["at"]}]
    start = next(e for e in events if e["kind"] in ("flow", "pipeline"))
    if start["t"] != events[0]["t"]:
        marks.append({"i": nearest(datetime.fromisoformat(start["t"])), "label": f"runs {_local(start['t'])[4:]}",
                      "color": "warm", "at": out[events.index(start)]["at"]})
    cleanest = re.search(r"waiting until (\w{3}) (\d\d):(\d\d) UTC", " ".join(e["text"] for e in events))
    if cleanest:  # the cleanest start @grid named, on the first matching day after filing
        day, hh, mm = cleanest.group(1), int(cleanest.group(2)), int(cleanest.group(3))
        when = next(filed.replace(hour=hh, minute=mm) + timedelta(days=k) for k in range(7)
                    if (filed + timedelta(days=k)).strftime("%a") == day)
        marks.append({"i": nearest(when), "label": f"cleanest {when.astimezone(MADRID):%H:%M}", "color": "warm",
                      "at": out[1]["at"] + .04})
    return {"iid": issue["iid"], "title": issue["title"], "where": "Madrid · europe-southwest1 · replay of 5–9 May 2025",
            "labels": [x for x in issue["labels"] if x.split("::")[0] in ("priority", "energy")],
            "events": out, "signal": [{"v": p["signal"] or 0, "surplus": bool(p["surplus"])} for p in window],
            "marks": marks, "signal_label": "Decision signal, gCO₂/kWh · green: price ≤ 0 · Madrid time"}


def _prices() -> dict:
    from joulethief.signals.snapshots import es_prices

    p, day = es_prices(), datetime(2025, 5, 5, tzinfo=MADRID)
    values = [{"h": h, "v": p.value_at((day + timedelta(hours=h)).astimezone(timezone.utc))} for h in range(24)]
    surplus = [v["h"] for v in values if v["v"] <= 0]
    return {"day": "Monday 5 May 2025", "values": values, "first_surplus": surplus[0], "last_surplus": surplus[-1]}


def _verify(tmp: Path) -> dict:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    subprocess.run([sys.executable, str(ROOT / "scripts" / "energy_benchmark.py")], cwd=tmp, env=env, check=True,
                   capture_output=True)
    bench = json.loads((tmp / "benchmark.json").read_text())
    blame = [{"g": f"{line['g_per_day']:.3f}", "where": f"{line['file']}:{line['line']}"} for line in bench["lines"][:6]]
    for cmd in (["ci-energy", "--minutes", "12", "--ledger", "ledger.jsonl"],
                ["receipt", "build", "--digest", "sha256:" + "0" * 64, "--subject", "registry.gitlab.com/…/app"]):
        subprocess.run([sys.executable, "-m", "joulethief.cli", *cmd], cwd=tmp, env=env, check=True, capture_output=True)
    pred = json.loads((tmp / "receipt.predicate.json").read_text())
    build, budget = pred.get("build", {}), pred.get("budget", {})

    def rng(r: dict, unit: str, digits: int) -> str:
        return f"{r['low']:.{digits}f} – {r['high']:.{digits}f} {unit} (likely {r['likely']:.{digits}f})"

    receipt = "\n".join([
        "predicateType: urn:joulethief:carbon-receipt:v1",
        f"build.energy:  {rng(build['energy_kwh'], 'kWh', 3)}",
        f"build.CO₂e (consequential):\n  {rng(build['consequential_g'], 'g', 1)}",
        f"budget: {budget['spentG']:.1f} / {budget['capG']:.0f} g ({budget['period']})",
        f"verdict: {pred.get('verdict')}",
    ])
    return {"blame": blame, "blame_caption": "projected gCO₂e/day per source line (this service)", "receipt": receipt,
            "gates": ["`release:verify-receipt` · no valid receipt inside the monthly budget → **no deploy**",
                      "`monitor:canary-energy` · canary more than **15 %** hungrier per request → **no promotion**",
                      "`verify:energy` · joules per request as a **metrics report** on every MR",
                      "`govern:footprint` · carbon budget as a compliance **external control**"]}


def _dividend() -> dict:
    main = json.loads((RESULTS / "autonomy_dividend.json").read_text())
    robust = json.loads((RESULTS / "robustness.json").read_text())
    names = [("Great Britain", "NESO, Sep–Oct 2026"), ("Spain, spring", "OMIE, Mar–May 2025"), ("Spain, summer", "OMIE, Jul–Sep 2025")]
    seeds = list(robust["by_seed"].values())
    rows = []
    for (grid, signal), case, key in zip(names, main["cases"], seeds[0]):
        r = case["results"]
        divs = [s[key]["dividend"] for s in seeds]
        rows.append({"grid": grid, "signal": signal, "supervised": 1 - r["supervised"]["reduction_vs_run_now"],
                     "hands_off": 1 - r["hands_off"]["reduction_vs_run_now"], "dividend": r["carbon_dividend_of_autonomy"],
                     "late_supervised": r["supervised"]["late_jobs"], "late_hands_off": r["hands_off"]["late_jobs"],
                     "range": f"{min(divs):.1%}–{max(divs):.1%}"})
    return {"rows": rows}


def _regions() -> list[dict]:
    keep = ["europe-north1", "northamerica-northeast1", "us-west1", "europe-west2", "europe-southwest1", "us-east1"]
    rows = {}
    for line in (RESULTS / "region_ledgers.md").read_text().splitlines():
        cells = [c.strip(" `") for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0] in keep and cells[4] not in ("—", ""):
            rows[cells[0]] = {"region": cells[0], "city": "Finland (Hamina)" if cells[0] == "europe-north1" else cells[1],
                              "average": float(cells[3]), "marginal": float(cells[4]),
                              "ratio": float(cells[5].rstrip("×")), "highlight": cells[0] == "europe-north1"}
    return [rows[r] for r in keep if r in rows]


def film_data(args, tmp: Path, timing: dict) -> dict:
    def cues(scene: str) -> tuple[list[dict], float]:  # scenes not being rendered still need plausible timing
        if scene in timing:
            return timing[scene]["captions"], timing[scene]["duration"]
        text = next(t for n, _, t in SCENES if n == scene)
        spoken = len(text.split()) / 2.6
        return captions(text, LEAD, spoken), LEAD + spoken + TAIL

    replay = json.loads((RESULTS / "battery_replay.json").read_text())
    s = replay["summary"]
    days = {p["t"]: datetime.fromisoformat(p["t"]).astimezone(MADRID).strftime("%a") for p in replay["timeline"]}
    timeline = [{**p, "day": days[p["t"]]} for p in replay["timeline"]]
    remote = args.repo_url or subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True,
                                             text=True).stdout.strip()
    return {
        "prices": _prices(),
        "loop": [
            {"who": "human", "title": "Issue filed", "detail": "Anyone files work: a fix, an upgrade, a scan."},
            {"who": "Duo flow · trigger", "title": "Surge Intake", "detail": "Triages: priority, kind of work, can it wait. Labels it a Surge Request."},
            {"who": "every 30 min + webhook", "title": "Dispatcher", "detail": "CP-SAT plan on day-ahead prices and marginal signals, under every deadline."},
            {"who": "deterministic, no LLM", "title": "@grid", "detail": "Holds or releases each Surge Request, on the issue, with numbers."},
            {"who": "Flows API", "title": "Surge Worker", "detail": "Duo flow started hands-off: small model explores, large implements."},
            {"who": "9 CI stages", "title": "Merge request → CI", "detail": "Tests, joules/request, scanners, signed carbon receipt, energy canary."},
            {"who": "Duo flow · trigger", "title": "Release Captain", "detail": "Closes the issue with its carbon balance."},
        ],
        "story": {
            "hold": _story(replay, "Dashboard comparison is slow", [0.05, 1.0, 2.0, 3.0, 3.45], *cues("hold")),
            "urgent": _story(replay, "Production returns 500 on /api/grid", [0.6, 1.3, 1.45, 1.75], *cues("urgent")),
        },
        "battery": {
            "subtitle": "Replay of real OMIE day-ahead prices, Madrid, 5–9 May 2025 · production dispatcher · in-memory GitLab",
            "timeline": timeline,
            "kpis": [{"value": f"−{s['reduction']:.0%}", "label": "CO₂ vs running each task when filed"},
                     {"value": f"{s['surplus_share']:.0%}", "label": "of the energy used in surplus hours"},
                     {"value": f"{s['late']} of {s['issues']}", "label": "deadlines missed"},
                     {"value": f"{s['flows_started'] + s['pipelines_started']} / 0", "label": "flows & pipelines started by the loop / by humans"}],
        },
        "verify": _verify(tmp),
        "dividend": _dividend(),
        "regions": _regions(),
        "end": {"command": "pip install -r requirements-dev.txt\npython -m joulethief.cli demo",
                "url": remote.removesuffix(".git"), "footer": "GitLab Transcend Hackathon · Life After Code · MIT licence"},
    }


# ── rendering ────────────────────────────────────────────────────────────────────────────────────
def _ffmpeg(*args: str, stdin=None) -> subprocess.Popen:
    return subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], stdin=stdin)


def render_scene(job: dict) -> str:
    """Render one scene to an H.264 segment (or conform a user clip to it). Runs in a worker process."""
    out = Path(job["out"])
    if job.get("clip"):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-stream_loop", "-1", "-i", job["clip"],
                        "-t", f"{job['duration']:.3f}", "-an", "-vf",
                        "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0d1210,fps=30",
                        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)
        return str(out)
    from playwright.sync_api import sync_playwright

    frames = max(1, round(job["duration"] * FPS))
    ff = _ffmpeg("-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-", "-c:v", "libx264", "-preset",
                 "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out), stdin=subprocess.PIPE)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto((HERE / "film.html").as_uri())
        page.evaluate("([n, m, d]) => enter(n, m, d)", [job["scene"], job["meta"], job["data"]])
        for k in range(frames):
            page.evaluate(f"frame({k / FPS})")
            ff.stdin.write(page.screenshot(type="jpeg", quality=94))
        browser.close()
    ff.stdin.close()
    if ff.wait():
        raise RuntimeError(f"ffmpeg failed on scene {job['scene']}")
    return str(out)


def still(job: dict, t: float, out: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto((HERE / "film.html").as_uri())
        page.evaluate("([n, m, d]) => enter(n, m, d)", [job["scene"], {**job["meta"], "captions": []}, job["data"]])
        page.evaluate(f"frame({t})")
        page.screenshot(path=str(out))
        browser.close()


def scene_audio(audio: Path | None, duration: float, out: Path) -> None:
    src = ["-i", str(audio)] if audio else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *src, "-af",
                    f"adelay={int(LEAD * 1000)}:all=1,apad", "-t", f"{duration:.3f}", "-ar", "48000", "-ac", "2", str(out)],
                   check=True)


def srt(entries: list[dict]) -> str:
    def ts(s: float) -> str:
        ms = round(s * 1000)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{i}\n{ts(e['start'])} --> {ts(e['end'])}\n{e['text']}\n" for i, e in enumerate(entries, 1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tts", choices=["edge", "kokoro", "none"], default="edge")
    ap.add_argument("--voice", default="", help="edge: en-US-AndrewMultilingualNeural (default), en-GB-SoniaNeural, "
                                                 "en-US-AvaMultilingualNeural …; kokoro: af_heart (default), bf_emma, bm_george")
    ap.add_argument("--rate", default="+0%", help="speaking rate, e.g. --rate=-5%%")
    ap.add_argument("--kokoro-dir", default="~/kokoro", help="folder with kokoro-v1.0*.onnx and voices-v1.0.bin")
    ap.add_argument("--clip", action="append", default=[], help="scene=video.mp4: real footage instead of the rendered scene")
    ap.add_argument("--scenes", default="", help="comma-separated subset, for quick iterations")
    ap.add_argument("--still", action="append", default=[], help="scene[@seconds]: also write a 1920×1080 PNG")
    ap.add_argument("--stills-only", action="store_true", help="write the --still PNGs and stop (layout checks)")
    ap.add_argument("--repo-url", default="", help="shown on the end card (default: git remote origin)")
    ap.add_argument("--jobs", type=int, default=max(1, min(4, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--out", default=str(ROOT / "build" / "video"))
    args = ap.parse_args()
    args.voice = args.voice or {"edge": "en-US-AndrewMultilingualNeural", "kokoro": "af_heart", "none": ""}[args.tts]
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            print(f"{tool} not found: install ffmpeg first", file=sys.stderr)
            return 2

    out = Path(args.out)
    (out / "audio").mkdir(parents=True, exist_ok=True)
    clips = dict(c.split("=", 1) for c in args.clip)
    chosen = [s for s in SCENES if not args.scenes or s[0] in args.scenes.split(",")]

    timing, entries, clock = {}, [], 0.0
    for name, tag, text in chosen:
        audio, spoken = synthesize(text, out / "audio", args)
        duration = max(4.0, LEAD + spoken + TAIL)
        caps = captions(text, LEAD, spoken)
        timing[name] = {"audio": audio, "duration": duration, "captions": caps, "tag": tag}
        entries += [{**c, "start": c["start"] + clock, "end": c["end"] + clock} for c in caps]
        clock += duration
        print(f"{name:10s} {duration:5.1f} s  ({args.tts})", flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        data = film_data(args, Path(tmp), timing)
    jobs = [{"scene": name, "out": str(out / f"{i:02d}-{name}.mp4"), "duration": timing[name]["duration"],
             "clip": clips.get(name), "data": data,
             "meta": {"duration": timing[name]["duration"], "captions": timing[name]["captions"], "tag": timing[name]["tag"]}}
            for i, (name, _, _) in enumerate(chosen)]

    for spec in args.still:
        name, _, at = spec.partition("@")
        job = next(j for j in jobs if j["scene"] == name)
        png = out / f"still-{name}{'@' + at if at else ''}.png"
        still(job, float(at) if at else job["duration"] - .05, png)
        print(f"still → {png}")
    if args.stills_only:
        return 0

    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        segments = list(pool.map(render_scene, jobs))
    for job in jobs:
        scene_audio(timing[job["scene"]]["audio"], job["duration"], Path(job["out"]).with_suffix(".wav"))
    (out / "video.txt").write_text("".join(f"file '{Path(s).name}'\n" for s in segments))
    (out / "audio.txt").write_text("".join(f"file '{Path(s).with_suffix('.wav').name}'\n" for s in segments))
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "video.txt",
                    "-f", "concat", "-safe", "0", "-i", "audio.txt", "-c:v", "copy",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", "joule-thief.mp4"], cwd=out, check=True)
    (out / "joule-thief.srt").write_text(srt(entries))
    print(f"\n{out / 'joule-thief.mp4'}  {clock:.1f} s · captions: {out / 'joule-thief.srt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
