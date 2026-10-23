# ROS brand fonts

The canonical copies of the typefaces ROS uses. Everything else in the
repository takes them from here:

- `scripts/build-debs.sh` stages them into the `ros-fonts` package;
- the console's Docker build copies them into its static assets.

Nothing should carry a second copy.

| File | Family | Role | Licence |
|---|---|---|---|
| `FunnelDisplay[wght].ttf` | Funnel Display | The ROS interface font. Every piece of ROS UI, desktop and web, is set in this. | OFL-1.1 |
| `SpaceGrotesk[wght].ttf` | Space Grotesk | Display and landing pages, kept for brand parity. | OFL-1.1 |

Both are variable fonts with named instances, so `Funnel Display 11` and
`Funnel Display SemiBold 11` resolve the way a static family would.

The fonts are chosen to match the RHost console at
<https://rhost.rw/console/dashboard>, where Funnel Display is the
`--default-font-family` and Space Grotesk is used for the landing sections.

Upstream: <https://github.com/google/fonts> (`ofl/funneldisplay`,
`ofl/spacegrotesk`). Licence texts are beside the fonts and ship in
`/usr/share/doc/ros-fonts/`.

Funnel Display and Space Grotesk cover Latin and Cyrillic only. The fontconfig
rules in `ros-fonts` keep Noto and DejaVu behind them, so text outside that
coverage still renders rather than falling back to boxes.
