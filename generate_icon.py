#!/usr/bin/env python3
"""Generate a macOS .icns app icon for Task Managing Manager."""

import subprocess
import os
import tempfile
import struct
import zlib

def create_png(size, output_path):
    """Create a simple PNG icon at the given size."""
    # We'll create the icon using raw PNG generation
    # Icon: dark background with "TMM" text rendered as a simple design

    pixels = []
    for y in range(size):
        row = []
        for x in range(size):
            # Normalized coordinates
            nx = x / size
            ny = y / size

            # Background: dark gradient
            bg_r = int(22 + (ny * 8))
            bg_g = int(22 + (ny * 8))
            bg_b = int(22 + (ny * 8))

            # Border/edge fade
            edge = min(nx, 1-nx, ny, 1-ny)
            border_width = 0.02
            if edge < border_width:
                # Subtle border
                factor = edge / border_width
                bg_r = int(bg_r * factor + 60 * (1 - factor))
                bg_g = int(bg_g * factor + 60 * (1 - factor))
                bg_b = int(bg_b * factor + 60 * (1 - factor))

            # Red accent bar at bottom
            if 0.82 < ny < 0.88 and 0.15 < nx < 0.85:
                bg_r, bg_g, bg_b = 204, 51, 51

            # Silver "T" letter
            # Vertical stem
            if 0.25 < ny < 0.72 and 0.43 < nx < 0.57:
                bg_r, bg_g, bg_b = 192, 192, 198
            # Horizontal top
            if 0.2 < ny < 0.32 and 0.2 < nx < 0.8:
                bg_r, bg_g, bg_b = 192, 192, 198

            row.append((bg_r, bg_g, bg_b, 255))
        pixels.append(row)

    # Write PNG manually
    def write_png(filename, width, height, pixels):
        def make_chunk(chunk_type, data):
            chunk = chunk_type + data
            return struct.pack('>I', len(data)) + chunk + struct.pack('>I', zlib.crc32(chunk) & 0xffffffff)

        header = b'\x89PNG\r\n\x1a\n'
        ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
        ihdr = make_chunk(b'IHDR', ihdr_data)

        raw_data = b''
        for row in pixels:
            raw_data += b'\x00'  # filter byte
            for r, g, b, a in row:
                raw_data += struct.pack('BBBB', r, g, b, a)

        compressed = zlib.compress(raw_data, 9)
        idat = make_chunk(b'IDAT', compressed)
        iend = make_chunk(b'IEND', b'')

        with open(filename, 'wb') as f:
            f.write(header + ihdr + idat + iend)

    write_png(output_path, size, size, pixels)


def main():
    icon_dir = tempfile.mkdtemp()
    iconset = os.path.join(icon_dir, 'AppIcon.iconset')
    os.makedirs(iconset)

    # Generate all required sizes
    sizes = [16, 32, 64, 128, 256, 512]
    for s in sizes:
        create_png(s, os.path.join(iconset, f'icon_{s}x{s}.png'))
        create_png(s * 2, os.path.join(iconset, f'icon_{s}x{s}@2x.png'))

    # Convert iconset to icns
    app_dir = os.path.dirname(os.path.abspath(__file__))
    icns_path = os.path.join(app_dir, 'Task Managing Manager.app', 'Contents', 'Resources', 'AppIcon.icns')

    subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', icns_path], check=True)
    print(f'Icon created: {icns_path}')

    # Cleanup
    import shutil
    shutil.rmtree(icon_dir)


if __name__ == '__main__':
    main()
