import re
import sys

mk = sys.argv[1]
s = open(mk).read()

# Stock-U-Boot / ubiblock scheme (like cmcc_a10-stock): the 'kernel' UBI volume
# holds a standalone FIT (kernel+dtb only), the rootfs is its own squashfs
# 'rootfs' volume, mounted via the generic rootfs auto-ubiblock patches.
# sysupgrade-tar + nand_do_upgrade (default platform.sh case) writes both volumes.
block = """define Device/vistotek_c6130g
  DEVICE_VENDOR := Vistotek
  DEVICE_MODEL := C6130G-5G
  DEVICE_DTS := mt7981b-vistotek-c6130g
  DEVICE_DTS_DIR := ../dts
  DEVICE_PACKAGES := kmod-mt7915e kmod-mt7981-firmware mt7981-wo-firmware \\
    kmod-usb3 kmod-usb-net-cdc-ether kmod-usb-net-qmi-wwan \\
    kmod-usb-serial-option uqmi luci luci-proto-qmi
  UBINIZE_OPTS := -E 5
  BLOCKSIZE := 128k
  PAGESIZE := 2048
  KERNEL_IN_UBI := 1
  KERNEL := kernel-bin | gzip | \\
\tfit gzip $$(KDIR)/image-$$(firstword $$(DEVICE_DTS)).dtb
  KERNEL_INITRAMFS := kernel-bin | lzma | \\
\tfit lzma $$(KDIR)/image-$$(firstword $$(DEVICE_DTS)).dtb with-initrd | pad-to 64k
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
endef
TARGET_DEVICES += vistotek_c6130g

"""

existing = re.compile(
    r"define Device/vistotek_c6130g\n.*?endef\nTARGET_DEVICES \+= vistotek_c6130g\n\n",
    re.S,
)
if existing.search(s):
    new = existing.sub(lambda m: block, s, count=1)
    if new == s:
        print("device block already up to date")
    else:
        open(mk, "w").write(new)
        print("device block replaced")
else:
    anchor = "define Device/gatonetworks_gdsp"
    s = s.replace(anchor, block + anchor, 1)
    open(mk, "w").write(s)
    print("device block injected")
