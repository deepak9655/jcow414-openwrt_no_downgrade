#!/usr/bin/env python3
"""
upload_firmware.py - Stream OpenWrt Firmware to Router RAM
Sercomm JioFiber JCOW414 (EcoNet EN7528 platform)

This script transfers the OpenWrt squashfs-tclinux.trx firmware image
from your PC directly into the router's RAM (/tmp/fw.trx) via an ephemeral
inetd TCP socket on port 9999.

Why TCP stream instead of HTTP server?
  Local HTTP servers hosted on Windows often fail due to Windows Defender Firewall
  blocking inbound connections on port 8000. Outbound PC-to-router TCP streaming
  bypasses host firewall blocks completely.
"""

import socket
import time
import os
import hashlib
import argparse
import sys
from router_utils import exec_commands

def upload_firmware(firmware_path, target_ip="192.168.29.1", root_pass="password", stream_port=9999):
    if not os.path.isfile(firmware_path):
        print(f"[ERROR] Firmware file not found: {firmware_path}")
        return False

    fw_size = os.path.getsize(firmware_path)
    with open(firmware_path, "rb") as f:
        local_md5 = hashlib.md5(f.read()).hexdigest()

    print("=" * 65)
    print(f"[*] Sercomm JCOW414 Firmware Upload to Router RAM")
    print(f"[*] Firmware File: {os.path.abspath(firmware_path)}")
    print(f"[*] File Size:     {fw_size:,} bytes ({fw_size / (1024*1024):.2f} MB)")
    print(f"[*] Local MD5:     {local_md5}")
    print(f"[*] Router IP:     {target_ip}")
    print(f"[*] Stream Port:   {stream_port}")
    print("=" * 65)

    # 1. Check router free RAM
    print("\n[*] Step 1: Checking router free RAM...")
    res = exec_commands(["free", "df -h /tmp"], host=target_ip, password=root_pass, wait_between=0.8)
    print(res.get("free", "").strip())

    # 2. Configure inetd receiver on router
    print(f"\n[*] Step 2: Setting up receiver service on router port {stream_port}...")
    setup_cmds = [
        "rm -f /tmp/fw.trx /tmp/recv_fw.sh /tmp/upload_inetd.conf",
        f"printf '#!/bin/sh\\ncat > /tmp/fw.trx\\n' > /tmp/recv_fw.sh",
        "chmod +x /tmp/recv_fw.sh",
        f"echo '{stream_port} stream tcp nowait root /tmp/recv_fw.sh recv_fw.sh' > /tmp/upload_inetd.conf",
        f"/pfrm2.0/bin/iptables -I fwInBypass -p tcp --dport {stream_port} -m ifgroup --ifgroup-in 0x1/0x1 -j ACCEPT",
        "killall inetd 2>/dev/null; busybox inetd /tmp/upload_inetd.conf"
    ]
    exec_commands(setup_cmds, host=target_ip, password=root_pass, wait_between=0.6)
    time.sleep(1.0)

    # 3. Stream firmware to router
    print(f"\n[*] Step 3: Streaming firmware to router /tmp/fw.trx...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(20.0)
    s.connect((target_ip, stream_port))

    sent_bytes = 0
    start_time = time.time()
    with open(firmware_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            s.sendall(chunk)
            sent_bytes += len(chunk)
            progress = (sent_bytes / fw_size) * 100
            sys.stdout.write(f"\r    Uploading: {progress:5.1f}% [{sent_bytes:,}/{fw_size:,} bytes]")
            sys.stdout.flush()

    s.close()
    elapsed = time.time() - start_time
    print(f"\n[+] Stream completed in {elapsed:.1f}s ({sent_bytes / elapsed / 1024:.1f} KB/s)")

    # 4. Verify MD5 on router
    print("\n[*] Step 4: Verifying firmware integrity on router...")
    verify_cmds = [
        "ls -la /tmp/fw.trx",
        "md5sum /tmp/fw.trx"
    ]
    res_verify = exec_commands(verify_cmds, host=target_ip, password=root_pass, wait_between=1.5)
    
    router_md5 = ""
    for line in res_verify.get("md5sum /tmp/fw.trx", "").splitlines():
        if "fw.trx" in line and not line.strip().startswith("md5sum"):
            router_md5 = line.split()[0].strip()
            break

    print(f"[*] Local  MD5: {local_md5}")
    print(f"[*] Router MD5: {router_md5}")

    if local_md5.lower() == router_md5.lower():
        print(f"\n[SUCCESS] Firmware uploaded and verified successfully in /tmp/fw.trx!")
        print("[*] Ready for flashing with flash_and_swap.py")
        return True
    else:
        print("\n[ERROR] Checksum verification failed on router! Upload may be corrupted.")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload OpenWrt Firmware to JCOW414 Router RAM")
    parser.add_argument("firmware", nargs="?", default="openwrt-jcow414-squashfs-tclinux.trx", help="Path to openwrt-jcow414-squashfs-tclinux.trx")
    parser.add_argument("--target", default="192.168.29.1", help="Router IP address (default: 192.168.29.1)")
    parser.add_argument("--password", default="password", help="Router root password (default: password)")
    parser.add_argument("--port", type=int, default=9999, help="Streaming port (default: 9999)")
    args = parser.parse_args()

    success = upload_firmware(firmware_path=args.firmware, target_ip=args.target, root_pass=args.password, stream_port=args.port)
    sys.exit(0 if success else 1)
