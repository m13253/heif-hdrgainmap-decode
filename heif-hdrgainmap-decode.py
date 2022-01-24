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


def scrgb_to_linear(buf: np.ndarray) -> np.ndarray:
    buf_abs = np.abs(buf)
    return np.where(buf_abs <= 0.04045, buf_abs / 12.92, ((buf_abs + 0.055) / 1.055)**2.4) * np.sign(buf)


def main(argv: typing.List[str]) -> None:
    if len(argv) != 4:
        print('Convert HDR photos taken by iPhone 12 (or later) to regular HDR images.')
        print('Usage: heif-gainmap-decode.py <input.heic> <hdrgainmap.png> <output.exr>')
        print()
        print('To obtain the HDR gain map:')
        print('  % brew install libheif')
        print('  % heif-convert IMG_0000.heic IMG_0000.png')
        print()
        print('You will receive two files:')
        print('  * IMG_0000.png:')
        print('      The main image, but we don\'t need it, because we decode HEIC on our own.')
        print('  * IMG_0000-urn:com:apple:photo:2020:aux:hdrgainmap.png:')
        print('      This is the HDR gain map.')
        print()
        print('The output is an scRGB (gamma 1.0) encoded OpenEXR file.')
        print('You need to use an HDR tone-mapping software to edit it before sharing.')
        return
    print(f'Read image: {argv[1]}')
    input = oiio.ImageBuf(argv[1])
    print(f'Read gainmap: {argv[2]}')
    gainmap = oiio.ImageBuf(argv[2])
    print('Converting')

    # Resize gainmap to match image size using bilinear interpolation.
    input_roi = input.roi
    gainmap = oiio.ImageBufAlgo.resample(gainmap, interpolate=True, roi=input_roi)

    # Display P3 uses same EOTF as scRGB
    input_buf = input.get_pixels()
    del input
    input_buf = scrgb_to_linear(input_buf)

    # I don't know if the gainmap is in linear or gamma space. We assume it's linear.
    gainmap_buf = gainmap.get_pixels()
    del gainmap

    # Apply gainmap to input image.
    #
    # This formula is my guess. I don't know if it's correct.
    # But I guess Apple engineers themselves aren't sure either,
    # since the same image renders differently on iPhone and macOS Photos.app.
    #
    # But why 12? I guess it's reasonable to use the same number as HLG (ARIB STD-B67).
    output_buf = input_buf * 12**gainmap_buf
    del input_buf
    del gainmap_buf

    # Convert Display P3 to linear scRGB
    #
    # The algorithm to compute this matrix is from:
    #   http://www.brucelindbloom.com/index.html?Eqn_RGB_XYZ_Matrix.html
    #
    # The primary chromaticities are from:
    #   https://www.color.org/chardata/rgb/DCIP3.xalter
    #
    # Both white points are D65, so we don't need to do chromatic adaptation.
    DisplayP3_to_scRGB = np.array([
        [1.2249402, -0.22494018, -2.2841395e-16],
        [-0.042056955, 1.0420569, 2.563119e-17],
        [-0.019637555, -0.07863604, 1.0982736],
    ], dtype=np.float32)
    output_buf = np.tensordot(DisplayP3_to_scRGB, output_buf, axes=((1, ), (2, ))).transpose(1, 2, 0)
    output_buf = np.ascontiguousarray(output_buf)

    output_spec = oiio.ImageSpec(input_roi.width, input_roi.height, 3, oiio.FLOAT)
    output_spec.attribute("oiio:ColorSpace", "Linear")
    output = oiio.ImageBuf(output_spec)
    assert output.set_pixels(output.roi, output_buf)
    del output_buf

    # Write output image.
    print(f'Write output: {argv[3]}')
    output.write(argv[3], dtype=oiio.FLOAT)


if __name__ == '__main__':
    main(sys.argv)
