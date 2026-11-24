"""Render the replay to PNG frames, then to an mp4 with ffmpeg.

  uv run --with playwright==1.56.0 docs/marketing/video/render.py --out OUT_DIR [--w 1920 --h 1080] [--fps 30] [--still 20,25]
"""
import argparse, pathlib, subprocess, sys
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--w", type=int, default=1920)
ap.add_argument("--h", type=int, default=1080)
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--dur", type=float, default=35.0)
ap.add_argument("--still", default="", help="comma-separated seconds: write only these PNGs")
ap.add_argument("--name", default="thunderstruck")
ap.add_argument("--chromium", default=None, help="path to a Chromium/Chrome binary when Playwright's own build is not installed")
a = ap.parse_args()
out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
page_url = (pathlib.Path(__file__).parent / "replay.html").resolve().as_uri() + f"?w={a.w}&h={a.h}"

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=a.chromium) if a.chromium else p.chromium.launch()
    pg = b.new_page(viewport={"width": a.w, "height": a.h})
    pg.goto(page_url)
    if a.still:
        for s in a.still.split(","):
            pg.evaluate(f"render({float(s)})")
            pg.screenshot(path=str(out / f"still_{a.w}x{a.h}_{float(s):05.1f}.png"))
        b.close(); sys.exit(0)
    frames = out / f"frames_{a.w}x{a.h}"; frames.mkdir(exist_ok=True)
    n = int(a.dur * a.fps)
    for i in range(n):
        pg.evaluate(f"render({i / a.fps})")
        pg.screenshot(path=str(frames / f"{i:05d}.png"))
    b.close()
mp4 = out / f"{a.name}_{a.w}x{a.h}.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps), "-i", str(frames / "%05d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", str(mp4)], check=True)
print(mp4)
