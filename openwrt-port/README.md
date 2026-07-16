# Mainline OpenWrt port — Vistotek C6130G-5G (Wingtech WT7981P)

Goal: run **mainline OpenWrt (`mediatek/filogic`)** on this 5G CPE, replacing the
vendor MediaTek-SDK OpenWrt 5.4 image, while **keeping the stock MTK U-Boot** and
the Quectel RM520N-GL working over USB.

Status: **recon complete, first-draft DTS written.** Not yet built or flashed.

---

## 1. Hardware (confirmed from dumps + live device)

| Block | Detail | Mainline support |
|---|---|---|
| SoC | MediaTek **MT7981B** (Filogic 820), 2×A53, 512 MiB DDR3 | ✅ first-class |
| WiFi | **MT7976** 2.4G+5G (vendor uses proprietary `mt_wifi`) | ✅ via **mt76** |
| Switch | **MT7531** DSA — lan2, lan3, wan; 2.5G CPU port | ✅ |
| Modem | **Quectel RM520N-GL** 5G, USB (QMI), AT on `/dev/ttyUSB2` | ✅ `qmi_wwan` + `quectel-CM` |
| NAND | Winbond SPI-NAND 128 MiB → `ubi` + `ubi2` (A/B), behind **NMBM** | ✅ NMBM in mediatek target |
| NOR | Winbond W25Q32 4 MiB → BL2, u-boot-env, Factory, FIP, woem, wtinfo, nvram | ✅ |
| U-Boot | MTK 2022.07-rc3, boots FIT from UBI `kernel` volume; bootmenu + TFTP recovery | keep as-is |

### GPIO map (from carved vendor DTB — all on `&pio`)
- **Keys:** reset = pin 1 (AL), wps = pin 0 (AL), rfkill = pin 7 (AL)
- **Modem (RM520N):** `5gpower` = pin 25, `5gpwrkey` = pin 2, `5gsim` = pin 15
- **Switch reset:** pin 39
- **LEDs:** status-blue 5, status-red 6, wan 8 (AL), wifi 9, 4g-yellow 10, 5g-blue 11,
  5g-yellow 12, 4g-blue 13, lan2 4 (AL), lan3 22 (AL)

---

## 2. Port strategy — hybrid of two upstream boards

No exact profile exists upstream (checked `target/linux/mediatek/dts`). Assemble from:

- **`mt7981b-gatonetworks-gdsp`** — MT7981 **+ RM520N** 5G CPE. Source of the modem/USB
  power rails, mt76 `&wifi` + Factory-eeprom nvmem, and MAC-cell scheme. **Closest twin.**
- **A filogic SPI-NAND + UBI board** (e.g. `cmcc-rax3000m`, `cudy-*-ubootmod`) — source of
  the NAND controller node, `ubi` partition, and the FIT-in-UBI sysupgrade recipe.
  (GDSP is NOR-only, so its storage half does not apply.)

Result → the draft **`mt7981b-vistotek-c6130g.dts`** in this folder.

### The one genuine divergence: MAC address
GDSP reads its MAC from `Factory@4/@24/@2a`. **On this board those bytes are zero** — the
per-unit MAC (`14:C1:FF:07:C6:91`) lives only in the **DES-encrypted `wtinfo`** partition,
which mainline won't decrypt. Options, pick one:
1. **Hardcode** the MAC in the DTS (fine for a single harvested unit).
2. **Boot hook**: a `/etc/board.d` or preinit script that runs the `wtinfo` DES decrypt
   (`../wtinfo_decrypt.py` logic, key `wtinfo-des-v1`) and sets the MAC from the JSON.
3. Accept an mt76-derived MAC (cosmetic; fine for bench use).

---

## 3. Work breakdown

### Phase A — build environment
- [x] OpenWrt cloned (shallow) to `../openwrt` (kernel **6.18**, target `mediatek/filogic`).
- [x] Templates identified: `mt7981b-gatonetworks-gdsp.dts` (modem/USB/NOR),
      `mt7981b-cudy-wr3000-nand.dtsi` (SPI-NAND/UBI).
