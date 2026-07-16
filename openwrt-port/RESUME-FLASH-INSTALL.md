# Resume: finish the persistent NAND flash install (#3)

> **RESOLVED 2026-07-15.** The "most promising direction" below was correct: switched
> the recipe to the `cmcc_a10-stock` scheme (standalone gzip kernel FIT in the `kernel`
> volume + separate squashfs `rootfs` volume, `sysupgrade-tar`), removed all
> fitblk/`rootdisk` config from the DTS, reflashed via `sysupgrade -n` from the
> RAM-booted initramfs. Clean power-cycle NAND boot verified on hardware: stock U-Boot
> `boot from ubi` → ubiblock root → interactive `root@OpenWrt`, nothing over TFTP.
> The `volname` question is moot — no `ubi-volume-fit` node is needed at all.
> Details in `README.md` Phase D. Kept for historical context only.

Everything for the mainline OpenWrt port of the **Vistotek C6130G-5G (Wingtech WT7981P, MT7981)**
is done and **verified via RAM-boot** — WiFi (both bands), MT7531 switch/DSA, all 10 LEDs, all 3
buttons, serial console, and port activity LEDs. The **only** unfinished piece is making the image
**boot persistently from NAND** after `sysupgrade`. This doc has everything needed to finish it.

## The problem (precise)

Our image is `KERNEL_IN_UBI` with `IMAGE/sysupgrade.itb = ... | fit gzip <dtb> external-static-with-rootfs`.
On flash, the NAND UBI ends up with **2 user volumes** (confirmed live via `ubinfo -a`):
- `kernel` — the FIT (kernel + dtb + **rootfs as a loadable**), ~10.7 MiB
- `rootfs_data`

There is **no separate `rootfs` volume** — the rootfs lives inside the FIT, so root must come from
**`fitblk` → `/dev/fit0`**, which requires `chosen/rootdisk` → a `ubi-volume-fit` binding.

Two attempts, both fail differently:
1. **`rootdisk = <&ubi>`** (raw partition): boots verbosely, then **kernel panic — "VFS: Unable to mount
   root fs on unknown-block(0,0)"**, no `root=`, boot-loops. (fitblk never activated.)
2. **`rootdisk = <&ubi_rootdisk>` + `ubi-volume-fit { volname = "kernel"; }` + `bootargs-append =
   " root=/dev/fit0 rootwait"`** (current DTS state): boot from NAND **hangs silently** — no kernel
   console output at all. Can't confirm the config from an initramfs boot (fitblk only activates as the
   *root* device, which initramfs isn't; no `/dev/fit0` or `/dev/ubiblock*` appears there).

Also: **`sysupgrade` hung on its post-write reboot** (the write itself completed — UBI stayed intact).

## Key unresolved question

`volname`. On-device `ubinfo` says the FIT volume is literally named **`kernel`** — but every upstream
filogic NAND board (`abt_asr3000`, `mt7981b-h3c-magic-nx30-pro`, `qihoo-360t7`, `cudy-*-ubootmod`,
`netis-*`) writes `volname = "fit"`. These can't both be right unless their ubinize names the volume
differently. **This must be resolved** — see next steps.

## Most promising direction (try FIRST)

The upstream boards that use the `ubi-volume-fit` scheme mostly ship a **modified U-Boot** (`-ubootmod`
or preloader/FIP artifacts). We keep the **stock MTK U-Boot**, which boots a FIT from the `kernel`
volume via `bootm`. The cleaner match for stock-U-Boot NAND boards is the **classic ubiblock scheme**,
NOT fitblk: a **separate squashfs `rootfs` UBI volume** mounted via `ubiblock`, like the `-stock`
boards do. Compare:
- `target/linux/mediatek/image/filogic.mk` → `Device/cmcc_a10-stock`: uses
  `IMAGE/sysupgrade.bin := sysupgrade-tar` (separate rootfs volume + ubiblock root), **not**
  `fit ... external-static-with-rootfs`.
- Look at how a `-stock` NAND board's DTS + recipe get root (no `rootdisk`/`ubi-volume-fit` needed if
  ubiblock auto-detects the `rootfs` volume).

**Action:** switch our `Device/vistotek_c6130g` recipe away from the `abt_asr3000` (fit-in-ubi) template
toward a `-stock`/ubiblock template, so the rootfs is its own `rootfs` squashfs volume and roots via
ubiblock — which the stock U-Boot's `bootm` of the `kernel` FIT should handle.

## Next steps (ordered)

