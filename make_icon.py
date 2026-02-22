#!/usr/bin/env python3
"""Quick icon generator - creates small PNGs and converts to .icns"""
import subprocess, os, struct, zlib, tempfile, shutil

def make_png(size, path):
    """Create a minimal dark icon with a red accent and silver T."""
    rows = []
    for y in range(size):
        row = b'\x00'  # filter
        for x in range(size):
            nx, ny = x/size, y/size
            r, g, b = 25, 25, 25  # dark bg

            # Red bar at bottom
            if 0.82 < ny < 0.88 and 0.15 < nx < 0.85:
                r, g, b = 204, 51, 51
            # Silver T - vertical
            elif 0.25 < ny < 0.72 and 0.43 < nx < 0.57:
                r, g, b = 192, 192, 198
            # Silver T - horizontal
            elif 0.2 < ny < 0.32 and 0.2 < nx < 0.8:
                r, g, b = 192, 192, 198

            row += struct.pack('BBBB', r, g, b, 255)
        rows.append(row)

    raw = b''.join(rows)
    compressed = zlib.compress(raw, 9)

    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)))
        f.write(chunk(b'IDAT', compressed))
        f.write(chunk(b'IEND', b''))

d = tempfile.mkdtemp()
iconset = os.path.join(d, 'AppIcon.iconset')
os.makedirs(iconset)

for s in [16, 32, 128, 256, 512]:
    make_png(s, os.path.join(iconset, f'icon_{s}x{s}.png'))
    if s <= 256:
        make_png(s*2, os.path.join(iconset, f'icon_{s}x{s}@2x.png'))

out = os.path.join(os.path.dirname(__file__), 'Task Managing Manager.app', 'Contents', 'Resources', 'AppIcon.icns')
subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', out], check=True)
shutil.rmtree(d)
print(f'Done: {out}')
