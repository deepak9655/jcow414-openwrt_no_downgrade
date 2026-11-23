"""
router_utils.py - Telnet Communication and Socket Utilities
Part of the Sercomm JioFiber JCOW414 OpenWrt Flashing Toolkit.
Educational / Research use only.
"""

import socket
import time
import sys

def get_telnet_socket(host="192.168.29.1", port=23, username="root", password="password", timeout=8.0):
    """
    Connects to router via Telnet, negotiates IAC options, and logs in.
    Returns an open socket object.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((host, port))
    
    # Receive initial IAC sequence
    time.sleep(0.3)
    try:
        s.recv(1024)
    except socket.timeout:
        pass

    # Standard Telnet IAC negotiations response:
    # IAC WONT ECHO, IAC WONT NAWS, IAC DO ECHO, IAC DO SUPPRESS-GO-AHEAD
    s.sendall(b'\xff\xfc\x01\xff\xfc\x1f\xff\xfd\x01\xff\xfd\x03')
    time.sleep(0.3)
    
    try:
        s.recv(1024)
    except socket.timeout:
        pass
    
    # Send username
    s.sendall(f"{username}\r\n".encode())
    time.sleep(0.5)
    
    try:
        s.recv(1024)
    except socket.timeout:
        pass
    
    # Send password
    s.sendall(f"{password}\r\n".encode())
    time.sleep(0.8)
    
    try:
        s.recv(1024)
    except socket.timeout:
        pass
        
    return s


def exec_commands(commands, host="192.168.29.1", port=23, username="root", password="password", wait_between=1.0):
    """
    Executes a list of shell commands sequentially over Telnet and returns a dictionary of outputs.
    """
    s = get_telnet_socket(host=host, port=port, username=username, password=password)
    results = {}
    
    for cmd in commands:
        s.sendall(cmd.encode() + b'\r\n')
        time.sleep(wait_between)
        out = b""
        s.settimeout(1.0)
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                out += chunk
            except (socket.timeout, BlockingIOError):
                break
        s.settimeout(5.0)
        results[cmd] = out.decode(errors='ignore')
    
    s.close()
    return results


def check_port(host, port, timeout=3.0):
    """
    Checks if a TCP port is open.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