1. **Isolate the silent hang.** Rebuild the initramfs, re-add `earlycon` to bootargs on the *NAND* boot
   (need to see if it's U-Boot's NAND read/`bootm` hanging vs the kernel booting with a dead console).
   Capture what cmdline the stock U-Boot actually passes (grep the flashed boot log for
   `Kernel command line:`). Suspect: `bootargs-append` interacting badly, or no `console=` on the
   stock-U-Boot cmdline (then rely on `stdout-path`, which needs `uart0` enabled — already fixed).
2. **Resolve `volname`.** Either (a) rebuild with `volname = "fit"` and do ONE clean NAND-boot test, or
   better (b) go the ubiblock route (step in "most promising direction") and drop fitblk entirely.
3. **Fix the `sysupgrade` hang.** It completed the write but hung on reboot. Test `sysupgrade -v` and
   watch; may just need a manual `reboot -f` after, or it's a stuck process during "closing shell
   sessions".
4. Each change = incremental rebuild (`docker start owrt-build`, ~12 min, toolchain cached) → verify
   DTB/recipe → reflash → **clean power-cycle NAND-boot test** (the only real test).

## Environment / how to drive it

- **Files:** repo `/Users/alex/vistotek-5g-cpe/`. Backups: `ubi.bin`, `ubi2.bin`, `dump.bin`.
  Port files: `openwrt-port/` (DTS `mt7981b-vistotek-c6130g.dts`, `README.md`, `docker/build.sh` +
  `add_leds.py` + `inject_device.py`, `tftp/`, `artifacts/`). OpenWrt tree: `openwrt/` with our device
  in `target/linux/mediatek/image/filogic.mk` (`Device/vistotek_c6130g`) and DTS in
  `target/linux/mediatek/dts/`.
- **Build:** Docker container `owrt-build` holds the full cached toolchain. `docker start owrt-build`
  re-runs `openwrt-port/docker/build.sh` (idempotent incremental: copies DTS, injects leds, cleans
  kernel+base-files, `make`). Watch `openwrt-port/build.log`; artifacts land in `openwrt-port/artifacts/`.
  Do NOT build on the macOS FS (case-insensitive) — the container builds on its own FS.
- **Serial (serial-mcp):** `/dev/cu.usbserial-0001` (CP2102), 115200 8N1. Trap autoboot with
  `serial_wait_for` pattern `Hit any key to stop autoboot`, `respond " "`; then to reach the U-Boot
  console send hex `1B 5B 42`×7 + `0D` (7×DOWN, ENTER). Close the port when done.
- **U-Boot net / TFTP:** U-Boot `ipaddr 192.168.2.1`, `serverip 192.168.2.88`. Mac `en8` must be
  `192.168.2.88` (`sudo ifconfig en8 192.168.2.88 255.255.255.0 up`) and run the TFTP server:
  `sudo dnsmasq --no-daemon --port=0 --enable-tftp --tftp-root=/Users/alex/vistotek-5g-cpe/openwrt-port/tftp --tftp-no-blocksize --interface=en8 --bind-interfaces --log-queries`
  (needs sudo — user runs it). `en8` also has alias `192.168.1.10` for the LAN.
- **RAM-boot recipe** (always works, independent of NAND): at `MT7981>`:
  `setenv bootargs 'console=ttyS0,115200n1 clk_ignore_unused'; tftpboot 0x46000000 recovery.itb; bootm 0x46000000`
  (`recovery.itb` = the initramfs; keep it staged in `tftp/`).
- **Flashing:** device (OpenWrt) LAN is `192.168.1.1`, passwordless dropbear
  (`ssh -o PreferredAuthentications=none -o PubkeyAuthentication=no root@192.168.1.1`). `scp -O` the
  `sysupgrade.itb` to `/tmp`, then `sysupgrade -n /tmp/<img>`.
- **Recovery if a flash goes bad:** RAM-boot the initramfs, then `dd` `ubi.bin` back onto the `ubi`
  MTD (mtd7, the NAND `ubi` partition) — or restore per-volume. Stock BL2/U-Boot on NOR is never
  touched. Stock LAN is `192.168.88.1`.
- **Device facts:** MAC `14:C1:FF:07:C6:91`; board_name `vistotek,c6130g`; kernel 6.18.38; the console
  fix (`&uart0 { status="okay" }` + `serial0` alias) is already in the DTS and confirmed working.

## Definition of done for #3
A clean power-cycle → stock U-Boot autoboots from NAND → reaches an interactive `root@OpenWrt` prompt
on serial, `ubus call system board` shows `vistotek,c6130g`, WiFi/switch up — with **nothing** loaded
over TFTP. Then update `README.md` Phase D to done and consider upstreaming.
