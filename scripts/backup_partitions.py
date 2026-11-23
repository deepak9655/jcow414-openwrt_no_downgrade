#!/usr/bin/env python3
"""
backup_partitions.py - Full NAND Partition & Calibration Backup
Sercomm JioFiber JCOW414 (EcoNet EN7528 platform)

This script creates a complete backup of critical router partitions:
  - mtd0  (bootloader, 256KB)
  - mtd1  (romfile - contains factory calibration, MAC address, serial, 256KB)
  - mtd11 (config, 2MB)
  - mtd13 (reservearea - contains dual-image bootflag, 2.25MB)
  - /flash (active configuration database tree)
  - Factory credentials in /tmp/factory*

The backup archive is compressed on the router, checksummed, streamed to your PC
over a dedicated temporary TCP socket, and verified locally.
"""

import socket
import time
import os
import hashlib
import argparse
import sys
from router_utils import exec_commands

def perform_backup(target_ip="192.168.29.1", root_pass="password", output_dir="backup", stream_port=9998):
    os.makedirs(output_dir, exist_ok=True)
    local_archive = os.path.join(output_dir, "router_backup.tar.gz")

    print("=" * 65)
    print(f"[*] Sercomm JCOW414 NAND & Calibration Backup")
    print(f"[*] Router IP:     {target_ip}")
    print(f"[*] Output Dir:    {os.path.abspath(output_dir)}")
    print(f"[*] Stream Port:   {stream_port}")
    print("=" * 65)

    # 1. Dump partitions on router
    dump_cmds = [
        "mkdir -p /tmp/backup",
        "dd if=/dev/mtdblock0 of=/tmp/backup/mtd0_bootloader.bin bs=64k 2>/dev/null",
        "dd if=/dev/mtdblock1 of=/tmp/backup/mtd1_romfile.bin bs=64k 2>/dev/null",
        "dd if=/dev/mtdblock11 of=/tmp/backup/mtd11_config.bin bs=64k 2>/dev/null",
        "dd if=/dev/mtdblock13 of=/tmp/backup/mtd13_reservearea.bin bs=64k 2>/dev/null",
        "cp -r /flash /tmp/backup/flash_backup 2>/dev/null",
        "cp /tmp/factory* /tmp/backup/ 2>/dev/null",
        "cd /tmp && tar -czf /tmp/router_backup.tar.gz backup",
        "ls -la /tmp/router_backup.tar.gz",
        "md5sum /tmp/router_backup.tar.gz"
    ]

    print("\n[*] Step 1: Dumping raw partitions and configuration on router...")
    res = exec_commands(dump_cmds, host=target_ip, password=root_pass, wait_between=1.2)
    
    router_md5 = ""
    for line in res.get("md5sum /tmp/router_backup.tar.gz", "").splitlines():
        if "router_backup.tar.gz" in line and not line.strip().startswith("md5sum"):
            router_md5 = line.split()[0].strip()
            break

    if not router_md5:
        print("[ERROR] Failed to obtain router backup checksum. Response:")
        print(res.get("md5sum /tmp/router_backup.tar.gz", ""))
        return False

    print(f"[+] Router archive created. MD5: {router_md5}")

    # 2. Setup ephemeral streaming service on router via inetd
    print(f"\n[*] Step 2: Configuring ephemeral download stream on port {stream_port}...")
    stream_cmds = [
        f"printf '#!/bin/sh\\ncat /tmp/router_backup.tar.gz\\n' > /tmp/send_backup.sh",
        "chmod +x /tmp/send_backup.sh",
        f"echo '{stream_port} stream tcp nowait root /tmp/send_backup.sh send_backup.sh' >> /tmp/backup_inetd.conf",
        f"/pfrm2.0/bin/iptables -I fwInBypass -p tcp --dport {stream_port} -m ifgroup --ifgroup-in 0x1/0x1 -j ACCEPT",
        "killall inetd 2>/dev/null; busybox inetd /tmp/backup_inetd.conf"
    ]
    exec_commands(stream_cmds, host=target_ip, password=root_pass, wait_between=0.6)
    time.sleep(1.0)

    # 3. Stream backup to PC
    print(f"[*] Step 3: Downloading archive to {local_archive}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(15.0)
    s.connect((target_ip, stream_port))

    total_bytes = 0
    with open(local_archive, "wb") as f:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            f.write(chunk)
            total_bytes += len(chunk)
    s.close()

    print(f"[+] Download complete: {total_bytes:,} bytes received.")

    # 4. Verify local MD5
    with open(local_archive, "rb") as f:
        local_md5 = hashlib.md5(f.read()).hexdigest()

    print(f"[*] Local  MD5: {local_md5}")
    print(f"[*] Router MD5: {router_md5}")

    if local_md5.lower() == router_md5.lower():
        print(f"\n[SUCCESS] Partition backup verified and saved to {local_archive}!")
        print("[!] KEEP THIS BACKUP SAFE. It contains unique device MAC and calibration data.")
        
        # Clean up router temp files
        cleanup_cmds = [
            "rm -rf /tmp/backup /tmp/send_backup.sh /tmp/backup_inetd.conf",
            f"/pfrm2.0/bin/iptables -D fwInBypass -p tcp --dport {stream_port} -m ifgroup --ifgroup-in 0x1/0x1 -j ACCEPT 2>/dev/null"
        ]
        exec_commands(cleanup_cmds, host=target_ip, password=root_pass, wait_between=0.5)
        return True
    else:
        print("\n[ERROR] MD5 checksum mismatch! Download may be corrupted.")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full Partition & Calibration Backup for JCOW414")
    parser.add_argument("--target", default="192.168.29.1", help="Router IP address (default: 192.168.29.1)")
    parser.add_argument("--password", default="password", help="Router root password (default: password)")
    parser.add_argument("--outdir", default="backup", help="Local directory to store backup (default: backup)")
    parser.add_argument("--port", type=int, default=9998, help="Streaming port (default: 9998)")
    args = parser.parse_args()

    success = perform_backup(target_ip=args.target, root_pass=args.password, output_dir=args.outdir, stream_port=args.port)
    sys.exit(0 if success else 1)
