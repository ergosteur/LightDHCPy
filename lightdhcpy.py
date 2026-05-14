#!/usr/bin/env python3
"""
=============================================================================
LightDHCPy - The Lightweight Python DHCP Server
=============================================================================
Description:
    A feature-rich, zero-dependency IPv4 DHCP server written entirely in 
    standard Python 3. It handles the basic DORA process, manages static 
    and dynamic leases, and includes a built-in Web UI for real-time 
    monitoring and configuration hot-reloading.

Features:
    - No external dependencies (uses only Python's standard library).
    - Built-in Web UI Dashboard for real-time lease monitoring.
    - Basic Authentication for the Web UI (default: admin:admin).
    - In-browser JSON configuration editor with hot-reloading.
    - Interactive `--quickstart` wizard for instant setup.
    - Supports PXE booting, static leases, and custom DHCP options.

Usage:
    1. Quickstart Wizard (Recommended for first run):
        sudo python3 lightdhcpy.py --quickstart
        
    2. Run with Web UI and existing config:
        sudo python3 lightdhcpy.py -c config.json --web-port 8080
        
    3. Manual CLI configuration:
        sudo python3 lightdhcpy.py --server-ip 192.168.1.1 --start 192.168.1.100 \
                                 --end 192.168.1.200 --subnet 255.255.255.0 \
                                 --web-port 8080

Disclaimer:
    This code was developed with the assistance of Google's Gemini. It is an 
    educational/experimental tool and is NOT intended for production use. It 
    was designed strictly for use in isolated lab or network testing environments. 
    
    IMPORTANT: To ensure cross-platform compatibility with UDP broadcasts, this 
    server binds to ALL interfaces (0.0.0.0:67). It WILL respond to DHCP 
    requests on networks you may not intend to serve. You MUST use your host 
    operating system's firewall (iptables, Windows Firewall, ufw, etc.) to block 
    UDP port 67 on any interfaces where you do not want this server to act as a 
    DHCP server.
    
    Running a DHCP server on a network that already has an active DHCP server 
    (like your home router or corporate network) can cause a "Rogue DHCP" 
    scenario, resulting in IP conflicts and severe network outages. Use with 
    extreme caution.
=============================================================================
"""

import socket
import struct
import argparse
import ipaddress
import json
import logging
import time
import os
import sys
import threading
import http.server
import base64

