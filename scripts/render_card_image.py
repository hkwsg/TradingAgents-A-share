from __future__ import annotations

import argparse
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from PIL import Image

from render_card_html import render_html

# 固定路径优先（Windows 标准安装位置），再用 PATH 兜底（跨平台 + 非标准安装）
_CHROME_PATHS = (
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

_BROWSER_NAMES = ("chrome", "msedge", "google-chrome", "chromium")


def find_browser(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
        raise FileNotFoundError(f"Browser not found: {path}")

    # 1. 标准安装路径（Windows）
    for path in _CHROME_PATHS:
        if path.exists():
            return path

    # 2. PATH 搜索（跨平台 / 非标准安装）
    for name in _BROWSER_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)

    raise FileNotFoundError(
        "Chrome/Edge executable not found. Pass --browser <path>. "
        f"Searched names: {', '.join(_BROWSER_NAMES)}"
    )


def detect_background(image: Image.Image) -> tuple[int, int, int]:
    width, height = image.size
    sample_points = []
    for x in range(0, width, max(1, width // 40)):
        sample_points.append((x, height - 1))
        sample_points.append((x, 0))
    for y in range(0, height, max(1, height // 40)):
        sample_points.append((0, y))
        sample_points.append((width - 1, y))

    colors = [image.getpixel(point) for point in sample_points]
    return Counter(colors).most_common(1)[0][0]


def crop_background(src: Path, dst: Path, bg: tuple[int, int, int] | None = None) -> None:
    image = Image.open(src).convert("RGB")
    bg = bg or detect_background(image)
    pixels = image.load()
    width, height = image.size
    last_content_y = 0
    tolerance = 8

    for y in range(height):
        has_content = False
        for x in range(width):
            r, g, b = pixels[x, y]
            if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > tolerance:
                has_content = True
                break
        if has_content:
            last_content_y = y

    crop_bottom = min(height, last_content_y + 42) if last_content_y else height
    dst.parent.mkdir(parents=True, exist_ok=True)
    image.crop((0, 0, width, crop_bottom)).save(dst)


def screenshot(browser: Path, html_path: Path, raw_png: Path, width: int, height: int) -> None:
    url = html_path.resolve().as_uri()
    raw_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        f"--screenshot={raw_png.resolve()}",
        url,
    ]
    subprocess.run(cmd, check=True)


def default_output_path(md_path: Path) -> Path:
    stem = md_path.stem
    return md_path.with_name(f"{stem}_图像版.png")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a text investment card markdown file to PNG.")
    parser.add_argument("markdown", type=Path, help="资料卡 markdown 文件")
    parser.add_argument("--output", type=Path, help="输出 PNG 路径，默认与 markdown 同目录")
    parser.add_argument("--html-output", type=Path, help="输出 HTML 路径，默认与 PNG 同名")
    parser.add_argument("--browser", help="Chrome/Edge 可执行文件路径")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=8000)
    parser.add_argument("--keep-raw", action="store_true", help="保留未裁剪 raw PNG")
    args = parser.parse_args()

    md_path = args.markdown
    if not md_path.exists():
        raise FileNotFoundError(md_path)

    output = args.output or default_output_path(md_path)
    html_output = args.html_output or output.with_suffix(".html")
    raw_png = output.with_name(f"{output.stem}_raw.png")
    browser = find_browser(args.browser)

    render_html(md_path, html_output)
    screenshot(browser, html_output, raw_png, args.width, args.height)
    crop_background(raw_png, output)

    if not args.keep_raw:
        raw_png.unlink(missing_ok=True)

    print(f"HTML: {html_output}")
    print(f"PNG:  {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
