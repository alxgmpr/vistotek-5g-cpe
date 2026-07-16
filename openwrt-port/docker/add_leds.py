import re
import sys

f = sys.argv[1]
s = open(f).read()

# Desired vistotek LED block. Kept as the single source of truth: the script
# REPLACES any existing vistotek block so edits here always land on incremental
# rebuilds (the openwrt tree persists in the build container, so the old block
# is already present and a plain "skip if present" would drop new lines).
block = (
    "vistotek,c6130g)\n"
    "\tucidef_set_led_netdev \"lan2\" \"LAN2\" \"yellow:lan2\" \"lan2\" \"link tx rx\"\n"
    "\tucidef_set_led_netdev \"lan3\" \"LAN3\" \"yellow:lan3\" \"lan3\" \"link tx rx\"\n"
    "\tucidef_set_led_netdev \"wan\" \"WAN\" \"yellow:wan\" \"wan\" \"link tx rx\"\n"
    "\tucidef_set_led_netdev \"wlan2g\" \"WLAN2G\" \"blue:wifi\" \"phy0-ap0\" \"link tx rx\"\n"
    "\tucidef_set_led_heartbeat \"status\" \"STATUS\" \"blue:status\"\n"
    # Modem indicator LEDs: named + default-off on the "none" trigger so they show
    # in LuCI and are driven by the modem-led daemon (which only touches LEDs left
    # on "none"). Set any other trigger in LuCI to override (e.g. default-on).
    "\tucidef_set_led_default \"5g_blue\" \"5G-BLUE\" \"blue:5g\" \"0\"\n"
    "\tucidef_set_led_default \"5g_yellow\" \"5G-YELLOW\" \"yellow:5g\" \"0\"\n"
    "\tucidef_set_led_default \"4g_blue\" \"4G-BLUE\" \"blue:4g\" \"0\"\n"
    "\tucidef_set_led_default \"4g_yellow\" \"4G-YELLOW\" \"yellow:4g\" \"0\"\n"
    "\t;;\n"
)

# Match an existing "vistotek,c6130g)" case up to its first ";;" terminator.
existing = re.compile(r"vistotek,c6130g\)\n(?:.*\n)*?\t;;\n")
if existing.search(s):
    new = existing.sub(block, s, count=1)
    if new == s:
        print("leds unchanged")
    else:
        open(f, "w").write(new)
        print("updated leds block")
    sys.exit(0)

anchor = "case $board in\n"
if anchor not in s:
    print("ERROR: anchor not found")
    sys.exit(1)
s = s.replace(anchor, anchor + block, 1)
open(f, "w").write(s)
print("injected leds")