- [ ] (Phase C) full `mediatek/filogic` build — needs Linux/Docker (macOS can't build host tools).

Reproduce the standalone DTS check:
```sh
gcc -E -nostdinc -undef -D__DTS__ -x assembler-with-cpp -I harness \
    -o /tmp/board.pp.dts mt7981b-vistotek-c6130g.dts
dtc -I dts -O dtb -o /tmp/board.dtb /tmp/board.pp.dts    # exit 0, DTB built
```

### Phase B — device tree  *(mostly done — see the DTS in this folder)*
- [x] Controller node labels **resolved** against OpenWrt's filogic dtsi:
      `&spi0` = SPI-NAND (`spi@1100a000`), `&spi2` = SPI-NOR (`spi@11009000`),
      switch under `&mdio_bus`, `&mdio_pins` is base-provided, flash pin groups
      (`spi0_flash_pins`/`spi2_flash_pins`) are board-defined in `&pio`.
- [x] MAC strategy: **hardcoded** `14:C1:FF:07:C6:91` (single unit). Swap for a
      wtinfo-decrypt hook if generalising.
- [ ] Still `[VERIFY]` on bench: MT7531 reset-gpios level, the switch `interrupts`
      line (guessed `<38>`), and modem power-on ordering/polarity.
- [x] **`dtc`-compiled clean** (harness validation): DTB builds, `dtc` exit 0, zero
      errors; 9 phandles resolve with no dangling refs; all nodes round-trip
      (flashes, MT7531 ports, modem export, wtinfo, hardcoded MAC). Harness lives in
      `harness/` (real dt-bindings + a SoC stub). The only warnings are stub-node
      `unit_address_vs_reg` artifacts that vanish against the real `mt7981b.dtsi`.
      Confirmed all referenced labels exist via OpenWrt's
      `patches-6.18/117-complete-mt7981b-dtsi.patch`.
- [ ] Final `dtc` against the real patched dtsi happens automatically in the Phase-C build.

### Phase C — image definition ✅ BUILT
- [x] `Device/vistotek_c6130g` added to `image/filogic.mk`. Originally modeled on
      `abt_asr3000` (fit-in-UBI + fitblk), **switched to the `cmcc_a10-stock` scheme**
      after the fitblk root failed on the stock U-Boot (see Phase D): standalone gzip
      kernel FIT in the `kernel` UBI volume + separate squashfs `rootfs` volume,
      `IMAGE/sysupgrade.bin := sysupgrade-tar` (`BLOCKSIZE 128k`, `PAGESIZE 2048`,
      `KERNEL_IN_UBI`, `UBINIZE_OPTS -E 5`).
      `DEVICE_PACKAGES` = mt76 (`kmod-mt7915e`+`kmod-mt7981-firmware`+`mt7981-wo-firmware`)
      + modem (`kmod-usb3`,`kmod-usb-net-qmi-wwan`,`kmod-usb-serial-option`,`uqmi`).
      Preloader/FIP artifacts **omitted** (keep stock U-Boot; no U-Boot board config).
- [x] **Full OpenWrt build succeeded** (Docker/Debian, kernel **6.18.38**), exit 0.
      Output in `artifacts/`:
      - `...vistotek_c6130g-squashfs-sysupgrade.bin` (11.3 MB) — flash image (tar:
        kernel FIT + squashfs root)
      - `...vistotek_c6130g-initramfs-kernel.bin` (9.3 MB) — RAM-boot recovery
      - `...vistotek_c6130g.manifest`
      DTS compiled clean against the real patched `mt7981b.dtsi`.
- Rebuild: `docker/build.sh` (clones OpenWrt, injects DTS + device via
  `docker/inject_device.py`, configs `DEVICE_vistotek_c6130g`, builds). Build on a
  case-sensitive FS (the container's own), never a mounted macOS volume.

### Bring-up verified on real hardware (RAM-boot, initramfs)
All tested live over serial + network on the built image:
- **Serial console** — was broken (no output past "disabling unused clocks" / `procd: failed to set stdio`).
  Root cause (confirmed via live DT): base dtsi ships `serial@11002000` **disabled**, and the DTS never
  enabled it. Fix = `&uart0 { status = "okay" }` **plus** `aliases { serial0 = &uart0 }`. Interactive
  `root@OpenWrt` shell confirmed. (`clk_ignore_unused` no longer needed once the UART driver holds the clock.)
- **WiFi** — 2.4 GHz *and* 5 GHz APs brought up (hostapd AP-ENABLED, 802.11ax, mt76, MAC 14:C1:FF:07:C6:91).
- **Switch/DSA** — lan2 link + br-lan forwarding; lan3/wan present.
- **LEDs** — all 10 GPIOs verified against the case. Corrections applied to the DTS:
  the LAN2/LAN3/WAN port LEDs are **yellow**, not blue (labels fixed). Power LED is hardwired-constant.
- **Buttons** — reset (pin 1), WPS (pin 0), rfkill (pin 7) all emit correct `gpio-button-hotplug` events.
- **Port activity LED** — `netdev` trigger gives solid-on-link + flicker-on-traffic (verified on lan2).

### Remaining board-file polish
- [x] **Rebuilt + flashed + verified live (2026-07-16).** The `yellow:*` port-LED labels, the
      `01_leds` netdev triggers, and the `02_network` `lan2 lan3`/`wan` interfaces fix (stops LuCI's
      port widget crashing on phantom lan1/lan4) all landed in the running NAND image. Confirmed on the
      live device (`root@192.168.1.1`): `yellow:lan2/lan3/wan` + `blue:wifi` all show `[netdev]` active;
      `board_name vistotek,c6130g`, squashfs `/rom` + ubifs overlay, both WiFi bands up, RM520N
      enumerated (ttyUSB0-3, `usb0` cdc_ether registered), LuCI serving.
- [x] **`blue:status` heartbeat trigger — done + verified live (2026-07-16).** Added
      `ucidef_set_led_heartbeat "status" "STATUS" "blue:status"` to the `01_leds` block (via
      `docker/add_leds.py`, now idempotent — it *replaces* the vistotek block so edits always land on
      incremental rebuilds). Rebuilt, flashed `sysupgrade -n`, clean NAND reboot: `blue:status` reads
      `[heartbeat]` and `uci show system` shows `led_status.trigger='heartbeat'`. Port LEDs still
      `[netdev]`, both phys present, switch links up.
- [x] **5G/4G indicator LEDs — done + verified live (2026-07-16).** procd service
      `files/etc/init.d/modem-led` (thin wrapper) + standalone engine `files/usr/sbin/modem-led`
      (+ `files/etc/config/modem_led`) polls the RM520N over `/dev/ttyUSB2`
      (`AT+QENG="servingcell"` for RAT, `AT+CGACT?` for data session) and drives one LED at a time by
      **connection state** (chosen over signal bars): `blue:5g` = 5G + data up, `yellow:5g` = 5G
      attached-only, `blue:4g`/`yellow:4g` = same for LTE, all off = no service. **User-overridable:**
      the daemon only writes an LED whose kernel trigger is `none`, so setting any other trigger in
      LuCI (`default-on` = always on) takes it out of daemon control; `/etc/init.d/modem-led disable`
      turns the feature off. Four LEDs ship as named `config led` defaults (trigger `none`) via
      `add_leds.py`. Design: `docs/2026-07-16-modem-led-design.md`.
      **Verified on hardware:** service enabled + running; no-SIM → all off; `simulate` sweep lights
      exactly the right single LED per state; `default-on` override respected while `none` LEDs are
      reclaimed by the daemon; `ledstate` shows detail. Two bugs found + fixed during bring-up: (1) the
      loop must be a **standalone engine**, not an `/etc/init.d/... loop` re-entry — the latter holds
      the procd service lock forever and deadlocks every later stop/reboot; (2) `sleep & wait` in the
      loop so SIGTERM stops it in ~1s (was ~5s); (3) `ledstate` command (not `status`, which is a
      built-in rc.common command).
      **Modem-power caveat (pre-existing, unrelated):** the RM520N ended up powered off after the
      iterative warm reboots and PWRKEY pulses didn't re-wake it (README Phase E race). A **cold power
      cycle** restores enumeration; until then the daemon reports `off` (all modem LEDs dark).

### Phase D — first flash (recoverable, bench) ✅ DONE (2026-07-15)
- [x] **RAM-boot first (zero flash writes):** TFTP `...initramfs-kernel.bin` from U-Boot
      (`ipaddr 192.168.2.1`/`serverip 192.168.2.88`) and `bootm`. Confirmed over UART:
      boots, ethernet/switch, WiFi (mt76), LEDs/keys, MAC.
- [x] **Persistent NAND boot.** The original `external-static-with-rootfs` +
      fitblk scheme failed on the stock U-Boot two ways (panic "unable to mount root"
      with `rootdisk = <&ubi>`; silent hang with `ubi-volume-fit`). Fix = drop fitblk
      entirely and use the classic **ubiblock/stock scheme** (`cmcc_a10-stock` style):
      no `rootdisk`/`bootargs` in the DTS at all — the `linux,ubi` partition
      auto-attaches (generic patch 490) and the volume named **`rootfs`** is
      auto-ubiblock'd and set as root (patches 491/493; stock cmdline has no `root=`).
      Flashed via `sysupgrade -n` of the tar from the RAM-booted initramfs
      (default `nand_do_upgrade` path → volumes `kernel` 6.1M / `rootfs` 4.7M /
      `rootfs_data` 40.2M). The earlier `sysupgrade` reboot hang did not recur.
      **Verified: clean power-cycle → stock U-Boot `boot from ubi` → interactive
      `root@OpenWrt` on serial, `board_name vistotek,c6130g`, phy0+phy1, br-lan up —
      nothing over TFTP.**
- [ ] Verify/adjust the `[VERIFY]` DTS items on real hardware (modem power seq,
      MT7531 reset level).

### Phase E — bring-up ✅ (dial test pending SIM)
- [x] WiFi (mt76) up on both bands using Factory eeprom (verified during RAM-boot bring-up).
- [x] **Modem**: root cause of "no USB at all" was the base dtsi shipping the **T-PHY
      (`&usb_phy`) disabled** — enabling it makes xhci probe. Power-on: the module
      starts on a **`5gpwrkey` pulse** (1 → 1 s → 0); the stock-style `5gpower` pulse
      alone does NOT wake it (verified). Stock GPIO inits are `5gpower=0`,
      `5gpwrkey=0`, `5gsim=1` (decoded from stock DTB; DTS fixed to match — 5gpower
      was wrongly 1). `files/etc/init.d/modem-power` (S25) pulses PWRKEY at boot,
      guarded against re-pulsing an already-running module (a pulse would power it
      OFF; note the module also restarts by itself on SoC warm reboots).
      RM520N-GL enumerates SuperSpeed, ttyUSB0-3 (AT on ttyUSB2), and is in **ECM
      mode** (`AT+QCFG="usbnet",1`, as stock) → `kmod-usb-net-cdc-ether` included,
      netdev `usb0` appears. Stock's `5greset` GPIO is vestigial (not in stock DTB;
      stock scripts' writes to it silently fail). **Dial test blocked: no SIM
      inserted** (`+CME ERROR: 10`). With a SIM: ECM auto-connect or AT dial, wan
      via DHCP on `usb0`.
- [x] MAC read from the plaintext `wtinfo` header (offset 0x0a) via nvmem
      fixed-layout — no more hardcoded MAC, upstreamable. Verified on eth0 + both phys.
- [x] LuCI included (`luci` in DEVICE_PACKAGES), serving at http://192.168.1.1.
- Note (build tooling): `build.sh` regenerates `.config` from the seed on every
  incremental build — re-running `make defconfig` alone keeps stale
  "# CONFIG_PACKAGE_x is not set" pins and silently drops packages newly added
  to DEVICE_PACKAGES.

### Phase F — polish
- [ ] LED triggers (wifi activity, wan, signal LEDs via a modem-status script).
- [ ] Submit upstream? (would need clean DTS + non-encrypted MAC story + wiki page.)

---

## 4. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Brick on flash | Keep stock U-Boot; flash via bootmenu/TFTP only. Full backups exist (below). Dual UBI (ubi/ubi2) = built-in fallback slot. |
| Wrong SPI controller labels | `[VERIFY]` against the exact `mt7981.dtsi` in the OpenWrt tree before building. |
| NMBM vs mainline NAND view | mediatek target supports NMBM; if layout mismatches, restore stock UBI over TFTP and adjust. |
| WiFi cal/regulatory off | Factory holds default cal; acceptable for bench. Tune later if needed. |
| Modem won't enumerate | Bench-verify `5gpower`/`5gpwrkey` level + ordering; the GDSP export model is the reference. |

## 5. Recovery assets (already captured, in repo root)
- `dump.bin` — full 4 MiB SPI-NOR (bootloader + factory), md5 known.
- `ubi.bin` — mtd8 active UBI, `dc899411563544cd5ade3285734e9873`.
- `ubi2.bin` — mtd9 backup UBI, `457efc859eab3059d55ff78f69a5b344`.
- `rootfs/` — extracted stock squashfs (for reference: vendor scripts, quectel-CM, etc.).
- `wtinfo_decrypt.py` — MAC/factory-blob decryptor (key `wtinfo-des-v1`).

**Full restore path if needed:** U-Boot → TFTP the stock `ubi.bin` back to the `ubi`
partition (`mtkupgrade ubi`), or rewrite the NOR from `dump.bin` via the SOIC8 clip.

## 6. Open questions to close on the bench
1. Modem power-on sequence/polarity (`5gpower` high, then `5gpwrkey` pulse?).
2. MT7531 reset-gpios active level, and the switch `interrupts` line (guessed `<38>`).
3. Whether the stock U-Boot's FIT/UBI expectations accept a stock-style image or need `-ubootmod`.
4. Confirm `spi0`+`spi2` coexist on this board's pinout (they use distinct SPI0_*/SPI2_* pins — dual-flash bootloader-on-NOR + rootfs-on-NAND is the vendor config, so this should hold).

*(Resolved during drafting: SoC controller labels — see Phase B.)*
