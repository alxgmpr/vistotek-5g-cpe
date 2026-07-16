# Design: modem-status LED daemon (`modem-led`) — Vistotek C6130G-5G

**Date:** 2026-07-16
**Status:** approved, implemented (build/flash/verify pending bench reconnect)

## Goal

Drive the four modem indicator LEDs (`blue:4g`, `yellow:4g`, `blue:5g`, `yellow:5g`)
from the Quectel RM520N-GL's **connection state**, while keeping each LED a normal,
user-overridable OpenWrt `config led` entry (so "off" / "always on" still work in LuCI).

## LED semantics

Exactly one LED lit at a time, mirroring the stock firmware's mutual exclusion between
the 4g and 5g pairs (`rootfs/etc/hotplug.d/lte/00-signal`). The pair encodes the
registered radio technology; blue-vs-yellow encodes connection state (not signal bars):

| Modem state | LED |
|---|---|
| Registered on 5G (SA or NSA) + data session up | `blue:5g` |
| Registered on 5G, no data session yet | `yellow:5g` |
| Registered on LTE + data session up | `blue:4g` |
| Registered on LTE, no data session | `yellow:4g` |
| No service / searching / modem off | all four off |

"4g pair" = any non-5G cellular RAT (LTE/WCDMA/…).

## State detection (self-contained, AT port only)

A small raw-AT helper in the init script talks to `/dev/ttyUSB2` (no extra package,
no dependency on how `wan` is later configured):

- **RAT** — `AT+QENG="servingcell"`: `NR5G-SA`/`NR5G-NSA` ⇒ 5g; `LTE`/`WCDMA`/`TD-SCDMA`/`GSM`/`CDMA`/`HDR` ⇒ 4g; else none.
- **Data session up** — `AT+CGACT?`: any context in state `1` (`+CGACT: <cid>,1`) ⇒ blue; else yellow.
- No serving cell ⇒ `off`.

The helper opens the tty read/write on fd 8, writes the command, and reads response
lines with a per-line 2 s timeout, so an absent/dead modem returns quickly (→ `off`).

## Override contract (the key requirement)

The daemon **only writes an LED whose active kernel trigger is `none`.** Before touching
each LED it reads `/sys/class/leds/<led>/trigger`; if the active `[bracketed]` trigger is
anything other than `none`, it leaves that LED entirely alone. Therefore, in
LuCI → System → LED Configuration:

- **Always on** → set the LED's trigger to `default-on`; the daemon backs off, the kernel holds it on.
- **Blink / bind to something else** → any trigger (`timer`, `netdev`, …); the daemon backs off.
- **Turn the whole feature off** → `/etc/init.d/modem-led disable` (or `uci set modem_led.globals.enabled=0; /etc/init.d/modem-led stop`); the daemon clears the LEDs it owns and stops.

The four LEDs ship as named `config led` entries (via `01_leds`, trigger `none`, default
off) so they appear in LuCI and default to daemon control. `sysupgrade -n` regenerates
this cleanly.

## Components

- `files/usr/sbin/modem-led` — standalone engine: the AT helper (`at_cmd`), `detect_state`,
  the trigger-respecting `set_led`, the state→LED `apply`, and subcommands
  `daemon <port> <interval>`, `simulate <state>`, `status`, `off`. The `daemon` poll loop backs
  its `sleep` with `sleep & wait` so a SIGTERM is handled immediately (a plain `sleep` under a
  TERM trap is deferred until the sleep finishes, which delayed procd's stop by up to `interval`).
- `files/etc/init.d/modem-led` — thin procd wrapper (`START=96`, `USE_PROCD=1`). `start_service`
  reads uci and runs `procd_set_param command /usr/sbin/modem-led daemon <port> <interval>`;
  `stop_service` calls `modem-led off`. Extra commands `simulate` and `ledstate` delegate to the
  engine (`ledstate`, not `status`, because `status` is a built-in rc.common command).
  Auto-enables at build time via the `START=` header (the build creates the `S96modem-led`
  rc.d symlink the same way it does `S25modem-power`).

  **Why the engine is a separate script (not an `/etc/init.d/modem-led loop` re-entry):**
  every `rc.common` invocation of an init script holds an flock on
  `/tmp/lock/procd_<svc>.lock` for the life of that process. Running the *poll loop* through
  rc.common therefore holds that lock forever, and every later `stop` (including the
  `K10modem-led` script at reboot/`sysupgrade`) deadlocks on it — observed live: `stop` stuck
  in `do_wait`, loop process holding `fd → /tmp/lock/procd_modem-led.lock`. Execing a plain
  standalone script as the procd command avoids rc.common (and the lock) entirely.
- `files/etc/config/modem_led` — `globals` section: `enabled`, `port` (`/dev/ttyUSB2`), `interval`.
- `docker/add_leds.py` — extends the vistotek `01_leds` block with the four
  `ucidef_set_led_default` entries (idempotent; replaces the whole block).
- `DEVICE_PACKAGES` — no change.

## Verification results

Offline: shell syntax check; unit tests of `detect_state`/`apply` across six scenarios
(5G-SA up, 5G-NSA attached, LTE up, LTE attached, no-service, modem-absent); override-guard
test (`none` → managed; `default-on`/`heartbeat` → skipped). All pass.

On hardware (2026-07-16, flashed via `sysupgrade -n`):
- Service enabled (`S96modem-led`) and running as the standalone engine.
- No SIM → engine `state: off`, all four LEDs `trigger=none brightness=0`.
- `simulate` sweep: each of 5g-up/5g-att/4g-up/4g-att lights exactly the right single LED
  (`blue:5g`/`yellow:5g`/`blue:4g`/`yellow:4g`); `off` clears all.
- Override: with the daemon running, `blue:5g` set to `default-on` stayed lit across a poll
  cycle (daemon left it alone), while a `none`-trigger LED forced on was reclaimed to off.
- `stop` completes (no lock deadlock); after the `sleep & wait` fix it returns promptly.

Not exercised live: the actual AT round-trip to the modem, because the RM520N was powered
off (see caveat) — but the no-service code path (modem absent → `off`) is identical in effect.

## Notes / limits

- NSA detection assumes `AT+QENG="servingcell"` reports an `NR5G-NSA` token in EN-DC; if a
  given firmware reports only the LTE anchor there, NSA would show on the 4g pair. Tunable.
- "Data up" is modem-side (`CGACT`), deliberately decoupled from the host `wan` netdev.
- Repo is not a git repo, so this doc is recorded but not committed.
- **Modem-power caveat (unrelated to this feature):** repeated warm reboots (from iterating on
  flashes) left the RM520N powered off, and PWRKEY pulses did not re-wake it — the known
  `modem-power` warm-reboot race (README Phase E). A cold power cycle of the device restores
  enumeration. When `ttyUSB2` is absent the daemon simply reports `off` (all LEDs dark).
