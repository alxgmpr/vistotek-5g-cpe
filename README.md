# Mainline OpenWrt for the Vistotek C6130G-5G (Wingtech WT7981P)

Mainline OpenWrt (`mediatek/filogic`, kernel 6.18) on the Vistotek C6130G-5G 5G CPE,
replacing the vendor MediaTek-SDK OpenWrt 5.4 image while keeping the stock MediaTek
U-Boot and the Quectel RM520N-GL modem.

**Status: working.** Builds clean, boots persistently from NAND under the stock U-Boot, and
is verified on hardware — WiFi (both bands), the MT7531 switch, all LEDs and buttons, serial
console, and the RM520N modem. Only a live data dial is unexercised (no SIM).

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

## Notes on the non-obvious bits

- **NAND boot** — the classic ubiblock scheme (`cmcc_a10-stock` style): a gzip kernel FIT in
  the `kernel` UBI volume plus a separate squashfs `rootfs` volume auto-`ubiblock`'d as root.
  No fitblk, no U-Boot changes (fitblk / `ubi-volume-fit` fails on the stock U-Boot).
- **Serial console** — needs both `&uart0 { status = "okay" }` and
  `aliases { serial0 = &uart0 }`; the base dtsi ships the UART disabled.
- **Modem** — enumerates once the T-PHY (`&usb_phy`) is enabled and `modem-power` pulses the
  `5gpwrkey` GPIO at boot; ECM mode as stock (cdc_ether `usb0`).
- **MAC** — read from the plaintext `wtinfo` header via an nvmem fixed-layout cell; the
  per-unit MAC lives only in `wtinfo`, not Factory.
- **LEDs** — board.d wires `netdev` on the port LEDs and `heartbeat` on status; the four
  4G/5G LEDs are driven by the `modem-led` daemon (below).

### 4G/5G indicator LEDs

`modem-led` (a procd service plus the `/usr/sbin/modem-led` engine) polls the RM520N and
lights one LED by connection state: `blue:5g` = 5G online, `yellow:5g` = 5G attached-only,
`blue:4g` / `yellow:4g` = the LTE equivalents, all off = no service. It only drives LEDs left
on the `none` trigger, so a LuCI override (`default-on` = always on) or
`/etc/init.d/modem-led disable` takes over. Design:
[openwrt-port/docs/2026-07-16-modem-led-design.md](openwrt-port/docs/2026-07-16-modem-led-design.md).

## Building

Everything lives in [`openwrt-port/`](openwrt-port/). `docker/build.sh` clones OpenWrt,
injects the device tree, image recipe (`Device/vistotek_c6130g`), and board.d / `files/`
overlays, then builds the `mediatek/filogic` image in a Linux container (case-sensitive FS).
Output → `openwrt-port/artifacts/`: `…-squashfs-sysupgrade.bin` to flash,
`…-initramfs-kernel.bin` for RAM-boot recovery. CI runs the same build on every push
([`.github/workflows/build.yml`](.github/workflows/build.yml)).

## Flashing & recovery

Flash from a running OpenWrt or a RAM-booted initramfs (LAN `192.168.1.1`, passwordless
dropbear):

```sh
IMG=openwrt-mediatek-filogic-vistotek_c6130g-squashfs-sysupgrade.bin
scp -O "$IMG" root@192.168.1.1:/tmp/
ssh root@192.168.1.1 sysupgrade -n /tmp/"$IMG"
```

RAM-boot recovery (no flash writes) from U-Boot (`ipaddr 192.168.2.1`,
`serverip 192.168.2.88`): `tftpboot 0x46000000 recovery.itb; bootm 0x46000000`.

Worst case, TFTP the stock `ubi.bin` back to the `ubi` partition (`mtkupgrade ubi`), or
reflash the NOR from `dump.bin` with a SOIC8 clip — the stock BL2/U-Boot on NOR is never
touched, and the dual UBI is a fallback slot. Backups (`dump.bin`, `ubi.bin`, `ubi2.bin`,
extracted `rootfs/`) and `wtinfo_decrypt.py` (the wtinfo/MAC decryptor, key `wtinfo-des-v1`)
are kept locally — gitignored, too large for the repo.

## Branches

- **`main`** — the full working image, including the `modem-led` connection-state daemon above.
- **`upstream`** — the mainline-submission form: the daemon is dropped (4G/5G LEDs defined-only)
  and the guessed MT7531 switch IRQ removed after cross-checking the stock DTB (reset polarity
  confirmed, vendor declares no switch interrupt).

## Known issues

- **Dial test** — blocked on a SIM (`+CME ERROR: 10`).
- **modem-power warm-reboot race** — the RM520N restarts itself on SoC warm reboots and the
  boot pulse can toggle a mid-restart module back off; a cold power cycle recovers it.

See [openwrt-port/RESUME-FLASH-INSTALL.md](openwrt-port/RESUME-FLASH-INSTALL.md) for the
NAND-boot debugging and the full bench / serial / TFTP setup.
