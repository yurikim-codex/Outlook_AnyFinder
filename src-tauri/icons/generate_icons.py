"""OutLook AnyFinder 앱 아이콘 생성기 (외부 의존성 없음 — Python 표준만 사용).

모티프: Outlook 블루 배경 + 흰 봉투 + 앰버 돋보기 (메일 검색).
출력: 32x32.png, 128x128.png, 128x128@2x.png(256), icon.ico(16~256 멀티사이즈)

사용법:  python src-tauri/icons/generate_icons.py
참고: 개발 머신에서 `npx tauri icon <1024px 원본>`으로 교체 가능 —
      이 스크립트는 빌드가 막히지 않도록 하는 최소 품질 아이콘이다.
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ── 색상 ──
BG_TOP = (27, 127, 212)      # #1B7FD4
BG_BOTTOM = (11, 79, 145)     # #0B4F91
ENVELOPE = (255, 255, 255)
FLAP = (11, 79, 145)
GLASS = (255, 200, 61)        # #FFC83D
LENS_TINT = (140, 190, 240)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def smooth(d: float, half_w: float, aa: float) -> float:
    """중심선 기준 거리 d, 두께 half_w, 안티앨리어싱 폭 aa → 커버리지"""
    return clamp01((half_w + aa - d) / (2.0 * aa))


def sd_round_box(px, py, cx, cy, hx, hy, r):
    dx = abs(px - cx) - hx + r
    dy = abs(py - cy) - hy + r
    ax, ay = max(dx, 0.0), max(dy, 0.0)
    outside = math.hypot(ax, ay)
    inside = min(max(dx, dy), 0.0)
    return outside + inside - r


def sd_circle(px, py, cx, cy, r):
    return math.hypot(px - cx, py - cy) - r


def sd_segment(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    t = clamp01((wx * vx + wy * vy) / max(vx * vx + vy * vy, 1e-9))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def blend(dst, src, a):
    a = clamp01(a)
    return tuple(int(round(lerp(d, s, a))) for d, s in zip(dst, src))


def render(size: int):
    aa = 1.2 / size  # 안티앨리어싱 폭 (정규 좌표)
    pixels = bytearray()
    for row in range(size):
        for col in range(size):
            # 픽셀 중심의 정규 좌표 [0,1]
            x = (col + 0.5) / size
            y = (row + 0.5) / size

            # 1) 배경: 둥근 사각형 + 세로 그라디언트
            d_bg = sd_round_box(x, y, 0.5, 0.5, 0.5 - 0.02, 0.5 - 0.02, 0.18)
            cov_bg = smooth(d_bg, 0.0, aa)
            if cov_bg <= 0.0:
                pixels += b"\x00\x00\x00\x00"
                continue
            bg = tuple(int(round(lerp(t, b, y))) for t, b in zip(BG_TOP, BG_BOTTOM))

            color, alpha = bg, cov_bg

            # 2) 봉투 몸통
            d_env = sd_round_box(x, y, 0.42, 0.47, 0.26, 0.17, 0.03)
            cov_env = smooth(d_env, 0.0, aa)
            if cov_env > 0.0:
                color = blend(color, ENVELOPE, cov_env)
                # 3) 봉투 플랩 (V자 라인)
                d1 = sd_segment(x, y, 0.17, 0.315, 0.42, 0.50)
                d2 = sd_segment(x, y, 0.67, 0.315, 0.42, 0.50)
                cov_flap = smooth(min(d1, d2), 0.012, aa) * clamp01(-d_env / aa)
                color = blend(color, FLAP, cov_flap * 0.85)

            # 4) 돋보기 렌즈 유리 (반투명 틴트)
            gx, gy, gr = 0.665, 0.635, 0.155
            d_lens = sd_circle(x, y, gx, gy, gr)
            cov_lens = smooth(d_lens, 0.0, aa)
            if cov_lens > 0.0:
                color = blend(color, LENS_TINT, cov_lens * 0.35)

            # 5) 돋보기 링
            d_ring = abs(sd_circle(x, y, gx, gy, gr)) 
            cov_ring = smooth(d_ring, 0.028, aa)
            color = blend(color, GLASS, cov_ring)

            # 6) 돋보기 손잡이
            hx0, hy0 = gx + gr * 0.72, gy + gr * 0.72
            hx1, hy1 = gx + gr * 1.62, gy + gr * 1.62
            d_handle = sd_segment(x, y, hx0, hy0, hx1, hy1)
            cov_handle = smooth(d_handle, 0.038, aa)
            color = blend(color, GLASS, cov_handle)

            r, g, b = color
            pixels += bytes((r, g, b, int(round(alpha * 255))))
    return bytes(pixels)


# ── PNG writer ──

def write_png(path: Path, size: int, raw: bytes):
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    stride = size * 4
    scanlines = bytearray()
    for row in range(size):
        scanlines += b"\x00" + raw[row * stride : (row + 1) * stride]
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(scanlines), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


# ── ICO writer (PNG 압축 엔트리, Vista+) ──

def write_ico(path: Path, entries: list[tuple[int, bytes]]):
    count = len(entries)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    directory = bytearray()
    data = bytearray()
    for size, png in entries:
        dim = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset
        )
        data += png
        offset += len(png)
    path.write_bytes(header + bytes(directory) + bytes(data))


def main():
    plan = [
        (32, HERE / "32x32.png"),
        (128, HERE / "128x128.png"),
        (256, HERE / "128x128@2x.png"),
    ]
    rendered = {}
    for size, path in plan:
        raw = render(size)
        rendered[size] = raw
        # PNG 파일을 먼저 만들고 ICO에는 그 파일을 넣기 위해 바이트 확보
        write_png(path, size, raw)
        print(f"written {path.name} ({size}x{size})")

    # ICO용 각 사이즈 PNG 바이트 재생성
    ico_entries = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        if size in rendered:
            raw = rendered[size]
        else:
            raw = render(size)
        tmp = HERE / f"_tmp_{size}.png"
        write_png(tmp, size, raw)
        ico_entries.append((size, tmp.read_bytes()))
        tmp.unlink()
    write_ico(HERE / "icon.ico", ico_entries)
    print("written icon.ico (16,24,32,48,64,128,256)")


if __name__ == "__main__":
    main()
