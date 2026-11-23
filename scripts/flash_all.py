#!/usr/bin/env python3
"""
flash_all.py - Complete End-to-End OpenWrt Flashing Pipeline
Sercomm JioFiber JCOW414 (EcoNet EN7528 platform)

Runs the complete automated flashing workflow:
  1. Trigger JFxploit F-01 Pre-Auth exploit for root Telnet access
  2. Backup all critical NAND partitions, calibration data, and config
  3. Stream OpenWrt squashfs-tclinux.trx into router RAM (/tmp/fw.trx)
  4. Flash Bank 1 (tclinux), swap dual-boot flag, and reboot into OpenWrt
"""

import sys
import os
import argparse

# Add scripts directory to path if executed directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exploit_root import exploit
from backup_partitions import perform_backup
from upload_firmware import upload_firmware
from flash_and_swap import flash_and_swap

def main():
    parser = argparse.ArgumentParser(description="End-to-End OpenWrt Installer for Sercomm JCOW414")
    parser.add_argument("--firmware", default="openwrt-jcow414-squashfs-tclinux.trx", help="Path to OpenWrt tclinux.trx firmware")
    parser.add_argument("--target", default="192.168.29.1", help="Stock router IP (default: 192.168.29.1)")
    parser.add_argument("--password", default="password", help="Temporary root password for Telnet (default: password)")
    parser.add_argument("--backup-dir", default="backup", help="Directory to save raw NAND backup (default: backup)")
    parser.add_argument("--yes", "-y", action="store_true", help="Non-interactive mode (auto-confirm flash)")
    args = parser.parse_args()

    if not os.path.isfile(args.firmware):
        print(f"[ERROR] Firmware image not found at: {args.firmware}")
        print("Please download openwrt-jcow414-squashfs-tclinux.trx from:")
        print("https://github.com/UdayKhare09/jcow414-openwrt/releases/tag/v1.0.0")
        sys.exit(1)

    print("\n" + "#" * 68)
    print("#  Sercomm JioFiber JCOW414 OpenWrt Flashing Pipeline")
    print("#" * 68 + "\n")

    # Step 1: Exploit
    print("[PHASE 1/4] Gaining Root Shell via JFxploit F-01...")
    if not exploit(target_ip=args.target, root_pass=args.password):
        print("[!] Phase 1 failed. Aborting.")
        sys.exit(1)

    # Step 2: Backup
    print("\n[PHASE 2/4] Backing up NAND partitions and calibration data...")
    if not perform_backup(target_ip=args.target, root_pass=args.password, output_dir=args.backup_dir):
        print("[!] Phase 2 failed. Aborting for safety.")
        sys.exit(1)

    # Step 3: Upload
    print("\n[PHASE 3/4] Uploading OpenWrt firmware to router RAM...")
    if not upload_firmware(firmware_path=args.firmware, target_ip=args.target, root_pass=args.password):
        print("[!] Phase 3 failed. Aborting.")
        sys.exit(1)

    # Step 4: Flash & Swap
    print("\n[PHASE 4/4] Flashing Bank 1 and swapping dual-boot flag...")
    if not flash_and_swap(target_ip=args.target, root_pass=args.password, auto_confirm=args.yes):
        print("[!] Phase 4 failed.")
        sys.exit(1)

    print("\n[COMPLETE] All steps completed successfully!")

if __name__ == "__main__":
    main()
