# Mainline OpenWrt for the Vistotek C6130G-5G (Wingtech WT7981P)

Mainline OpenWrt (`mediatek/filogic`, kernel 6.18) on the Vistotek C6130G-5G 5G CPE,
replacing the vendor MediaTek-SDK OpenWrt 5.4 image while keeping the stock MediaTek
U-Boot and the Quectel RM520N-GL modem.

**Status: working.** Builds clean, boots persistently from NAND under the stock U-Boot,
and is verified on hardware — WiFi (both bands), the MT7531 switch, all LEDs and buttons,
serial console, and the RM520N modem all come up. The only unexercised path is a live data
dial (no SIM on hand).

## Hardware

| Block | Detail | Mainline |
|---|---|---|
| SoC | MediaTek MT7981B (Filogic 820), 2×A53, 512 MiB DDR3 | first-class |
| WiFi | MT7976 2.4G + 5G | mt76 |
| Switch | MT7531 DSA — lan2, lan3, wan; 2.5G CPU port | yes |
| Modem | Quectel RM520N-GL 5G over USB, AT on `/dev/ttyUSB2` | qmi_wwan / cdc_ether |
| NAND | Winbond SPI-NAND 128 MiB → `ubi` + `ubi2` (A/B), behind NMBM | NMBM |
| NOR | Winbond W25Q32 4 MiB → BL2, env, Factory, FIP, wtinfo, nvram | keep stock |
| U-Boot | MTK 2022.07-rc3, boots a FIT from the UBI `kernel` volume | keep stock |

### GPIO map (all on `&pio`)
- **Keys:** reset 1 (AL), wps 0 (AL), rfkill 7 (AL)
- **Modem:** 5gpower 25, 5gpwrkey 2, 5gsim 15 — switch reset 39
- **LEDs:** status-blue 5, status-red 6, wan 8 (AL), wifi 9, 4g-yellow 10, 5g-blue 11,
  5g-yellow 12, 4g-blue 13, lan2 4 (AL), lan3 22 (AL)

## What works

- **NAND boot** — persistent boot under the stock U-Boot using the classic ubiblock
  scheme (`cmcc_a10-stock` style): a gzip kernel FIT in the `kernel` UBI volume plus a
  separate squashfs `rootfs` volume that is auto-`ubiblock`'d as root. No fitblk, no
  U-Boot changes. (The fitblk / `ubi-volume-fit` scheme was tried first and fails on the
  stock U-Boot — see [openwrt-port/RESUME-FLASH-INSTALL.md](openwrt-port/RESUME-FLASH-INSTALL.md).)
- **Serial console** — needs both `&uart0 { status = "okay" }` and
  `aliases { serial0 = &uart0 }`; the base dtsi ships the UART disabled.
- **WiFi** — both bands via mt76 and the Factory eeprom.
- **Switch** — MT7531 DSA: lan2, lan3, wan.
- **Buttons** — reset, wps, rfkill via `gpio-button-hotplug`.
- **LEDs** — all 10, with default triggers wired in board.d: `netdev` on the port LEDs,
  `heartbeat` on status, and the modem-status daemon on the 4G/5G LEDs (below).
- **Modem** — the RM520N-GL enumerates (ttyUSB0-3, cdc_ether `usb0`) once the T-PHY
  (`&usb_phy`) is enabled and `modem-power` pulses `5gpwrkey` at boot; ECM mode as stock.
- **MAC** — read from the plaintext `wtinfo` header via an nvmem fixed-layout cell (no
  hardcoding, upstreamable). The per-unit MAC lives only in `wtinfo`, not Factory.
- **LuCI** — served at `http://192.168.1.1`.

### 4G/5G indicator LEDs

