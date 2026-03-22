# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Matplotlib renderers for use with :func:`dash_capture.graph_exporter`."""

from __future__ import annotations

import io

import matplotlib.pyplot as plt

plt.switch_backend("agg")


def snapshot_renderer(_target, _snapshot_img, title: str = ""):
    """Render a browser snapshot as a matplotlib figure.

    Parameters
    ----------
    _target :
        File-like object to write to (injected by the export button).
    _snapshot_img :
        Callable that returns raw PNG bytes of the captured graph
        (injected by the export button).
    title :
        Optional axes title drawn by matplotlib on top of the snapshot.
    """
    img = plt.imread(io.BytesIO(_snapshot_img()))
    dpi = 300
    h, w = img.shape[:2]
    fig, ax = plt.subplots(figsize=(w / dpi, h / dpi), dpi=dpi)
    try:
        ax.imshow(img)
        ax.axis("off")
        if title:
            ax.set_title(title)
        fig.savefig(_target, format="png", bbox_inches="tight", pad_inches=0)
    finally:
        plt.close(fig)
