# 🛡️ Advanced Linux MAC Address Changer

A feature-rich Python tool for Linux that allows you to change network interface MAC addresses, generate random MAC addresses, and restore the original MAC address when needed.

The tool also attempts to preserve the current network configuration by taking a snapshot of IPv4/IPv6 addresses and routes before changing the MAC address and restoring them afterward.

---

## ✨ Features

* 🔀 **Custom MAC Address:** Assign a specific MAC address to a network interface.
* 🎲 **Random MAC Generation:** Generate a random locally administered MAC address.
* 💾 **Original MAC Backup:** Automatically saves the original MAC address for later restoration.
* 🔄 **Easy Restoration:** Restore the saved original MAC address using the `-r` option.
* 🌐 **Network State Preservation:** Captures IPv4/IPv6 addresses and routes and attempts to restore them after the MAC address is changed.
* 🖥️ **Interactive Mode:** Use a simple menu to select the network interface and desired action.
* ⚡ **Command-Line Support:** Perform operations directly using command-line arguments.
* 🔧 **Interface Selection:** Select an interface using either its name or its ID.
* ⚙️ **Backend Compatibility:** Uses `iproute2` (`ip`) when available and falls back to `ifconfig`.

---

## 📋 Requirements

* **Operating System:** Linux
* **Python:** Python 3.x
* **Privileges:** Root / Sudo access
* **Networking Tools:** `iproute2` (`ip`) or `net-tools` (`ifconfig`)

---

# 🚀 Usage Guide

## 1. Interactive Mode

Run the tool without arguments to launch the interactive menu:

```bash
sudo python3 mac_changer.py
```

You will be able to:

1. Select a network interface.
2. Choose an action.
3. Set a custom MAC address.
4. Generate a random MAC address.
5. Restore the original MAC address.

---

## 2. Command-Line Arguments Mode

### List Available Network Interfaces

```bash
python3 mac_changer.py --list
```

The tool displays available interfaces along with their IDs, MAC addresses, and current states.

---

### Set a Specific MAC Address

Using the interface name:

```bash
sudo python3 mac_changer.py -i eth0 -m 00:11:22:33:44:55
```

Using the interface ID:

```bash
sudo python3 mac_changer.py -i 0 -m 00:11:22:33:44:55
```

---

### Generate a Random MAC Address

```bash
sudo python3 mac_changer.py -i eth0 -d
```

Or using an interface ID:

```bash
sudo python3 mac_changer.py -i 0 -d
```

---

### Restore the Original MAC Address

```bash
sudo python3 mac_changer.py -i eth0 -r
```

Or using an interface ID:

```bash
sudo python3 mac_changer.py -i 0 -r
```

---

## 🧠 How It Works

Before changing a MAC address, the tool:

1. Saves the original MAC address.
2. Takes a snapshot of the network configuration when the `ip` command is available.
3. Brings the selected interface down.
4. Applies the new MAC address.
5. Brings the interface back up.
6. Attempts to restore saved IP addresses and routes.

The original MAC address is stored locally and can later be restored using the `-r` option.

---

## 🛠️ Built With

* **Python 3**
* **argparse**
* **subprocess**
* **Linux sysfs**
* **iproute2**
* **net-tools**

---

## ⚠️ Disclaimer

This tool is intended for educational purposes, authorized security testing, and legitimate network administration.

Always ensure that you have permission before modifying network interfaces or MAC addresses.