`modem-led` (a procd service plus the `/usr/sbin/modem-led` engine) polls the RM520N and
lights one LED by connection state: `blue:5g` = 5G online, `yellow:5g` = 5G attached-only,
`blue:4g` / `yellow:4g` = the LTE equivalents, all off = no service. It only drives LEDs
left on the `none` kernel trigger, so a LuCI override (e.g. `default-on` = always on) or
`/etc/init.d/modem-led disable` takes over. Design:
[openwrt-port/docs/2026-07-16-modem-led-design.md](openwrt-port/docs/2026-07-16-modem-led-design.md).

## Building

Everything for the port lives in [`openwrt-port/`](openwrt-port/). `openwrt-port/docker/build.sh`
clones OpenWrt, injects the device tree, the image recipe (`Device/vistotek_c6130g`), and the
board.d / `files/` overlays, then builds the `mediatek/filogic` image. Build in a Linux container
on a case-sensitive filesystem — never a mounted macOS volume. Output lands in
`openwrt-port/artifacts/`:

- `openwrt-mediatek-filogic-vistotek_c6130g-squashfs-sysupgrade.bin` — the flash image
- `openwrt-mediatek-filogic-vistotek_c6130g-initramfs-kernel.bin` — RAM-boot recovery

CI builds the image on every push — see [`.github/workflows/build.yml`](.github/workflows/build.yml).

Standalone DTS sanity check (no full build):

```sh
cd openwrt-port
gcc -E -nostdinc -undef -D__DTS__ -x assembler-with-cpp -I harness \
    -o /tmp/board.pp.dts mt7981b-vistotek-c6130g.dts
dtc -I dts -O dtb -o /tmp/board.dtb /tmp/board.pp.dts
```

## Flashing & recovery

From a running OpenWrt or a RAM-booted initramfs (LAN `192.168.1.1`, passwordless dropbear):

```sh
scp -O openwrt-mediatek-filogic-vistotek_c6130g-squashfs-sysupgrade.bin root@192.168.1.1:/tmp/
ssh root@192.168.1.1 sysupgrade -n /tmp/openwrt-mediatek-filogic-vistotek_c6130g-squashfs-sysupgrade.bin
```

RAM-boot recovery (zero flash writes) from the U-Boot console (`ipaddr 192.168.2.1`,
`serverip 192.168.2.88`):

```
setenv bootargs 'console=ttyS0,115200n1'; tftpboot 0x46000000 recovery.itb; bootm 0x46000000
```

Full restore: TFTP the stock `ubi.bin` back to the `ubi` partition (`mtkupgrade ubi`), or
reflash the NOR from `dump.bin` with a SOIC8 clip. The stock BL2/U-Boot on NOR is never
touched, and the dual UBI (`ubi`/`ubi2`) is a built-in fallback slot.

Recovery assets are kept locally and gitignored (too large for the repo): `dump.bin`
(4 MiB SPI-NOR), `ubi.bin` / `ubi2.bin` (the A/B UBI images), `rootfs/` (extracted stock
squashfs), and `wtinfo_decrypt.py` (the wtinfo/MAC decryptor, key `wtinfo-des-v1`).

## Known issues / TODO

- **Dial test** — blocked on a SIM (`+CME ERROR: 10`). With a SIM: ECM auto-connect or an
  AT dial, wan via DHCP on `usb0`.
- **modem-power warm-reboot race** — the RM520N restarts itself on SoC warm reboots, and
  `modem-power`'s boot pulse can toggle a mid-restart module back off. A cold power cycle
  always recovers it.
- **DTS `[VERIFY]` items** — the MT7531 `reset-gpios` active level and the switch
  `interrupts` line (`<38>`) are best-guesses that work but aren't cross-checked against
  the vendor DTB.
- **Upstreaming** — the DTS and nvmem-MAC story are clean enough to submit; would need a
  wiki page.

For the blow-by-blow NAND-boot debugging and the full bench / serial / TFTP setup, see
[openwrt-port/RESUME-FLASH-INSTALL.md](openwrt-port/RESUME-FLASH-INSTALL.md).
