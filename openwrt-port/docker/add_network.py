import sys

f = sys.argv[1]
s = open(f).read()

# lan1/lan4 don't exist on this board (2x LAN + 1x WAN switch ports); without
# this case the filogic default advertises lan1-lan4 and LuCI's port status
# widget crashes on the phantom netdevs.
block = (
    "\tvistotek,c6130g)\n"
    '\t\tucidef_set_interfaces_lan_wan "lan2 lan3" "wan"\n'
    "\t\t;;\n"
)

if "vistotek,c6130g)" in s:
    print("network case already present")
    sys.exit(0)

anchor = "case $board in\n"
if anchor not in s:
    print("ERROR: anchor not found")
    sys.exit(1)
s = s.replace(anchor, anchor + block, 1)
open(f, "w").write(s)
print("injected network case")
