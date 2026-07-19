"""SciSciGPT publication figure style (adapted from the APTO-Discovery standard).

This module is preloaded on every Python sandbox kernel: the rcParams from
sciscigpt.mplstyle already apply to every figure. Import it for the palette
and canvas helpers:

    import sciscigpt_style as style
    fig, ax = style.figure()            # publication canvas, 3:2
    ax.plot(x, y, color=style.COLORS[0])
    plt.show()                          # figures are captured automatically

Design rules (rationale in FIGURE_STANDARDS.md):
- Okabe-Ito colorblind-safe palette in fixed order; one coordinated color
  system per figure; sequential data uses a single ramp (viridis/cividis).
- Quiet chrome: no top/right spines, no grid, thin marks, frameless legend.
- Never encode one variable with two channels (e.g. width AND color).
"""
from pathlib import Path

import matplotlib
matplotlib.style.use(str(Path(__file__).with_name("sciscigpt.mplstyle")))
import matplotlib.pyplot as plt

# Okabe-Ito (Wong, Nature Methods), fixed order — assign in sequence, never cycle
COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7",
          "#E69F00", "#56B4E9", "#F0E442", "#000000"]


def figure(aspect=1.5, nrows=1, ncols=1, **kw):
	"""Publication canvas: 8 in wide, height = width / aspect (3:2 default)."""
	return plt.subplots(nrows, ncols, figsize=(8.0, 8.0 / aspect), **kw)


def panel_labels(axes, x=-0.10, y=1.05):
	"""Bold lowercase panel letters (a, b, c, ...) — Nature convention."""
	import numpy as np
	for i, ax in enumerate(np.ravel(axes)):
		ax.text(x, y, chr(ord("a") + i), transform=ax.transAxes,
				fontweight="bold", fontsize=12, va="bottom")
