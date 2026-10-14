"""Generate icon.png (512 px) and icon.ico (multi-res) in the app folder."""
import os

_HERE    = os.path.dirname(os.path.abspath(__file__))
PNG_PATH = os.path.join(_HERE, "icon.png")
ICO_PATH = os.path.join(_HERE, "icon.ico")


def _draw(size: int):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    cx = cy = size / 2
    R  = size / 2 - size / 32

    # radial navy-to-blue background
    for i in range(int(R), 0, -1):
        t = i / R
        d.ellipse([cx-i, cy-i, cx+i, cy+i],
                  fill=(int(8+40*t), int(20+80*t), int(55+120*t), 255))

    lw = max(2, round(size / 58))
    gc = (210, 235, 255, 200)

    # outer circle
    d.ellipse([cx-R, cy-R, cx+R, cy+R], outline=gc, width=lw)
    # equator
    d.line([cx-R, cy, cx+R, cy], fill=gc, width=lw)
    # central meridian ellipse
    mw = R * 0.35
    d.ellipse([cx-mw, cy-R, cx+mw, cy+R], outline=gc, width=lw)
    # upper latitude arc (top half of a flat ellipse → bows upward)
    lrx, lry = R * 0.88, R * 0.17
    ly1 = cy - R * 0.48
    d.arc([cx-lrx, ly1-lry, cx+lrx, ly1+lry], 180, 360, fill=gc, width=lw)
    # lower latitude arc (bottom half → bows downward)
    ly2 = cy + R * 0.48
    d.arc([cx-lrx, ly2-lry, cx+lrx, ly2+lry], 0, 180, fill=gc, width=lw)

    # orange download-arrow badge (bottom-right)
    br = R * 0.37
    bx, by = cx + R * 0.50, cy + R * 0.50
    sd = size / 80
    d.ellipse([bx-br+sd, by-br+sd, bx+br+sd, by+br+sd], fill=(0, 0, 0, 70))
    d.ellipse([bx-br, by-br, bx+br, by+br], fill=(225, 95, 15, 255))
    aw, ah, sw = br*0.50, br*0.65, br*0.22
    top, mid = by - ah*0.45, by + ah*0.08
    d.rectangle([bx-sw, top, bx+sw, mid], fill=(255, 255, 255, 255))
    d.polygon([(bx-aw, mid), (bx+aw, mid), (bx, by+ah*0.50)],
              fill=(255, 255, 255, 255))
    return img


def make() -> str | None:
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not available — skipping icon generation.")
        return None

    _draw(512).save(PNG_PATH)
    _draw(256).save(ICO_PATH, format="ICO",
                    sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)])
    print(f"[icon] {PNG_PATH}")
    print(f"[icon] {ICO_PATH}")
    return ICO_PATH


if __name__ == "__main__":
    make()
