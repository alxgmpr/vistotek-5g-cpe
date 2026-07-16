#!/bin/bash
# Incremental rebuild after the serial0-alias DTS fix. Run as builder inside owrt-inc.
set -e
export FORCE_UNSAFE_CONFIGURE=1
cd /build/openwrt
LOG=/staging/rebuild.log
exec > >(tee "$LOG") 2>&1
set -x
echo "[alias present in tree DTS?]"
grep -A1 'aliases {' target/linux/mediatek/dts/mt7981b-vistotek-c6130g.dts | head
echo "[clean kernel build to force DTB regen]"
make target/linux/clean
echo "[rebuild — toolchain cached, so this is kernel+dtb+image only]"
set +e
make -j"$(nproc)"
RC=$?
set -e
echo "[BUILD EXIT $RC]"
ls -l bin/targets/mediatek/filogic/*vistotek* 2>/dev/null || echo "(no artifacts)"
mkdir -p /staging/artifacts
cp -v bin/targets/mediatek/filogic/*vistotek* /staging/artifacts/ 2>/dev/null || echo "no copy"
echo "[END rc=$RC]"
