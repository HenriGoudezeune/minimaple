"""ImageTools-subset voor mini-Maple: Read, Write, Create, View, ToGrayscale, ToRGB, Width, Height, NumChannels.

Afbeeldingen zijn MImage-objecten (numpy-floats in [0,1]).  Bestandsnamen worden opgelost t.o.v. de map in de
omgevingsvariabele MINIMAPLE_FILES (standaard: de huidige werkmap); paden die daaruit ontsnappen worden geweigerd.
"""
import os
import numpy as np
import sympy as sp
from .values import maple, MImage, Plot, Str
from .objs import MapleError

PKG = 'ImageTools'
EXTS = {'.png', '.jpg', '.jpeg'}


def files_dir():
    return os.path.realpath(os.environ.get('MINIMAPLE_FILES') or os.getcwd())


def _path(name, must_exist):
    if os.environ.get('MINIMAPLE_PUBLIC') == '1':
        raise MapleError('file access is disabled on the public server')
    name = str(name)
    base = files_dir()
    full = os.path.realpath(os.path.join(base, name))
    if os.path.commonpath([base, full]) != base:
        raise MapleError(f"file access outside the working directory is not allowed: {name}")
    if os.path.splitext(full)[1].lower() not in EXTS:
        raise MapleError("unsupported image format (use .png or .jpg)")
    if must_exist and not os.path.isfile(full):
        raise MapleError(f"cannot open file {name}")
    return full


def _img(x, who):
    if not isinstance(x, MImage):
        raise MapleError(f"invalid input: {who} expects an Image")
    return x


def _to_float_array(M):
    if isinstance(M, MImage):
        return M.data
    if isinstance(M, sp.MatrixBase):
        return np.array(M.tolist(), dtype=float)
    raise MapleError("invalid input: expected a Matrix or an Image")


def _clip(a):
    return np.clip(np.nan_to_num(np.asarray(a, dtype=float)), 0.0, 1.0)


@maple('currentdir')
def currentdir(ctx, *a):
    return Str(files_dir())


@maple('Read', pkg=PKG)
def Read(ctx, name, *rest):
    """Read("file.png"): lees een png/jpg als Image (RGB, floats in 0..1)."""
    import matplotlib.image as mpimg
    path = _path(name, True)
    a = mpimg.imread(path)
    if a.dtype == np.uint8:
        a = a.astype(float) / 255.0
    a = np.asarray(a, dtype=float)
    if a.ndim == 3 and a.shape[2] == 2:       # grijs + alpha
        a = a[:, :, 0]
    elif a.ndim == 3 and a.shape[2] >= 3:
        a = a[:, :, :3]
    elif a.ndim == 3:
        a = a[:, :, 0]
    return MImage(_clip(a))


@maple('Write', pkg=PKG)
def Write(ctx, name, img, *rest):
    """Write("file.png", img): schrijf een Image of Matrix als png/jpg."""
    import matplotlib.image as mpimg
    path = _path(name, False)
    a = _clip(_to_float_array(img))
    mpimg.imsave(path, a, cmap='gray', vmin=0, vmax=1)
    return Str(str(name))


@maple('Create', pkg=PKG)
def Create(ctx, M, *rest):
    """Create(M): maak een grijswaarden-Image van een Matrix (waarden 0..1)."""
    if isinstance(M, MImage):
        return M
    a = _to_float_array(M)
    if a.ndim != 2:
        raise MapleError("invalid input: Create expects a 2-D Matrix")
    return MImage(_clip(a))


def image_plot(img):
    return Plot('image', [{'type': 'image', 'data': img.data}], {}, 2)


@maple('View', 'Embed', pkg=PKG)
def View(ctx, img, *rest):
    """View(img): toon een Image (als plot in web en MCP)."""
    return image_plot(_img(img, 'View'))


@maple('ToGrayscale', pkg=PKG)
def ToGrayscale(ctx, img, *rest):
    img = _img(img, 'ToGrayscale')
    a = img.data
    if a.ndim == 2:
        return img
    return MImage(_clip(a[:, :, 0] * 0.299 + a[:, :, 1] * 0.587 + a[:, :, 2] * 0.114))


@maple('ToRGB', pkg=PKG)
def ToRGB(ctx, img, *rest):
    img = _img(img, 'ToRGB')
    a = img.data
    return img if a.ndim == 3 else MImage(np.stack([a, a, a], axis=2))


@maple('Width', pkg=PKG)
def Width(ctx, img):
    return sp.Integer(_img(img, 'Width').data.shape[1])


@maple('Height', pkg=PKG)
def Height(ctx, img):
    return sp.Integer(_img(img, 'Height').data.shape[0])


@maple('NumChannels', pkg=PKG)
def NumChannels(ctx, img):
    a = _img(img, 'NumChannels').data
    return sp.Integer(1 if a.ndim == 2 else a.shape[2])


def image_to_matrix(img):
    a = img.data
    if a.ndim != 2:
        raise MapleError("color Image: use ToGrayscale first to convert it to a Matrix")
    return sp.Matrix(a.shape[0], a.shape[1], [sp.Float(v) for v in a.ravel()])
