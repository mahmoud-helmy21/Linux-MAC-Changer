import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys

NET_DIR = "/sys/class/net"
STATE_FILE = os.path.join(os.path.expanduser("~"), ".mac_changer_state.json")
MAC_PATTERN = re.compile(r"^[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}$")


def fail(message):
    print("[-] " + message)
    sys.exit(1)


def ok(message):
    print("[+] " + message)


def info(message):
    print("[*] " + message)


def list_interfaces():
    try:
        return sorted(os.listdir(NET_DIR))
    except OSError:
        return []


def read_sysfs(interface, filename):
    try:
        with open(os.path.join(NET_DIR, interface, filename)) as handle:
            return handle.read().strip()
    except OSError:
        return None


def get_current_mac(interface):
    mac = read_sysfs(interface, "address")
    if mac and MAC_PATTERN.match(mac):
        return mac.lower()
    return None


def get_operstate(interface):
    return read_sysfs(interface, "operstate")


def load_state():
    try:
        with open(STATE_FILE) as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w") as handle:
        json.dump(state, handle, indent=2)


def remember_original(interface):
    state = load_state()
    if interface in state:
        return state[interface]
    mac = get_current_mac(interface)
    if mac:
        state[interface] = mac
        save_state(state)
    return mac


def forget_original(interface):
    state = load_state()
    state.pop(interface, None)
    save_state(state)


def resolve_interface(value, interfaces=None):
    interfaces = list_interfaces() if interfaces is None else interfaces
    if value in interfaces:
        return value
    if value.isdigit():
        index = int(value)
        if 0 <= index < len(interfaces):
            return interfaces[index]
    return None


def generate_random_mac():
    octets = [random.getrandbits(8) for _ in range(6)]
    octets[0] = (octets[0] & 0xFC) | 0x02
    return ":".join("{:02x}".format(octet) for octet in octets)


def normalize_mac(value):
    mac = value.strip().lower()
    if not MAC_PATTERN.match(mac):
        fail("Invalid MAC address '{}' (expected format aa:bb:cc:dd:ee:ff)".format(value))
    return mac


def require_root():
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        fail("Root privileges required. Run with sudo.")


BACKEND = None


def resolve_backend():
    global BACKEND
    if BACKEND is not None:
        return BACKEND
    if shutil.which("ip"):
        BACKEND = "ip"
    elif shutil.which("ifconfig"):
        BACKEND = "ifconfig"
    else:
        fail("Neither 'ip' (iproute2) nor 'ifconfig' (net-tools) found.")
    return BACKEND


def run_command(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True)
    if result.returncode != 0:
        fail("{} failed: {}".format(" ".join(arguments), result.stderr.strip()))


def bring_down(interface):
    info("Taking {} down".format(interface))
    if resolve_backend() == "ip":
        run_command(["ip", "link", "set", "dev", interface, "down"])
    else:
        run_command(["ifconfig", interface, "down"])


def bring_up(interface):
    info("Bringing {} up".format(interface))
    if resolve_backend() == "ip":
        run_command(["ip", "link", "set", "dev", interface, "up"])
    else:
        run_command(["ifconfig", interface, "up"])


def apply_mac(interface, new_mac):
    if resolve_backend() == "ip":
        run_command(["ip", "link", "set", "dev", interface, "address", new_mac])
    else:
        run_command(["ifconfig", interface, "hw", "ether", new_mac])


def snapshot_network(interface):
    if shutil.which("ip") is None:
        return None

    def output(arguments):
        result = subprocess.run(["ip"] + arguments, capture_output=True, text=True)
        return result.stdout

    ipv4_addrs = re.findall(r"inet\s+([0-9.]+/\d+)\s", output(["-o", "-4", "addr", "show", "dev", interface]))
    ipv6_addrs = [
        "{}/{}".format(address, prefix)
        for address, prefix, _scope in re.findall(
            r"inet6\s+([0-9a-fA-F:]+)/(\d+)\s+scope\s+(\S+)",
            output(["-o", "-6", "addr", "show", "dev", interface]),
        )
    ]
    v4_routes = [line.strip() for line in output(["-o", "route", "show", "dev", interface]).splitlines() if line.strip()]
    v6_routes = [line.strip() for line in output(["-o", "-6", "route", "show", "dev", interface]).splitlines() if line.strip()]
    return {
        "ipv4_addrs": ipv4_addrs,
        "ipv6_addrs": ipv6_addrs,
        "v4_routes": v4_routes,
        "v6_routes": v6_routes,
    }


def restore_network(interface, snapshot):
    total = sum(len(entries) for entries in snapshot.values())
    if total == 0:
        return
    info("Restoring {} saved entr(y/ies): addresses + routes".format(total))

    restored = 0
    def try_restore(arguments):
        nonlocal restored
        result = subprocess.run(arguments, capture_output=True, text=True)
        stderr = result.stderr.strip()
        succeeded = result.returncode == 0 or "File exists" in stderr or "already assigned" in stderr
        restored += succeeded
        if not succeeded:
            print("[!] Skipped '{}': {}".format(" ".join(arguments[1:]), stderr))

    for cidr in snapshot["ipv4_addrs"]:
        try_restore(["ip", "-4", "addr", "add", cidr, "dev", interface])

    for cidr in snapshot["ipv6_addrs"]:
        try_restore(["ip", "-6", "addr", "add", cidr, "dev", interface])

    for route_prefix, routes in (
        (["route"], snapshot["v4_routes"]),
        (["-6", "route"], snapshot["v6_routes"]),
    ):
        for route in routes:
            arguments = route.split()
            if "dev" not in arguments:
                arguments += ["dev", interface]
            try_restore(["ip"] + route_prefix + ["add"] + arguments)

    if restored == total:
        ok("Network configuration fully preserved ({}/{})".format(restored, total))
    else:
        print("[!] Restored {}/{} entries. Check 'ip addr' and 'ip route'".format(restored, total))


