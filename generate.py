import asyncio
import base64
import os
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Template
from playwright.async_api import async_playwright

SIZES = [
    ("social_400x400",    400,  400),
    ("zoom_600x400",      600,  400),
    ("email_1000x500",   1000,  500),
    ("youtube_1920x1080", 1920, 1080),
]


def get_event_data():
    return {
        "title":        os.environ.get("EVENT_TITLE", ""),
        "raw_date":     os.environ.get("EVENT_DATE", ""),   # YYYY-MM-DD
        "speaker_name": os.environ.get("SPEAKER_NAME", ""),
        "speaker_title":os.environ.get("SPEAKER_TITLE", ""),
        "event_type":   os.environ.get("EVENT_TYPE", "Online Webinar"),
        "time":         os.environ.get("EVENT_TIME", "7:30 PM - 8:45 PM (GMT +4)"),
        "pdus":         os.environ.get("EVENT_PDUS", "Earn 2 PDUs"),
    }


def parse_date(raw_date):
    dt = datetime.strptime(raw_date, "%Y-%m-%d")
    return {
        "day_of_week": dt.strftime("%A").upper(),
        "day":         str(dt.day),
        "month":       dt.strftime("%B").upper(),
        "year":        str(dt.year),
    }


def load_svg(path):
    return Path(path).read_text(encoding="utf-8")


def encode_image(path):
    path = Path(path)
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode()
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{b64}"


def find_speaker_photo():
    for ext in ("jpg", "jpeg", "png"):
        p = Path("inputs") / f"speaker_photo.{ext}"
        if p.exists():
            return p
    return None


async def render_template(browser, html, width, height, out_path):
    page = await browser.new_page()
    await page.set_viewport_size({"width": width, "height": height})
    await page.set_content(html, wait_until="networkidle")
    await page.evaluate("document.fonts.ready")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(
        path=str(out_path),
        clip={"x": 0, "y": 0, "width": width, "height": height},
    )
    await page.close()


async def generate_all(event_data, speaker_photo_path, output_dir="output"):
    if not event_data["raw_date"]:
        print("Error: EVENT_DATE is required (format: YYYY-MM-DD)")
        sys.exit(1)

    date_parts  = parse_date(event_data["raw_date"])
    logo_h      = load_svg("assets/logo-horizontal-white.svg")
    logo_mark   = load_svg("assets/logo-mark-white.svg")
    speaker_img = encode_image(speaker_photo_path)

    data = {
        **event_data,
        **date_parts,
        "logo_horizontal": logo_h,
        "logo_mark":       logo_mark,
        "speaker_photo":   speaker_img,
    }

    template_dirs = sorted(p for p in Path("templates").iterdir() if p.is_dir())

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()

        for tdir in template_dirs:
            tfile = tdir / "template.html"
            if not tfile.exists():
                continue

            tmpl = Template(tfile.read_text(encoding="utf-8"))

            for size_name, w, h in SIZES:
                html     = tmpl.render(**data, canvas_width=w, canvas_height=h)
                out_path = Path(output_dir) / tdir.name / f"{size_name}.png"
                await render_template(browser, html, w, h, out_path)
                print(f"  ✓  {tdir.name}/{size_name}.png")

        await browser.close()

    print(f"\nDone — {len(template_dirs) * len(SIZES)} files in '{output_dir}/'")


if __name__ == "__main__":
    data  = get_event_data()
    photo = find_speaker_photo()

    if not photo:
        print("Error: place speaker_photo.jpg (or .png) in the inputs/ folder")
        sys.exit(1)

    asyncio.run(generate_all(data, photo))
