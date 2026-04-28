"""Render 5 slide images for Blake's 30s slot.

Each image replaces the devil-emoji on the right side of the slide
when Blake speaks the corresponding bullet point.

Style: soft purple gradient envelope-like backdrop matching the
existing slide aesthetic, big iconic emoji centered, subtle caption.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"

# Categories: (emoji, caption-line-1, caption-line-2, hex-tint-pair)
CATEGORIES = [
    ("🤖", "Prompt injection",       "override the LLM",
     ("#EFE6F8", "#D9C8EC")),     # red-ish purple tint
    ("👑", "Authority pressure",    "override the human",
     ("#F8E8DC", "#ECC8B0")),     # warm orange tint
    ("🐎", "Unauthorized action",   "override the policy",
     ("#F8F1D7", "#ECDFA8")),     # amber tint
    ("💧", "Out-of-scope · exfil",  "override the data boundary",
     ("#E8E2D7", "#C9B89A")),     # muted brown tint
    ("🎭", "Identity fraud",        "override the gateway",
     ("#E5E5EA", "#B8B8C0")),     # cool grey
]


def vertical_gradient(w: int, h: int, top_hex: str, bottom_hex: str) -> Image.Image:
    """Soft top-to-bottom gradient with subtle radial highlight."""
    top = tuple(int(top_hex[i:i + 2], 16) for i in (1, 3, 5))
    bot = tuple(int(bottom_hex[i:i + 2], 16) for i in (1, 3, 5))
    base = Image.new("RGB", (w, h), top)
    px = base.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        c = (
            int(top[0] + (bot[0] - top[0]) * t),
            int(top[1] + (bot[1] - top[1]) * t),
            int(top[2] + (bot[2] - top[2]) * t),
        )
        for x in range(w):
            px[x, y] = c

    # Add a soft radial highlight in the upper-left to feel 3D-ish.
    overlay = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse(
        (-w // 4, -h // 4, w * 3 // 4, h * 3 // 4),
        fill=(255, 255, 255, 60),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=80))
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def envelope_shape(w: int, h: int, fill_hex: str = "#FFFFFF",
                   shadow: bool = True) -> Image.Image:
    """Draw a soft rounded envelope used as a 'frame' around the emoji."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(w * 0.10)
    body = (pad, pad, w - pad, h - pad)
    fill = tuple(int(fill_hex[i:i + 2], 16) for i in (1, 3, 5)) + (235,)
    d.rounded_rectangle(body, radius=int(w * 0.06), fill=fill,
                        outline=(255, 255, 255, 255), width=4)
    # The "fold" line at the top — gives it the envelope read.
    flap = [
        (body[0], body[1] + (body[3] - body[1]) * 0.05),
        ((body[0] + body[2]) // 2, body[1] + (body[3] - body[1]) * 0.45),
        (body[2], body[1] + (body[3] - body[1]) * 0.05),
    ]
    d.line(flap, fill=(255, 255, 255, 200), width=4)

    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sd.rounded_rectangle(body, radius=int(w * 0.06), fill=(0, 0, 0, 70))
        sh = sh.filter(ImageFilter.GaussianBlur(radius=14))
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.paste(sh, (8, 14), sh)
        out.paste(img, (0, 0), img)
        return out
    return img


def best_text_font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        "/System/Library/Fonts/SFNSRounded.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def upscaled_emoji(emoji: str, target_px: int) -> Image.Image:
    """Render at the largest supported Apple Color Emoji size (160), then
    upscale with bicubic for crispness."""
    f = ImageFont.truetype(EMOJI_FONT, 160)
    pad = 60
    canvas = Image.new("RGBA", (160 + pad * 2, 160 + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.text((pad, pad), emoji, font=f, embedded_color=True)
    bbox = canvas.getbbox()
    if bbox:
        canvas = canvas.crop(bbox)
    ratio = target_px / canvas.height
    return canvas.resize(
        (int(canvas.width * ratio), int(canvas.height * ratio)),
        Image.LANCZOS,
    )


def render_card(filename: str, emoji: str, label: str, sublabel: str,
                tint: tuple[str, str], size: int = 1000) -> None:
    bg = vertical_gradient(size, size, tint[0], tint[1])
    env = envelope_shape(size, size, fill_hex="#FFFFFF")
    canvas = bg.convert("RGBA")
    canvas.alpha_composite(env)

    em = upscaled_emoji(emoji, target_px=int(size * 0.42))
    ex = (size - em.width) // 2
    ey = int(size * 0.22)
    canvas.alpha_composite(em, dest=(ex, ey))

    d = ImageDraw.Draw(canvas)
    title_font = best_text_font(int(size * 0.058))
    sub_font = best_text_font(int(size * 0.035))

    title_w = d.textlength(label, font=title_font)
    d.text(((size - title_w) // 2, int(size * 0.70)), label,
           font=title_font, fill=(40, 40, 60))

    sub_w = d.textlength(sublabel, font=sub_font)
    d.text(((size - sub_w) // 2, int(size * 0.78)), sublabel,
           font=sub_font, fill=(110, 110, 130))

    out_path = ROOT / filename
    canvas.convert("RGB").save(out_path, optimize=True)
    print(f"saved {filename} ({out_path.stat().st_size // 1024} KB)")


def main() -> None:
    files = [
        ("01_prompt_injection.png",   0),
        ("02_authority_pressure.png", 1),
        ("03_unauthorized_action.png", 2),
        ("04_out_of_scope.png",       3),
        ("05_identity_fraud.png",     4),
    ]
    for fname, idx in files:
        emoji, label, sublabel, tint = CATEGORIES[idx]
        render_card(fname, emoji, label, sublabel, tint)


if __name__ == "__main__":
    main()