WEB_UI_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LightDHCPy Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f4f4f9; color: #333; margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
        .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .stat-box { background: #f8f9fa; padding: 15px; border-radius: 6px; text-align: center; border: 1px solid #e9ecef; }
        .stat-box .value { font-size: 24px; font-weight: bold; color: #3498db; margin-top: 5px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; font-weight: 600; color: #555; }
        tr:hover { background-color: #f1f1f1; }
        .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .badge-active { background-color: #2ecc71; color: white; }
        .badge-static { background-color: #3498db; color: white; }
        .refresh-btn { background-color: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; font-size: 14px; transition: background 0.2s;}
        .refresh-btn:hover { background-color: #2980b9; }
        
        .alert-warning { background-color: #fff3cd; color: #856404; padding: 15px; border-radius: 6px; border: 1px solid #ffeeba; margin-bottom: 20px; font-size: 14px; line-height: 1.5; }
        
        /* Modal & Editor Styles */
        .btn-warning { background-color: #f39c12; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; font-size: 14px; transition: background 0.2s; }
        .btn-warning:hover { background-color: #e67e22; }
        .btn-success { background-color: #2ecc71; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 16px; margin-top: 15px;}
        .btn-success:hover { background-color: #27ae60; }
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.6); }
        .modal-content { background-color: #fefefe; margin: 5% auto; padding: 25px; border-radius: 8px; width: 80%; max-width: 800px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .close { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; line-height: 20px;}
        .close:hover { color: #333; }
        textarea.config-area { width: 100%; height: 400px; font-family: monospace; padding: 12px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; resize: vertical; font-size: 14px; background: #f8f9fa; }
        
        #restarting-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(255,255,255,0.95); z-index: 2000; justify-content: center; align-items: center; flex-direction: column; font-size: 24px; color: #333;}
        .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite; margin-bottom: 20px;}
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        /* Custom Notification */
        #notification-box { display: none; padding: 15px; margin-bottom: 15px; border-radius: 4px; color: white; font-weight: bold; }
        .notif-error { background-color: #e74c3c; }
        .notif-success { background-color: #2ecc71; }
    </style>
</head>
<body>
    <div class="container">
        <h1>
            LightDHCPy Dashboard
            <div>
                <button class="btn-warning" onclick="openConfigEditor()" style="margin-right: 10px;">Edit Config</button>
                <button class="refresh-btn" onclick="fetchStatus()">Refresh Data</button>
            </div>
        </h1>
        
        <div id="notification-box"></div>

        <div class="alert-warning">
            <strong>⚠️ Security Warning:</strong> Bound to <strong>0.0.0.0</strong>. Use OS firewall to block UDP port 67 on excluded interfaces.
        </div>
        
        <div class="card grid">
            <div class="stat-box">
                <div>Interface IP</div>
                <div class="value" id="info-ip">-</div>
            </div>
            <div class="stat-box">
                <div>Subnet Mask</div>
                <div class="value" id="info-subnet">-</div>
            </div>
            <div class="stat-box">
                <div>Available Pool IPs</div>
                <div class="value" id="info-pool">-</div>
            </div>
        </div>

        <div class="card">
            <h2>Active Leases (<span id="lease-count">0</span>)</h2>
            <table id="leases-table">
                <thead>
                    <tr>
                        <th>IP Address</th>
                        <th>MAC Address</th>
                        <th>Hostname</th>
                        <th>Vendor Class</th>
                        <th>Expires In</th>
                        <th>Type</th>
                    </tr>
                </thead>
                <tbody>
                    <tr><td colspan="6" style="text-align: center;">Loading...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- Configuration Editor Modal -->
    <div id="configModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeConfigEditor()">&times;</span>
            <h2 style="margin-top: 0; color: #2c3e50;">Edit Configuration (config.json)</h2>
            <div id="modal-notification" style="display:none; padding:10px; margin-bottom:10px; border-radius:4px; background:#e74c3c; color:white;"></div>
            <p style="color: #666; font-size: 14px; margin-bottom: 15px;">Saving will trigger a hot-reload of the DHCP server process.</p>
            <textarea id="config-text" class="config-area"></textarea>
            <div style="text-align: right;">
                <button class="btn-success" onclick="saveAndReload()">Save & Restart Server</button>
            </div>
        </div>
    </div>

    <!-- Restarting Overlay -->
    <div id="restarting-overlay">
        <div class="spinner"></div>
        <div>Restarting DHCP Server...</div>
        <div style="font-size: 14px; color: #666; margin-top: 10px;">Waiting for server to come back online</div>
    </div>

    <script>
        function showNotification(message, isError = false, targetId = 'notification-box') {
            const box = document.getElementById(targetId);
            box.style.display = 'block';
            box.innerText = message;
            box.className = isError ? 'notif-error' : 'notif-success';
            setTimeout(() => { box.style.display = 'none'; }, 5000);
        }

        function fetchStatus() {
            fetch('/api/status')
                .then(response => {
                    if(response.status === 401) {
                        showNotification("Authentication required. Please refresh and login.", true);
                        throw new Error("Unauthorized");
                    }
                    return response.json()
                })
                .then(data => {
                    document.getElementById('info-ip').innerText = data.config.server_ip;
                    document.getElementById('info-subnet').innerText = data.config.subnet;
                    document.getElementById('info-pool').innerText = data.config.available_ips;
                    
                    const tbody = document.querySelector('#leases-table tbody');
                    tbody.innerHTML = '';
                    
                    let count = 0;
                    const now = Date.now() / 1000;

                    for (const [mac, info] of Object.entries(data.leases)) {
                        count++;
                        const tr = document.createElement('tr');
                        const isStatic = Object.keys(data.static_leases).includes(mac);
                        
                        let expiresIn = "Never";
                        let badgeClass = "badge-static";
                        let badgeText = "Static";

                        if (!isStatic) {
                            const secondsLeft = Math.max(0, Math.floor(info.expires - now));
                            const hours = Math.floor(secondsLeft / 3600);
                            const minutes = Math.floor((secondsLeft % 3600) / 60);
                            expiresIn = `${hours}h ${minutes}m`;
                            badgeClass = "badge-active";
                            badgeText = "Dynamic";
                        }

                        tr.innerHTML = `
                            <td><strong>${info.ip}</strong></td>
                            <td style="font-family: monospace;">${mac}</td>
                            <td>${info.hostname || '-'}</td>
                            <td>${info.vendor_class || '-'}</td>
                            <td>${expiresIn}</td>
                            <td><span class="badge ${badgeClass}">${badgeText}</span></td>
                        `;
                        tbody.appendChild(tr);
                    }

                    if (count === 0) {
                        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">No active leases</td></tr>';
                    }
                    document.getElementById('lease-count').innerText = count;
                })
                .catch(err => console.error("Error fetching status:", err));
        }

        function openConfigEditor() {
            fetch('/api/config')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('config-text').value = JSON.stringify(data, null, 4);
                    document.getElementById('configModal').style.display = 'block';
                    document.getElementById('modal-notification').style.display = 'none';
                })
                .catch(err => showNotification("Error fetching config: " + err, true));
        }

        function closeConfigEditor() {
            document.getElementById('configModal').style.display = 'none';
        }

        function saveAndReload() {
            const rawText = document.getElementById('config-text').value;
            try {
                JSON.parse(rawText);
            } catch (e) {
                showNotification("Invalid JSON format: " + e.message, true, 'modal-notification');
                return;
            }

            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: rawText
            })
            .then(async res => {
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || "Failed to save configuration.");
                return data;
            })
            .then(() => {
                closeConfigEditor();
                document.getElementById('restarting-overlay').style.display = 'flex';
                
                let attempts = 0;
                const pollInterval = setInterval(() => {
                    attempts++;
                    fetch('/api/status')
                        .then(res => {
                            if (res.ok || res.status === 401) {
                                clearInterval(pollInterval);
                                window.location.reload(); 
                            }
                        })
                        .catch(() => {
                            if (attempts > 15) {
                                clearInterval(pollInterval);
                                showNotification("Server offline. It may have crashed due to invalid config. Check console logs.", true);
                                document.getElementById('restarting-overlay').style.display = 'none';
                            }
                        });
                }, 1000);
            })
            .catch(err => showNotification(err.message, true, 'modal-notification'));
        }

        fetchStatus();
        setInterval(fetchStatus, 5000); 
    </script>
</body>
</html>
"""

class WebUIHandler(http.server.BaseHTTPRequestHandler):
    
    def check_auth(self):
        # Basic Auth implementation
        expected_user = self.server.dhcp_server.web_user
        expected_pass = self.server.dhcp_server.web_pass
        
        if not expected_user:
            return True # Auth disabled
            
        auth_header = self.headers.get('Authorization')
        if auth_header:
            auth_type, encoded_creds = auth_header.split(' ', 1)
            if auth_type.lower() == 'basic':
                try:
                    decoded = base64.b64decode(encoded_creds).decode('utf-8')
                    user, pwd = decoded.split(':', 1)
                    if user == expected_user and pwd == expected_pass:
                        return True
                except Exception:
                    pass
                    
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="LightDHCPy Dashboard"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Unauthorized')
        return False

    def do_GET(self):
        if not self.check_auth():
            return
            
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(WEB_UI_HTML.encode('utf-8'))
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            dhcp = self.server.dhcp_server
            status = {
                "config": {
                    "server_ip": dhcp.server_ip,
                    "subnet": dhcp.subnet,
                    "available_ips": len(dhcp.ip_pool)
                },
                "leases": dhcp.leases,
                "static_leases": dhcp.static_leases
            }
            self.wfile.write(json.dumps(status).encode('utf-8'))
        elif self.path == '/api/config':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            dhcp = self.server.dhcp_server
            config_str = json.dumps(dhcp.current_config_dict, indent=4)
            self.wfile.write(config_str.encode('utf-8'))
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.check_auth():
            return
            
        if self.path == '/api/config':
            dhcp = self.server.dhcp_server
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                new_config = json.loads(post_data)
                
                # Validation Step to prevent boot loops
                try:
                    ipaddress.IPv4Address(new_config.get('server_ip'))
                    ipaddress.IPv4Address(new_config.get('start'))
                    ipaddress.IPv4Address(new_config.get('end'))
                    ipaddress.IPv4Address(new_config.get('subnet'))
                except ValueError as ve:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"Invalid IP format in config: {ve}"}).encode('utf-8'))
                    return
                
                save_path = dhcp.config_file or "config.json"
                
                with open(save_path, 'w') as f:
                    json.dump(new_config, f, indent=4)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
                
                # Signal reload
                dhcp.needs_reload = True
                dhcp.reload_config_path = save_path
                
            except json.JSONDecodeError as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid JSON", "details": str(e)}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Internal Error", "details": str(e)}).encode('utf-8'))
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        logging.debug(f"WebUI: {self.client_address[0]} - {format % args}")

class ReuseHTTPServer(http.server.HTTPServer):
    allow_reuse_address = True

def run_web_ui(dhcp_server, port):
    server_address = ('0.0.0.0', port)
    httpd = ReuseHTTPServer(server_address, WebUIHandler)
    httpd.dhcp_server = dhcp_server
    logging.info(f"Web UI started on http://0.0.0.0:{port}")
    if dhcp_server.web_user:
        logging.info(f"Web UI Auth -> User: {dhcp_server.web_user} (Password is set)")
    httpd.serve_forever()

class MinimalDHCPServer:
    def __init__(self, interface_ip, start_ip, end_ip, subnet, gateway=None, dns=None, lease_file="leases.json", static_leases=None, next_server=None, boot_file=None, custom_options=None, web_user="admin", web_pass="admin"):
        self.server_ip = interface_ip
        self.subnet = subnet
        self.gateway = gateway
        self.dns = dns
        self.lease_time = 86400
        self.lease_file = lease_file
        self.static_leases = static_leases or {}
        self.next_server = next_server or '0.0.0.0'
        self.boot_file = boot_file or ''
        self.custom_options = custom_options or []
        self.web_user = web_user
        self.web_pass = web_pass
        
        self.last_disk_save = 0  # Debounce timer
        
        net = ipaddress.IPv4Network(f"{self.server_ip}/{self.subnet}", strict=False)
        self.broadcast_ip = str(net.broadcast_address)
        
        start = int(ipaddress.IPv4Address(start_ip))
        end = int(ipaddress.IPv4Address(end_ip))
        self.ip_pool = [str(ipaddress.IPv4Address(i)) for i in range(start, end + 1)]
        
        self.leases = {}
        self.load_leases()
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(('0.0.0.0', 67))
        self.sock.settimeout(1.0) 

    def load_leases(self):
        if os.path.exists(self.lease_file):
            try:
                with open(self.lease_file, 'r') as f:
                    self.leases = json.load(f)
                for mac, data in self.leases.items():
                    if data['ip'] in self.ip_pool:
                        self.ip_pool.remove(data['ip'])
                logging.info(f"Loaded {len(self.leases)} active leases")
            except Exception as e:
                logging.error(f"Failed to load leases: {e}")

    def save_leases(self, force=False):
        """Save leases with debounce to avoid disk thrashing during DHCP storms"""
        now = time.time()
        if force or (now - self.last_disk_save > 5):
            try:
                with open(self.lease_file, 'w') as f:
                    json.dump(self.leases, f, indent=4)
                self.last_disk_save = now
            except Exception as e:
                logging.error(f"Failed to save leases: {e}")

    def clean_expired_leases(self):
        now = time.time()
        expired_macs = []
        for mac, data in self.leases.items():
            if mac in self.static_leases:
                continue 
            if data['expires'] < now:
                expired_macs.append(mac)
        
        for mac in expired_macs:
            ip = self.leases.pop(mac)['ip']
            self.ip_pool.append(ip)
            logging.info(f"[*] Lease for {mac} ({ip}) expired")
        
        if expired_macs:
            self.save_leases(force=True)

    def get_ip_for_mac(self, mac_hex, options=None):
        options = options or {}
        hostname = options.get('hostname', '')
        vendor_class = options.get('vendor_class', '')

        if mac_hex in self.static_leases:
            ip = self.static_leases[mac_hex]
            self.leases[mac_hex] = {
                'ip': ip, 
                'expires': time.time() + self.lease_time,
                'hostname': hostname or self.leases.get(mac_hex, {}).get('hostname', ''),
                'vendor_class': vendor_class or self.leases.get(mac_hex, {}).get('vendor_class', '')
            }
            self.save_leases()
            return ip

        if mac_hex in self.leases:
            self.leases[mac_hex]['expires'] = time.time() + self.lease_time 
            if hostname: self.leases[mac_hex]['hostname'] = hostname
            if vendor_class: self.leases[mac_hex]['vendor_class'] = vendor_class
            self.save_leases()
            return self.leases[mac_hex]['ip']
            
        if not self.ip_pool:
            logging.warning("[-] No more IP addresses available in the pool.")
            return None
            
        ip = self.ip_pool.pop(0)
        self.leases[mac_hex] = {
            'ip': ip, 
            'expires': time.time() + self.lease_time,
            'hostname': hostname,
            'vendor_class': vendor_class
        }
        self.save_leases()
        return ip

    def parse_options(self, options_data):
        options = {}
        i = 0
        while i < len(options_data):
            tag = options_data[i]
            if tag == 255: break
            if tag == 0:
                i += 1
                continue
            
            length = options_data[i+1]
            value = options_data[i+2 : i+2+length]
            
            if tag == 53: options['msg_type'] = value[0]
            elif tag == 50: options['req_ip'] = socket.inet_ntoa(value)
            elif tag == 12: options['hostname'] = value.decode('utf-8', errors='ignore')
            elif tag == 60: options['vendor_class'] = value.decode('utf-8', errors='ignore')
                
            i += 2 + length
        return options

    def build_packet(self, xid, mac_padded, yiaddr, msg_type, flags):
        packet = b''
        packet += b'\x02\x01\x06\x00'
        packet += xid              
        packet += b'\x00\x00'      
        packet += flags            
        packet += b'\x00\x00\x00\x00' 
        packet += socket.inet_aton(yiaddr) 
        packet += socket.inet_aton(self.next_server) 
        packet += b'\x00\x00\x00\x00' 
        packet += mac_padded       
        packet += b'\x00' * 64     
        
        boot_file_bytes = self.boot_file.encode('utf-8')
        if len(boot_file_bytes) < 128:
            boot_file_bytes += b'\x00' * (128 - len(boot_file_bytes))
        packet += boot_file_bytes[:128]
        
        packet += b'\x63\x82\x53\x63' 
        
        packet += b'\x35\x01' + bytes([msg_type])
        packet += b'\x36\x04' + socket.inet_aton(self.server_ip)
        packet += b'\x33\x04' + struct.pack("!I", self.lease_time)
        packet += b'\x01\x04' + socket.inet_aton(self.subnet)
        
        if self.gateway:
            packet += b'\x03\x04' + socket.inet_aton(self.gateway)
        if self.dns:
            packet += b'\x06\x04' + socket.inet_aton(self.dns)
            
        for code, raw_bytes in self.custom_options:
            packet += bytes([code, len(raw_bytes)]) + raw_bytes
            
        packet += b'\xff'
        if len(packet) < 300:
            packet += b'\x00' * (300 - len(packet))
            
        return packet

    def run(self):
        logging.info("LightDHCPy Server started.")
        logging.info(f"Server IP: {self.server_ip}")
        logging.info(f"Pool: {self.ip_pool[0]} - {self.ip_pool[-1] if self.ip_pool else 'Empty'}")
        
        try:
            while True:
                if getattr(self, 'needs_reload', False):
                    logging.info("[*] Reload requested via Web UI. Restarting server...")
                    break

                self.clean_expired_leases()
                
                try:
                    data, addr = self.sock.recvfrom(1024)
                except socket.timeout:
                    continue
                
                if len(data) < 240: continue
                if data[0] != 1: continue

                xid = data[4:8]
                flags = data[10:12]
                mac_bytes = data[28:34]
                mac_padded = data[28:44]
                mac_hex = mac_bytes.hex(':')
                
                options = self.parse_options(data[240:])
                msg_type = options.get('msg_type')

                if msg_type == 1: 
                    logging.info(f"[>] DHCP DISCOVER from {mac_hex}")
                    ip = self.get_ip_for_mac(mac_hex, options)
                    if ip:
                        reply = self.build_packet(xid, mac_padded, ip, 2, flags)
                        self.sock.sendto(reply, (self.broadcast_ip, 68))
                        logging.info(f"[<] DHCP OFFER {ip} to {mac_hex}")

                elif msg_type == 3: 
                    logging.info(f"[>] DHCP REQUEST from {mac_hex}")
                    req_ip = options.get('req_ip')
                    ciaddr = socket.inet_ntoa(data[12:16])
                    if not req_ip and ciaddr != '0.0.0.0':
                        req_ip = ciaddr
                        
                    ip = self.get_ip_for_mac(mac_hex, options)
                    
                    if ip and (req_ip == ip or req_ip is None):
                        reply = self.build_packet(xid, mac_padded, ip, 5, flags)
                        self.sock.sendto(reply, (self.broadcast_ip, 68))
                        logging.info(f"[<] DHCP ACK {ip} to {mac_hex}")
                    else:
                        reply = self.build_packet(xid, mac_padded, '0.0.0.0', 6, flags)
                        self.sock.sendto(reply, (self.broadcast_ip, 68))
                        logging.info(f"[<] DHCP NAK sent to {mac_hex}")

                elif msg_type == 7: 
                    logging.info(f"[>] DHCP RELEASE from {mac_hex}")
                    if mac_hex in self.leases:
                        rel_ip = self.leases.pop(mac_hex)['ip']
                        if rel_ip not in self.static_leases.values():
                            self.ip_pool.append(rel_ip)
                        self.save_leases(force=True)
                        logging.info(f"[*] Released IP {rel_ip}")
                        
        except KeyboardInterrupt:
            logging.info("\n[*] Shutting down DHCP server.")
        finally:
            self.save_leases(force=True)
            self.sock.close()
            
        if getattr(self, 'needs_reload', False):
            config_path = getattr(self, 'reload_config_path', 'config.json')
            exec_args = [sys.argv[0], '-c', config_path]
            os.execv(sys.executable, [sys.executable] + exec_args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", help="Path to a JSON configuration file")
    parser.add_argument("--server-ip", help="The IP address of the interface running this server")
    parser.add_argument("--start", help="Start of the IP pool (e.g., 192.168.1.100)")
    parser.add_argument("--end", help="End of the IP pool (e.g., 192.168.1.200)")
    parser.add_argument("--subnet", help="Subnet mask (e.g., 255.255.255.0)")
    parser.add_argument("--gateway", help="Default gateway IP (optional)")
    parser.add_argument("--dns", help="DNS server IP (optional)")
    parser.add_argument("--lease-file", help="File to persist leases")
    parser.add_argument("--static", action="append", help="Static lease MAC=IP")
    parser.add_argument("--next-server", help="PXE Next Server IP")
    parser.add_argument("--boot-file", help="PXE Boot File Name")
    parser.add_argument("--option", action="append", help="Custom DHCP option CODE:TYPE:VALUE")
    parser.add_argument("--web-port", type=int, help="Enable Web UI on specified port")
    parser.add_argument("--web-user", default="admin", help="Web UI Username")
    parser.add_argument("--web-pass", default="admin", help="Web UI Password")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging output")
    parser.add_argument("--generate-config", metavar="FILE", help="Generate a sample config")
    parser.add_argument("--quickstart", action="store_true", help="Interactive wizard")
    
    args = parser.parse_args()

    if args.quickstart:
        print("=================================================")
        print("  LightDHCPy - Quickstart Wizard                 ")
        print("=================================================")
        while True:
            server_ip_str = input("Enter this machine's IP address (e.g., 192.168.1.10): ").strip()
            try:
                ipaddress.IPv4Address(server_ip_str)
                break
            except ValueError:
                print("[-] Invalid IP format.")

        octets = server_ip_str.split('.')
        base_ip = f"{octets[0]}.{octets[1]}.{octets[2]}"

        web_port_str = input("Enter Web UI Port [8080]: ").strip()
        web_port = int(web_port_str) if web_port_str.isdigit() else 8080

        quick_config = {
            "server_ip": server_ip_str,
            "start": f"{base_ip}.100",
            "end": f"{base_ip}.200",
            "subnet": "255.255.255.0",
            "gateway": f"{base_ip}.1",
            "dns": "8.8.8.8",
            "lease_file": "leases.json",
            "debug": False,
            "web_port": web_port,
            "web_user": "admin",
            "web_pass": "admin",
            "static": {},
            "custom_options": []
        }

        config_file = "config.json"
        if os.path.exists(config_file):
            if input(f"[!] '{config_file}' exists. Overwrite? (y/N): ").lower() != 'y':
                config_file = "quickstart_config.json"

        try:
            with open(config_file, 'w') as f:
                json.dump(quick_config, f, indent=4)
            args.config = config_file
        except Exception as e:
            sys.exit(1)

    # Simplified Config loader for improved readability
    config_data = {}
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config_data = json.load(f)
        except Exception as e:
            sys.exit(1)

    def get_val(cli_val, key, default=None):
        return cli_val if cli_val is not None else config_data.get(key, default)

    server_ip = get_val(args.server_ip, 'server_ip')
    start_ip = get_val(args.start, 'start')
    end_ip = get_val(args.end, 'end')
    subnet = get_val(args.subnet, 'subnet')

    if not all([server_ip, start_ip, end_ip, subnet]) and not args.generate_config:
        parser.error("Missing required arguments. --server-ip, --start, --end, and --subnet are required.")

    gateway = get_val(args.gateway, 'gateway')
    dns = get_val(args.dns, 'dns')
    lease_file = get_val(args.lease_file, 'lease_file', 'leases.json')
    next_server = get_val(args.next_server, 'next_server')
    boot_file = get_val(args.boot_file, 'boot_file')
    debug_mode = True if '--debug' in sys.argv else config_data.get('debug', False)
    web_port = get_val(args.web_port, 'web_port')
    web_user = get_val(args.web_user, 'web_user', 'admin')
    web_pass = get_val(args.web_pass, 'web_pass', 'admin')

    log_level = logging.DEBUG if debug_mode else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')

    def parse_custom_option(opt_str):
        try:
            parts = opt_str.split(':', 2)
            code, otype, val = int(parts[0]), parts[1].lower(), parts[2]
            if otype == 'string': raw = val.encode('utf-8')
            elif otype == 'ip': raw = socket.inet_aton(val)
            elif otype == 'ips': raw = b''.join(socket.inet_aton(ip.strip()) for ip in val.split(','))
            elif otype == 'hex': raw = bytes.fromhex(val)
            else: return None
            return (code, raw)
        except Exception:
            return None

    static_mappings = {}
    config_static = config_data.get('static', {})
    if isinstance(config_static, dict):
        for mac, ip in config_static.items(): static_mappings[mac.lower()] = ip

    raw_options = config_data.get('custom_options', [])
    parsed_custom_options = [parse_custom_option(opt) for opt in raw_options if parse_custom_option(opt)]

    used_config = {
        "server_ip": server_ip,
        "start": start_ip,
        "end": end_ip,
        "subnet": subnet,
        "gateway": gateway,
        "dns": dns,
        "lease_file": lease_file,
        "next_server": next_server,
        "boot_file": boot_file,
        "web_port": web_port,
        "web_user": web_user,
        "web_pass": web_pass,
        "debug": debug_mode,
        "static": static_mappings,
        "custom_options": raw_options
    }

    if args.generate_config:
        with open(args.generate_config, 'w') as f:
            json.dump(used_config, f, indent=4)
        sys.exit(0)

    server = MinimalDHCPServer(
        interface_ip=server_ip, start_ip=start_ip, end_ip=end_ip, subnet=subnet,
        gateway=gateway, dns=dns, lease_file=lease_file, static_leases=static_mappings,
        next_server=next_server, boot_file=boot_file, custom_options=parsed_custom_options,
        web_user=web_user, web_pass=web_pass
    )
    
    server.config_file = args.config
    server.current_config_dict = used_config
    
    if web_port:
        web_thread = threading.Thread(target=run_web_ui, args=(server, int(web_port)), daemon=True)
        web_thread.start()
        
    server.run()
