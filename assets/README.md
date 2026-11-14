# Assets

Pre-rendered pictures that the report embeds (as data: URIs), so the browser does not have to compute
SVG noise and blur filters while scrolling:

| File | What |
|---|---|
| `wood-light.webp`, `wood-dark.webp` | maple and walnut square textures (640×640, the whole 8×8 area) |
| `wood-frame.webp` | dark wooden frame (720×720) |
| `bg-night.webp`, `bg-fog.webp`, `bg-king.webp` | faded chess scenes for the page background (1600×1000) |

They were drawn from scratch as SVG (`board_svg.py`: the wood filters in the old DEFS and `background_svg()`),
rendered once with headless Edge and saved as WebP with Pillow. No photos or third-party images.
