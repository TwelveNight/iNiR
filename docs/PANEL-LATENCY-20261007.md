# First-open sidebar latency, 2026-10-07

This follows the [CPU optimization pass](PERFORMANCE-20261007.md). The target
is request-to-first-visible-movement, including the first opening after a
shell restart. The existing `iris.keepPanelsLoaded` option enables the
prewarm policy; its default remains false, and it is true on the measured host.

## Findings and changes

Stage timestamps showed ordinary layout readiness at 4–7 ms, but the native
window's first frame at roughly 78–98 ms. Starting the morph preparation
synchronously alone did not remove that wait. Keeping the native sidebar
surface mapped between openings did: the closed surface is transparent,
has an explicit empty input region, no keyboard focus and no active mixer
delegates or resource polling. Output selection is held only while the
panel is actually opening, open or closing, rather than while it is resident.

Content readiness and one warm frame still gate animation. Preparation can
start immediately once geometry/content are ready; closing cancels a pending
launch, and reversing an active animation retains its origin and spring state.
The motion meter records preparation stages and the surface's activation
count, so activation 1 distinguishes a real first opening from a repeat.

The remaining first-left-opening cost was synchronous mixer identity lookup.
QML Profiler recorded 96 icon existence checks taking about 226 ms, plus
repeated desktop-name normalization. Bounded positive/negative icon caching
and normalized media identity indexing reduce that work. Icon caches reset
with the desktop index, icon-theme configuration/service state and dark mode.

At the user's request, the sidebar now also runs a startup-only metadata
prewarm after Audio is ready. After a 250 ms settling delay it snapshots
existing streams and handles at most one identity per 32 ms timer tick.
Opening a sidebar pauses remaining work. Completion, disabling retention or
destroying the component stops the timers and releases the queue. New streams
after this one pass are resolved normally; there is no ongoing hidden-stream
polling. No panel is opened for prewarming.

## Verification

Same LTS kernel and NVIDIA shell renderer, external HDMI-A-1 at
2560x1440 / 143.995 Hz / scale 1, internal output off. Music was paused in
the baseline and window-retention runs and playing in the final run; CPU
numbers across those workloads are not directly comparable.

| Measurement | Original behavior | Final startup prewarm |
| --- | ---: | ---: |
| First left opening after restart | 368 ms | 30 ms, activation 1 |
| First right opening after restart | 93 ms | 28 ms, activation 1 |
| Later left openings/reopenings | 90–97 ms | 17–25 ms |
| Later right openings/reopenings | 87–105 ms | 12–19 ms |

The intermediate window-retention run, with music still paused, measured
13–22 ms for repeated openings. The final run's synchronous open handler
returned in 8 ms on the first left opening and 2 ms on the first right.

Live startup journal on this host:

- Shell component ready: 14:35:01.071, Asia/Shanghai.
- First shell frame: T+2261 ms.
- Prewarm completed: 14:35:05.549, two mixer identities in 299 ms.
- Both measured first openings had activation count 1; neither panel had
  been manually opened before its first measured opening.

Thus the first-open numbers apply after startup prewarm completes, about
4.5 seconds after shell component completion in this run. Clicking during
initial loading can still encounter work that is not ready. One expensive
identity lookup is not preemptible, although the queue yields between identities.
Retaining native surfaces uses additional graphics memory.

Qt 6 regression checks passed for readiness, cancellation before first frame,
reversal, disposal, empty input masks, output-release policy, bounded cache
invalidation, startup-only warmup, yielding between nodes, pausing, disabling,
empty snapshots and disappearing streams. Existing defaults, panel cache,
field uniforms and performance-contract checks also passed. The deployed
service logged no binding loops, invalid contexts, TypeError, ReferenceError
or NoReply during the final validation.

The final six sequences kept material, surface, origin and clean-end verdicts
valid; the maximum sampled frame gap was 16 ms. The strict pace test still
reports occasional long frames, and one reversal reported a stalled sample.
These are QML animation samples, not KMS presentation timestamps. An earlier
music-playing run had a 1075 ms gap that did not recur in the final run; its
cause was not established, so this change does not claim to eliminate all
animation stalls.

Raw artifacts: `/tmp/inir-latency-before-20261007`,
`/tmp/inir-latency-direct-20261007`, `/tmp/inir-latency-warm-20261007`,
`/tmp/inir-latency-cache-20261007`, `/tmp/inir-latency-preheated-20261007`.
The cold-open QML trace is in `/tmp/inir-latency-cold-profile-20261007`.
Live backups: `~/.config/inir/backups/panel-latency-20261007`.
