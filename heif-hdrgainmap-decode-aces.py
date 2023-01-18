#!/usr/bin/env python3

# heif-hdrgainmap-decode
# Copyright (C) 2020  Star Brilliant
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import base64
import sys
import typing
try:
    import OpenImageIO as oiio
except ImportError:
    print('Please install OpenImageIO using:')
    print('  % brew install openimageio')
    sys.exit(1)
try:
    import numpy as np
except ImportError:
    print('Please install NumPy using:')
    print('  % brew install numpy')
    sys.exit(1)


def scRGB_EOTF(buf: np.ndarray) -> np.ndarray:
    buf_abs = np.abs(buf)
    return np.where(buf_abs <= 0.04045, buf_abs / 12.92, ((buf_abs + 0.055) / 1.055)**2.4) * np.sign(buf)


def main(argv: typing.List[str]) -> None:
    if len(argv) != 4:
        print('Convert HDR photos taken by iPhone 12 (or later) to regular HDR images.')
        print('Usage: heif-gainmap-decode-aces.py <input.heic> <hdrgainmap.png> <output.exr>')
        print()
        print('To obtain the HDR gain map:')
        print('  % brew install libheif')
        print('  % heif-convert --with-aux --no-colons IMG_0000.heic IMG_0000.png')
        print()
        print('You will receive two files:')
        print('  * IMG_0000.png:')
        print('      The main image, but we don\'t need it, because we decode HEIC on our own.')
        print('  * IMG_0000-urn_com_apple_photo_2020_aux_hdrgainmap.png:')
        print('      This is the HDR gain map.')
        print()
        print('The output is an ACES 2065-1 encoded OpenEXR file.')
        print('You need to use an HDR tone-mapping software to edit it before sharing.')
        return

    print(f'Read image:   {argv[1]}')
    input = oiio.ImageBuf(argv[1])
    if not input.read():
        raise RuntimeError('Failed to open {}: {}'.format(argv[1], oiio.geterror()))
    print(f'Read gainmap: {argv[2]}')
    gainmap = oiio.ImageBuf(argv[2])
    if not gainmap.read():
        raise RuntimeError('Failed to open {}: {}'.format(argv[2], oiio.geterror()))
    print('Converting...')

    # Resize gainmap to match image size using bilinear interpolation.
    input_roi = input.roi
    gainmap = oiio.ImageBufAlgo.resample(gainmap, interpolate=True, roi=input_roi)

    # Display P3 uses same EOTF as scRGB
    input_buf = input.get_pixels()
    del input
    input_buf = scRGB_EOTF(input_buf)

    # I don't know if the gainmap is in linear or gamma space. We assume it's linear.
    gainmap_buf = gainmap.get_pixels()
    del gainmap

    # Apply gainmap to input image.
    #
    # This formula is my guess. I don't know if it's correct.
    # But I guess Apple engineers themselves aren't sure either,
    # since the same image renders differently on iPhone and macOS Photos.app.
    #
    # But why 8.0? It looks good and it's the same number as scRGB.
    output_buf = input_buf * 8**gainmap_buf
    del input_buf
    del gainmap_buf

    # Convert Display P3 to CIEXYZ, using Y for luminance.
    DisplayP3_to_Y = np.array([0.22897456, 0.69173852, 0.07928691], dtype=np.float32)
    output_Y = output_buf.dot(DisplayP3_to_Y)
    output_Y_max = output_Y.max()
    output_Y_avg = output_Y.mean()
    del output_Y
    print('MaxFALL: {:.2f} (scene referenced)'.format(output_Y_avg))
    print('MaxCLL:  {:.2f} (scene referenced)'.format(output_Y_max))

    # Convert Display P3 to ACES 2065-1.
    # Computed using https://github.com/m13253/colorspace-routines
    DisplayP3_to_ACES2065_1 = np.array([
        [0.5189335, 0.28625659, 0.19480993],
        [0.073859383, 0.81984516, 0.10629545],
        [-0.00030701137, 0.0438070503, 0.95649996],
    ], dtype=np.float32)
    output_buf = np.tensordot(DisplayP3_to_ACES2065_1, output_buf, axes=((1, ), (2, ))).transpose(1, 2, 0)
    output_buf = np.ascontiguousarray(output_buf)

    output_spec = oiio.ImageSpec(input_roi.width, input_roi.height, 3, oiio.FLOAT)
    # TIFF uses the "ICCProfile" tag, but OpenEXR does not.
    output_spec.attribute('ICCProfile', 'uint8[1072]', np.asarray(bytearray(base64.b64decode(
        # ACES-elle-V4-g10.icc from https://github.com/ellelstone/elles_icc_profiles
        # Copyright 2016, Elle Stone, CC-BY-SA 3.0 Unported.
        'AAAEMGxjbXMEMAAAbW50clJHQiBYWVogB+AABQABAA0AGQABYWNzcCpuaXgAAAAAAAAAAA'
        'AAAAAAAAAAAAAAAAAAAAAAAPbWAAEAAAAA0y1sY21zAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMZGVzYwAAARQAAABGY3BydAAAAVwAAAE2d3'
        'RwdAAAApQAAAAUY2hhZAAAAqgAAAAsclhZWgAAAtQAAAAUYlhZWgAAAugAAAAUZ1hZWgAA'
        'AvwAAAAUclRSQwAAAxAAAAAQZ1RSQwAAAxAAAAAQYlRSQwAAAxAAAAAQY2hybQAAAyAAAA'
        'AkZG1uZAAAA0QAAADqbWx1YwAAAAAAAAABAAAADGVuVVMAAAAqAAAAHABBAEMARQBTAC0A'
        'ZQBsAGwAZQAtAFYANAAtAGcAMQAwAC4AaQBjAGMAAAAAbWx1YwAAAAAAAAABAAAADGVuVV'
        'MAAAEaAAAAHABDAG8AcAB5AHIAaQBnAGgAdAAgADIAMAAxADYALAAgAEUAbABsAGUAIABT'
        'AHQAbwBuAGUAIAAoAGgAdAB0AHAAOgAvAC8AbgBpAG4AZQBkAGUAZwByAGUAZQBzAGIAZQ'
        'BsAG8AdwAuAGMAbwBtAC8AKQAsACAAQwBDAC0AQgBZAC0AUwBBACAAMwAuADAAIABVAG4A'
        'cABvAHIAdABlAGQAIAAoAGgAdAB0AHAAcwA6AC8ALwBjAHIAZQBhAHQAaQB2AGUAYwBvAG'
        '0AbQBvAG4AcwAuAG8AcgBnAC8AbABpAGMAZQBuAHMAZQBzAC8AYgB5AC0AcwBhAC8AMwAu'
        'ADAALwBsAGUAZwBhAGwAYwBvAGQAZQApAC4AAAAAWFlaIAAAAAAAAPbWAAEAAAAA0y1zZj'
        'MyAAAAAAABCL8AAARO///2aAAABYkAAP4D///8vv///jkAAALmAADQIlhZWiAAAAAAAAD9'
        'qwAAXKX///9OWFlaIAAAAAD///YJ///qZAAA0cJYWVogAAAAAAAAAyIAALj3AAACHXBhcm'
        'EAAAAAAAAAAAABAABjaHJtAAAAAAADAAAAALwWAABD6wAAAAAAAQAAAAAAB///7EltbHVj'
        'AAAAAAAAAAEAAAAMZW5VUwAAAM4AAAAcAEEAQwBFAFMAIABjAGgAcgBvAG0AYQB0AGkAYw'
        'BpAHQAaQBlAHMAIABmAHIAbwBtACAAVABCAC0AMgAwADEANAAtADAAMAA0ACwAIABoAHQA'
        'dABwADoALwAvAHcAdwB3AC4AbwBzAGMAYQByAHMALgBvAHIAZwAvAHMAYwBpAGUAbgBjAG'
        'UALQB0AGUAYwBoAG4AbwBsAG8AZwB5AC8AYQBjAGUAcwAvAGEAYwBlAHMALQBkAG8AYwB1'
        'AG0AZQBuAHQAYQB0AGkAbwBuAAAAAA=='
    )), dtype=np.uint8))
    # OpenEXR uses the "chromaticities" tag.
    output_spec.attribute('chromaticities', 'float[8]', (
        # https://acescentral.com/aces-documentation/
        # https://j.mp/TB-2014-004
        0.73470, 0.26530, 0.00000, 1.00000, 0.00010, -0.07700,
        # https://j.mp/TB-2018-001
        0.32168, 0.33767,
    ))
    output_spec.attribute('oiio:ColorSpace', 'Linear')
    output = oiio.ImageBuf(output_spec)
    assert output.set_pixels(output.roi, output_buf)
    del output_buf

    # Write output image.
    print(f'Write image: {argv[3]}')
    if not output.write(argv[3], dtype=oiio.FLOAT):
        raise RuntimeError('Failed to save {}: {}'.format(argv[3], oiio.geterror()))


if __name__ == '__main__':
    main(sys.argv)
