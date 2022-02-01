heif-hdrgainmap-decode
======================

Convert HDR photos taken by iPhone 12 (or later) to regular HDR images.

## Installation

First, make sure you have the following packages installed:
- Python 3.9 or later
- libheif
- NumPy
- OpenImageIO

On macOS, you can install these packages with Homebrew:
```bash
brew install python libheif numpy openimageio
```

## Usage

1. Copy the photo from your iPhone **losslessly** to your computer.

   You can use either AirDrop or a USB cable. But make sure the file is not
   modified by any software that doesn't support iPhone HDR photo.

   Let's assume the filename is `IMG_0000.heic`.

2. Extract the HDR gain map from the photo:

   ```bash
   heif-convert IMG_0000.heic IMG_0000.png
   ```

   You will receive two files:

   * `IMG_0000.png`:
     The main image, but we don't need it, because we decode HEIC on our own.

   * `IMG_0000-urn:com:apple:photo:2020:aux:hdrgainmap.png`:
     This is the HDR gain map.

3. Run the following command to convert the photo to regular HDR image:

   ```bash
   ./heif-hdrgainmap-decode.py IMG_0000.heic IMG_0000-urn:com:apple:photo:2020:aux:hdrgainmap.png IMG_0000_HDR.png
   ```

4. Remove the temporary files.

   ```bash
   rm -fv IMG_0000.png IMG_0000-*.png
   ```

5. The output is a BT.2020 (PQ) encoded PNG-48 file.

   If you plan to encode it back to HEIC, use "nclx" metadata:

   color_primaries: 9, transfer_characteristics: 16,
   matrix_coefficients: 9, full_range_flag: 1.

   Warning:

   Libheif currently has issues creating "nclx" metadata.

   Most Apple software have trouble displaying HDR HEIC images as of now.

## Technical details

The HDR gain map is encoded in the HEIF file as an auxiliary image (`auxC`).
Both the main image and the HDR gain map is encoded in 8-bits precision.
If the image viewer doesn't support this format, it will only show the main SDR
image, effectively becoming a tone mapping mechanism.

The exact algorithm is not disclosed, even the Photos app on iPhone and Mac
renders differently. Therefore, I assume there is no clear documentation even
inside Apple, Inc. **The following is a rough guess of how it works:**

To render the HDR version of the image, we need to multiply the SDR luminance
with “a constant raised to the power of the gain value”. If the gain value is
0.0, the image is unchanged. If the gain value is 1.0 (actually 255),
the luminance is multiplied by that constant.

I choose the constant to be 8.0 because it looks good, and it matches scRGB.

## License

The program is licensed under the GPLv3 (or later) license.
However, my algorithm can be freely used as long as you rewrite the code.

## Disclaimer

Please make sure to declare that **the algorithm is only a rough guess**
whenever you distribute or derive this algorithm. This is to prevent misleading
anyone that wants to study or improve the algorithm.
