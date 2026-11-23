#!/usr/bin/env python3
"""
flash_and_swap.py - Flash OpenWrt to Bank 1 and Swap Bootflag
Sercomm JioFiber JCOW414 (EcoNet EN7528 platform)

Dual-Bank Architecture:
  The Sercomm JCOW414 uses a dual-bank NAND flash design:
    - Bank 1: 'tclinux'       (mtd4: kernel + rootfs squashfs) -> Bootflag 0
    - Bank 2: 'tclinux_slave' (mtd7: kernel + rootfs squashfs) -> Bootflag 1

By writing OpenWrt strictly to 'tclinux' (Bank 1) and leaving 'tclinux_slave' (Bank 2)
intact, the stock Jio firmware remains completely preserved as a fail-safe recovery bank.

The bootflag stored in the 'reservearea' partition (mtd13) controls which bank the
bootloader boots:
  sys bootflag swap -> Toggles between 0 and 1.
"""

import socket
import time
import sys
import argparse
from router_utils import get_telnet_socket

def flash_and_swap(target_ip="192.168.29.1", root_pass="password", expected_md5=None, auto_confirm=False):
    print("=" * 65)
    print("    Sercomm JCOW414 OpenWrt Flasher & Dual-Boot Manager")
    print("=" * 65)

    print("[*] Connecting to router Telnet...")
    try:
        s = get_telnet_socket(host=target_ip, password=root_pass, timeout=8.0)
    except Exception as e:
        print(f"[ERROR] Could not connect to Telnet at {target_ip}: {e}")
        return False

    # 1. Verify firmware exists in /tmp/fw.trx
    print("\n[*] Step 1: Checking firmware in router RAM (/tmp/fw.trx)...")
    s.sendall(b"md5sum /tmp/fw.trx\r\n")
    time.sleep(2.0)
    out = s.recv(4096).decode(errors='ignore')
    
    router_md5 = ""
    for line in out.splitlines():
        if "fw.trx" in line and not line.strip().startswith("md5sum"):
            router_md5 = line.split()[0].strip()
            break

    if not router_md5:
        print("[ERROR] /tmp/fw.trx not found or empty! Run upload_firmware.py first.")
        s.close()
        return False

    print(f"[+] Found /tmp/fw.trx with MD5: {router_md5}")

    if expected_md5 and expected_md5.lower() != router_md5.lower():
        print(f"[ERROR] MD5 mismatch! Expected: {expected_md5}, Found: {router_md5}")
        s.close()
        return False

    # 2. Safety confirmation
    print("\n" + "!" * 65)
    print("  WARNING: FLASHING FIRMWARE TO NAND BANK 1 ('tclinux')")
    print("  DO NOT DISCONNECT POWER OR ETHERNET CABLE DURING FLASHING!")
    print("!" * 65 + "\n")

    if not auto_confirm:
        confirm = input("Type 'YES' to proceed with flashing: ")
        if confirm.strip() != "YES":
            print("[*] Flashing cancelled by user.")
            s.close()
            return False

    # 3. Flashing Bank 1 (tclinux)
    print("\n[*] Step 2: Flashing /tmp/fw.trx to Bank 1 (tclinux)...")
    s.sendall(b"mtd -f write /tmp/fw.trx tclinux\r\n")

    start_time = time.time()
    flash_output = ""
    s.settimeout(2.0)

    # Monitor output for up to 3 minutes
    while time.time() - start_time < 180:
        try:
            chunk = s.recv(1024).decode(errors='ignore')
            if chunk:
                flash_output += chunk
                sys.stdout.write(chunk)
                sys.stdout.flush()
                if "RIL>" in flash_output[-30:]:
                    break
        except socket.timeout:
            pass

    elapsed = time.time() - start_time
    print(f"\n[+] Flashing command completed in {elapsed:.1f} seconds.")

    # 4. Swap bootflag
    print("\n[*] Step 3: Swapping dual-boot flag to Bank 1...")
    s.sendall(b"/usr/bin/sys bootflag swap\r\n")
    time.sleep(2.0)
    swap_out = s.recv(4096).decode(errors='ignore')
    print(swap_out.strip())

    # 5. Verify bootflag
    print("\n[*] Step 4: Verifying new active bootflag...")
    s.sendall(b"/usr/bin/sys bootflag read\r\n")
    time.sleep(2.0)
    read_out = s.recv(4096).decode(errors='ignore')
    print(read_out.strip())

    if "boot_flag = 0" in read_out:
        print("\n[SUCCESS] Active bootflag confirmed as 0 (Bank 1: OpenWrt)!")
    else:
        print("\n[WARNING] Unexpected bootflag output. Please verify manually before rebooting.")

    # 6. Reboot into OpenWrt
    print("\n[*] Step 5: Syncing filesystems and rebooting into OpenWrt...")
    s.sendall(b"sync; sleep 1; reboot\r\n")
    time.sleep(2.0)
    s.close()

    print("\n" + "=" * 65)
    print("  [SUCCESS] Router is rebooting into OpenWrt!")
    print("=" * 65)
    print("\nNext steps:")
    print("  1. Wait ~60 seconds for the router to complete booting.")
    print("  2. Open your web browser and navigate to: http://192.168.1.1")
    print("  3. Or connect via SSH: ssh root@192.168.1.1 (no password initially)")
    print("  4. Set your root password and configure your network.")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flash OpenWrt to JCOW414 and Swap Bootflag")
    parser.add_argument("--target", default="192.168.29.1", help="Router IP address (default: 192.168.29.1)")
    parser.add_argument("--password", default="password", help="Router root password (default: password)")
    parser.add_argument("--md5", default=None, help="Optional expected MD5 checksum to verify")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    success = flash_and_swap(target_ip=args.target, root_pass=args.password, expected_md5=args.md5, auto_confirm=args.yes)
    sys.exit(0 if success else 1)
