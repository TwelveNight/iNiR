# Quickshell field binding optimization, 2026-10-07

This records the CPU pass before the subsequent
[first-open latency and startup prewarm work](PANEL-LATENCY-20261007.md).

Applied the [upstream optimization guide](https://github.com/snowarch/iNiR/wiki/OPTIMIZATION)
to Quickshell only. No Niri window settings, renderer selection, kernel,
display modes, session services or visual effects were changed. Music frame
effects remain enabled; media was paused during measurement.

## Change and validation

Qt 6 QML Profiler identified a moving field body invalidating every shader
uniform and shadow slot through the shared shapes array. `IrisField` now keeps
20 stable QObject slots, updates only shapes whose drawing inputs changed,
and reuses the join index when identifiers and their positions are unchanged.
Geometry, radii, joins, glass, paint flags and style changes still propagate;
removed bodies clear their slots immediately. Blur regions and input masks
are unchanged. The separate icon fix uses async decoding and deferred,
lifetime-bound missing-image fallback.

`test-iris-field-slots.py` runs the production field and uniform bindings in
Qt 6, substituting only desktop window/backdrop dependencies. It covers shape
identity reuse, movement, material/style changes, joins/renaming, removals and
the 20-shape limit. `test-smart-app-icon.py` covers cached failures, source
replacement and destruction. Existing input lifetime, panel retention,
identity cache, music pulse/publication, defaults and performance contract
checks also passed. The user confirmed bar, panels, tray and floating-window
input all work after deployment.

## Host measurement

Same LTS 6.18.55 kernel, hybrid GPU mode, NVIDIA shell rendering, HDMI-A-1
2560x1440 at 143.995 Hz and scale 1; internal output disabled in both runs.
Panel retention was enabled in both. Three rounds per left/right panel,
each containing open, close and mid-animation reversal. CPU is percent of
one logical core, averaged over the complete 6.5-second operation sequence.
The warm subset excludes the first round for each side in both versions.

| Scope | Before | After |
| --- | ---: | ---: |
| All six sequences: shell CPU | 24.32% | 19.37% |
| All six sequences: main thread CPU | 12.73% | 8.42% |
| Four warm sequences: shell CPU | 23.73% | 18.00% |
| Four warm sequences: main thread CPU | 12.32% | 7.48% |
| Warm left sequences: shell CPU | 23.42% | 17.54% |
| Warm right sequences: shell CPU | 24.04% | 18.45% |
| Warm mean request-to-first-movement | 92.25 ms | 102.00 ms |
| Warm animation long-frame samples | 17 | 16 |
| Warm maximum sampled gap | 93 ms | 21 ms |
| Quiet 15-second snapshot: shell CPU | 1.29% | 1.42% |
| Quiet snapshot: IPC response range | 23.61–25.16 ms | 22.87–24.32 ms |

These measurements show reduced CPU work, not elimination of input/animation
latency. The first left opening after restart took 364 ms (before: 129 ms);
later openings still took roughly 90–110 ms. The motion meter samples QML
animation passes, not KMS presentation timestamps. Its pace verdict still
fails the strict 144 Hz target. Idle measurements are short snapshots and
GPU utilization includes other applications, so neither proves a universal
idle or GPU improvement. An earlier after-deployment idle sample overlapped
the user's click validation (15.17% CPU), so it was retained separately and
replaced with the quiet snapshot above. Live logs contained no binding loops,
invalid contexts, TypeError, ReferenceError or NoReply after validation.

Raw measurement artifacts were saved in `/tmp/inir-wiki-before-20261007` and
`/tmp/inir-wiki-after-20261007`; QML traces are in
`/tmp/inir-wiki-profile-20261007` and `/tmp/inir-wiki-profile-after-20261007`.
Scoped live backups are under
`~/.config/inir/backups/wiki-quickshell-20261007-1407`.
