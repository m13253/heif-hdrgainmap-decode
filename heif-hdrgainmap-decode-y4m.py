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


def scRGB_EOTF(buf: np.ndarray) -> np.ndarray:
    buf_abs = np.abs(buf)
    return np.where(buf_abs <= 0.04045, buf_abs / 12.92, ((buf_abs + 0.055) / 1.055)**2.4) * np.sign(buf)


def PQ_OETF(buf: np.ndarray) -> np.ndarray:
    m1 = 2610 / 16384
    m2 = 2523 / 4096 * 128
    c1 = 3424 / 4096
    c2 = 2413 / 4096 * 32
    c3 = 2392 / 4096 * 32
    Y = np.abs(buf) / 10000
    return ((c1 + c2 * Y**m1) / (1 + c3 * Y**m1))**m2 * np.sign(buf)


def main(argv: typing.List[str]) -> None:
    if len(argv) not in (4, 5):
        print('Convert HDR photos taken by iPhone 12 (or later) to regular HDR images.')
        print('Usage: heif-gainmap-decode-y4m.py <input.heic> <hdrgainmap.png> <output.y4m> <Reference White, default to 100 cd/m\xb2>')
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
        print('The output is a 12-bit YUV4MPEG2 file.')
        print('  Pixel format:      yuv444p12le')
        print('  Signal range:      Limited')
        print('  Color primaries:   (9) BT.2020')
        print('  Transfer function: (16) SMPTE ST 2084')
        print('  Color matrix:      (9) BT.2020 Non-constant Luminance')
        print()
        print('You can further convert it into a 12-bit HEIF/AVIF file:')
        print('  % avifenc --cicp 9/16/9 --min 1 --max 12 IMG_0000.y4m IMG_0000.avif')
        print('  (Note: some decoders can\'t decode 12-bit files.)')
        print('or a 10-bit HEVC video:')
        print('  % ffmpeg -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc \\')
        print('    -i IMG_0000.y4m -vf tpad=stop_mode=clone:stop_duration=10 \\')
        print('    -pix_fmt yuv420p10le -c:v libx265 -tag:v hvc1 -crf:v 22 \\')
        print('    -x265-params colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc \\')
        print('    -movflags +faststart IMG_0000.mp4')
        return

    print(f'Read image:   {argv[1]}')
    input = oiio.ImageBuf(argv[1])
    if not input.read():
        raise RuntimeError('Failed to open {}: {}'.format(argv[1], oiio.geterror()))
    print(f'Read gainmap: {argv[2]}')
    gainmap = oiio.ImageBuf(argv[2])
    if not gainmap.read():
        raise RuntimeError('Failed to open {}: {}'.format(argv[2], oiio.geterror()))
    # There are different reference white standards,
    # including 80 cd/m², 100 cd/m², 120 cd/m², 203 cd/m².
    # Let's set the default value to be 100 cd/m²,
    # which matches BT.709 and the AVIF decoder in Google Chrome.
    reference_white = float(argv[4]) if len(argv) > 4 else 100.0
    print('Reference white: {:.2f} cd/m\xb2'.format(reference_white))
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
    # FIXME: This algorithm is not the standard definition.
    DisplayP3_to_Y = np.array([0.22897456, 0.69173852, 0.07928691], dtype=np.float32)
    output_Y = output_buf.dot(DisplayP3_to_Y)
    output_Y_max = output_Y.max() * reference_white
    output_Y_avg = output_Y.mean() * reference_white
    del output_Y
    print('MaxFALL: {:.2f} cd/m\xb2 (estimate)'.format(output_Y_avg))
    print('MaxCLL:  {:.2f} cd/m\xb2 (estimate)'.format(output_Y_max))

    # Convert Display P3 to BT.2020.
    # Computed using https://github.com/m13253/colorspace-routines
    DisplayP3_to_BT2020 = np.array([
        [0.75383303, 0.19859737, 0.047569597],
        [0.045743849, 0.9417772, 0.012478931],
        [-0.00121034035, 0.017601717, 0.9836086],
    ], dtype=np.float32)
    output_buf = np.tensordot(DisplayP3_to_BT2020, output_buf, axes=((1, ), (2, ))).transpose(1, 2, 0)
    output_buf = np.ascontiguousarray(output_buf)
    output_buf *= reference_white
    output_buf = PQ_OETF(output_buf)

    # Non-Constant Luminance Y'Cb'Cr' signal format
    # ITU-R BT.2100, Table 6
    BT2020_RGB_to_YCbCr = np.array([
        [0.2627, 0.6780, 0.0593],
        [-0.2627 / 1.8814, -0.6780 / 1.8804, 0.5],
        [0.5, -0.6780 / 1.4746, -0.0593 / 1.4746],
    ], dtype=np.float32)
    output_buf = np.tensordot(BT2020_RGB_to_YCbCr, output_buf, axes=((1, ), (2, ))).transpose(1, 2, 0)
    output_buf = np.ascontiguousarray(output_buf)

    # Convert to 12-bit representation.
    # 12-bit is the minimal bit depth to eliminate visible banding without dithering.
    # You may want to reduce to 10-bit before sharing.
    output_buf[:, :, 0] *= 3504
    output_buf[:, :, 0] += 256
    output_buf[:, :, 1:] *= 3584
    output_buf[:, :, 1:] += 2048
    output_buf.round(out=output_buf)
    output_buf[:, :, 0].clip(256, 3760, out=output_buf[:, :, 0])
    output_buf[:, :, 1:].clip(256, 3840, out=output_buf[:, :, 1:])

    output_planar = output_buf.astype('<u2').transpose(2, 0, 1)
    output_planar = np.ascontiguousarray(output_planar)
    del output_buf

    # Write output image.
    print(f'Write image: {argv[3]}')
    with open(argv[3], 'wb') as f:
        f.write(f'YUV4MPEG2 W{output_planar.shape[2]} H{output_planar.shape[1]} F1:1 Ip A1:1 C444p12 XYSCSS=444P12 XCOLORRANGE=LIMITED\nFRAME\n'.encode('utf-8', 'replace'))
        f.write(output_planar.tobytes('C'))


if __name__ == '__main__':
    main(sys.argv)
