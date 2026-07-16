#!/bin/bash
set -e
if [ "$(id -u)" = "0" ]; then
  export DEBIAN_FRONTEND=noninteractive
  if ! command -v git >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq build-essential clang flex bison g++ gawk libelf-dev \
      gettext git libncurses-dev libssl-dev python3 python3-setuptools \
      rsync swig unzip zlib1g-dev file wget qemu-user-static time sudo ca-certificates \
      >/tmp/apt.log 2>&1 || { echo "APT FAILED"; tail -20 /tmp/apt.log; exit 1; }
  fi
  id builder >/dev/null 2>&1 || useradd -m -s /bin/bash builder
  [ -d /build ] || { mkdir -p /build; chown builder:builder /build; }
  # ensure builder can overwrite a possibly root-owned DTS from an earlier docker cp
  [ -d /build/openwrt ] && chown -R builder:builder /build/openwrt/target/linux/mediatek/dts 2>/dev/null || true
  chmod 0777 /staging 2>/dev/null || true
  exec sudo -u builder -H bash "$0"
fi
# ---------------- builder (non-root) ----------------
export FORCE_UNSAFE_CONFIGURE=1
LOG=/staging/build.log
exec > >(tee "$LOG") 2>&1
set -x

if [ -d /build/openwrt/.git ]; then
  echo "=== INCREMENTAL rebuild (existing tree, toolchain cached) ==="
  cd /build/openwrt
  cp /staging/mt7981b-vistotek-c6130g.dts target/linux/mediatek/dts/
  grep -A1 'aliases {' target/linux/mediatek/dts/mt7981b-vistotek-c6130g.dts | head
  python3 /staging/docker/inject_device.py target/linux/mediatek/image/filogic.mk
  grep -A20 'define Device/vistotek_c6130g' target/linux/mediatek/image/filogic.mk
  python3 /staging/docker/add_leds.py target/linux/mediatek/filogic/base-files/etc/board.d/01_leds
  python3 /staging/docker/add_network.py target/linux/mediatek/filogic/base-files/etc/board.d/02_network
  if [ -d /staging/files ]; then
    cp -rv /staging/files/. target/linux/mediatek/filogic/base-files/
    chmod +x target/linux/mediatek/filogic/base-files/etc/init.d/* \
             target/linux/mediatek/filogic/base-files/usr/sbin/modem-led 2>/dev/null || true
  fi
  # regenerate .config from the seed every time: a re-run of defconfig alone
  # keeps stale "# CONFIG_PACKAGE_x is not set" pins and silently drops
  # packages newly added to DEVICE_PACKAGES
  printf 'CONFIG_TARGET_mediatek=y\nCONFIG_TARGET_mediatek_filogic=y\nCONFIG_TARGET_mediatek_filogic_DEVICE_vistotek_c6130g=y\n' > .config
  make defconfig >/tmp/defconfig.log 2>&1
  make target/linux/clean
  make package/base-files/clean
  set +e; make -j"$(nproc)"; RC=$?; set -e
else
  echo "=== FULL build ==="
  cd /build
  git clone --depth 1 https://github.com/openwrt/openwrt.git
  cd /build/openwrt
  cp /staging/mt7981b-vistotek-c6130g.dts target/linux/mediatek/dts/
  python3 /staging/docker/inject_device.py target/linux/mediatek/image/filogic.mk
  python3 /staging/docker/add_leds.py target/linux/mediatek/filogic/base-files/etc/board.d/01_leds
  python3 /staging/docker/add_network.py target/linux/mediatek/filogic/base-files/etc/board.d/02_network
  if [ -d /staging/files ]; then
    cp -rv /staging/files/. target/linux/mediatek/filogic/base-files/
    chmod +x target/linux/mediatek/filogic/base-files/etc/init.d/* \
             target/linux/mediatek/filogic/base-files/usr/sbin/modem-led 2>/dev/null || true
  fi
  ./scripts/feeds update -a  >/tmp/feeds.log  2>&1
  ./scripts/feeds install -a >/tmp/feeds2.log 2>&1
  printf 'CONFIG_TARGET_mediatek=y\nCONFIG_TARGET_mediatek_filogic=y\nCONFIG_TARGET_mediatek_filogic_DEVICE_vistotek_c6130g=y\n' > .config
  make defconfig >/tmp/defconfig.log 2>&1
  set +e; make -j"$(nproc)"; RC=$?; set -e
fi

echo "[BUILD EXIT $RC]"
ls -l bin/targets/mediatek/filogic/*vistotek* 2>/dev/null || echo "(no artifacts)"
mkdir -p /staging/artifacts
cp -v bin/targets/mediatek/filogic/*vistotek* /staging/artifacts/ 2>/dev/null || echo "no copy"
echo "[END rc=$RC]"
# propagate the real build result so CI (and `docker start`) can detect failure
exit "$RC"
