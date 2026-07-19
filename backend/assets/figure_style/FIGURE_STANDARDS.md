# SciSciGPT Figure Standards

The style module (`sciscigpt_style.py` + `sciscigpt.mplstyle`, preloaded in every
Python sandbox) makes figures compliant by default. These rules cover the design
decisions the style file cannot make for you. The figure evaluator reviews
against the same standards.

## Form
- Match the chart type to the data's job: magnitude, identity, trend,
  association, network. No decorative charts, no 3D.
- Dense networks: never ship a full hairball. Fade or threshold low-value edges
  to a light neutral gray, highlight the top-k relationships, or facet.

## Color — one coordinated system per figure
- Categorical identity: Okabe-Ito in fixed order (`style.COLORS`), max ~7
  meaningful classes.
- Magnitude: ONE sequential ramp (single hue light-to-dark, or viridis/cividis).
  Diverging: two opposing hues + neutral gray midpoint. Never rainbow/jet.
- Nodes, edges, and accents must come from the same family — no palette clashes.
- Never encode one variable with two channels (e.g. edge width AND edge color);
  pick the stronger channel and drop the redundant colorbar/legend.

## Layout and hierarchy
- The main message dominates; everything else recedes (thin, light, gray).
- No illegible overlaps: edges must not pass under nodes; labels must not
  collide; sizes must not crowd neighbors.
- Aspect near 3:2; no wasted empty bands; whitespace is part of the design.

## Chrome and type
- No top/right spines; hairline or no grid; thin marks; frameless legend only
  when 2+ series need identity — prefer direct labeling.
- Size legends need realistic scale anchors.
- Axis labels carry units; thousands separators; horizontal text wherever it fits.

## Integrity
- Axes start where honesty requires; every plotted number is loaded from the
  data by executed code — never typed in; stated encodings match what is drawn.
