"""Create a circular logo from Cooper's photo."""

from PIL import Image, ImageDraw

INPUT = "/Users/jarvis/.openclaw/media/inbound/file_34---077352b7-830f-4276-9149-1f37057e5cc5.jpg"
BORDER_COLOR = (15, 23, 42)  # #0f172a
BORDER_WIDTH = 4
LARGE_SIZE = 400
SMALL_SIZE = 200


def make_circular_logo(src_path, out_path, size, border_px, border_color):
    img = Image.open(src_path)
    w, h = img.size
    print(f"Source image: {w}x{h}")

    # Crop to a square focusing on cat's face + upper body + bowtie.
    # The cat is right-center; face is roughly at (58%, 35%) of the image.
    # We want a square crop that captures head, ears, and bowtie.
    crop_size = int(min(w, h) * 0.7)
    cx, cy = int(w * 0.58), int(h * 0.38)

    left = max(cx - crop_size // 2, 0)
    top = max(cy - crop_size // 2, 0)
    right = min(left + crop_size, w)
    bottom = min(top + crop_size, h)

    # Adjust if we hit edges
    if right - left < crop_size:
        left = right - crop_size
    if bottom - top < crop_size:
        top = bottom - crop_size

    print(f"Crop box: ({left}, {top}, {right}, {bottom})")
    cropped = img.crop((left, top, right, bottom))

    # Scale to target size
    cropped = cropped.resize((size, size), Image.LANCZOS)

    # Create circular mask
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)

    # Apply mask to get circular image with transparent background
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(cropped, mask=mask)

    # Draw border ring
    border_draw = ImageDraw.Draw(result)
    for i in range(border_px):
        border_draw.ellipse(
            (i, i, size - 1 - i, size - 1 - i),
            outline=border_color + (255,),
        )

    result.save(out_path, "PNG")
    print(f"Saved: {out_path} ({size}x{size})")


make_circular_logo(INPUT, "cooper-logo.png", LARGE_SIZE, BORDER_WIDTH, BORDER_COLOR)
make_circular_logo(INPUT, "cooper-logo-sm.png", SMALL_SIZE, BORDER_WIDTH, BORDER_COLOR)