def apply_change(interface, new_mac):
    snapshot = snapshot_network(interface)
    if snapshot is None:
        print("[!] 'ip' command not found. Addresses/routes may be lost during the change.")
    try:
        bring_down(interface)
        apply_mac(interface, new_mac)
        bring_up(interface)
    finally:
        if snapshot:
            restore_network(interface, snapshot)


def set_mac(interface, new_mac):
    original = remember_original(interface)
    if original is None:
        fail("Could not read the current MAC of {}".format(interface))

    print()
    info("Original MAC : {}".format(original))
    info("Target  MAC  : {}".format(new_mac))
    apply_change(interface, new_mac)

    current = get_current_mac(interface)
    if current == new_mac:
        ok("MAC changed successfully. {} now uses {}".format(interface, current))
        ok("Original MAC saved. Restore anytime with -r")
    else:
        fail("Something went wrong. Current MAC: {}".format(current))


def restore_mac(interface):
    original = load_state().get(interface)
    if not original:
        fail("No saved original MAC for {}. Change it first with -m or -d".format(interface))

    print()
    info("Saved original MAC: {}".format(original))
    apply_change(interface, original)

    current = get_current_mac(interface)
    if current == original:
        forget_original(interface)
        ok("Original MAC restored. {} is back to {}".format(interface, current))
    else:
        fail("Something went wrong. Current MAC: {}".format(current))


def print_interfaces(interfaces=None):
    interfaces = list_interfaces() if interfaces is None else interfaces
    if not interfaces:
        fail("No network interfaces found")

    print()
    print("{:<4}{:<14}{:<22}{}".format("ID", "INTERFACE", "MAC", "STATE"))
    print("-" * 52)
    for index, interface in enumerate(interfaces):
        mac = get_current_mac(interface) or "unknown"
        state = (get_operstate(interface) or "unknown").upper()
        print("{:<4}{:<14}{:<22}{}".format(index, interface, mac, state))
    print()


def select_interface(interfaces=None):
    interfaces = list_interfaces() if interfaces is None else interfaces
    if not interfaces:
        fail("No network interfaces found")

    print_interfaces(interfaces)
    choice = input("[?] Select an interface (ID or name): ").strip()
    interface = resolve_interface(choice, interfaces)
    if interface is None:
        fail("'{}' is not a valid interface ID or name".format(choice))
    return interface


def select_action():
    print("Actions:")
    print("  1) Set a specific MAC      (-m)")
    print("  2) Generate a random MAC   (-d)")
    print("  3) Restore original MAC    (-r)")
    print()
    choice = input("[?] Select an action: ").strip()
    if choice == "1":
        return ("set", normalize_mac(input("[?] Enter new MAC: ")))
    if choice == "2":
        return ("random", None)
    if choice == "3":
        return ("restore", None)
    fail("'{}' is not a valid action".format(choice))


def execute(interface, action):
    kind, value = action
    resolve_backend()
    require_root()

    if kind == "restore":
        restore_mac(interface)
    elif kind == "random":
        set_mac(interface, generate_random_mac())
    else:
        set_mac(interface, value)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mac_changer",
        description="Network interface MAC address changer",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "examples:\n"
            "  %(prog)s --list                  list interfaces with IDs\n"
            "  %(prog)s                         interactive mode\n"
            "  %(prog)s -i 0 -m aa:bb:cc:dd:ee:ff   set MAC on interface ID 0\n"
            "  %(prog)s -i eth0 -d              random MAC on eth0\n"
            "  %(prog)s -i 0 -r                 restore original MAC\n"
        ),
    )
    parser.add_argument(
        "-i", "--interface",
        help="target interface, by name (eth0) or ID from --list (0, 1, 2)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-m", "--mac", help="specific MAC address to assign")
    group.add_argument("-d", "--random", action="store_true", help="generate a random MAC address")
    group.add_argument("-r", "--restore", action="store_true", help="restore the saved original MAC")
    parser.add_argument("--list", action="store_true", help="list available interfaces and exit")
    return parser


def main():
    args = build_parser().parse_args()

    if args.list:
        print_interfaces()
        return

    if args.interface:
        interface = resolve_interface(args.interface)
        if interface is None:
            fail("'{}' is not a valid interface ID or name. Use --list to see options.".format(args.interface))

        if args.mac:
            action = ("set", normalize_mac(args.mac))
        elif args.random:
            action = ("random", None)
        elif args.restore:
            action = ("restore", None)
        else:
            fail("No action specified. Use -m <mac>, -d for random, or -r to restore.")
    else:
        interface = select_interface()
        action = select_action()

    execute(interface, action)


if __name__ == "__main__":
    main()
