import socket
import ipaddress
import subprocess
import re

# UNTESTED CODE!!! DO NOT USE WITHOUT REVIEW AND TEST!!!
def _get_local_ip_robust(self, dest_ip="192.168.1.100"):
    """
    Get local IP address without internet dependency
    Uses the destination IP to determine which local interface to use
    """
    try:
        # Method 1: Use destination IP to find appropriate local interface
        # This creates a UDP socket and "connects" to the destination
        # No actual packets are sent, but the OS determines routing
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((dest_ip, 1))  # Use any port, no data sent
            local_ip = s.getsockname()[0]
            
            # Validate it's not localhost and is a proper private IP
            if local_ip != "127.0.0.1" and self._is_valid_local_ip(local_ip):
                return local_ip
                
    except Exception as e:
        print(f"Method 1 failed: {e}")
    
    try:
        # Method 2: Find best interface by examining network interfaces
        return self._get_best_interface_ip()
        
    except Exception as e:
        print(f"Method 2 failed: {e}")
    
    try:
        # Method 3: Parse routing table to find default gateway interface
        return self._get_ip_from_route()
        
    except Exception as e:
        print(f"Method 3 failed: {e}")
    
    # Final fallback - but warn the user
    print("⚠️  Warning: Using localhost fallback. Manual IP configuration recommended.")
    return "127.0.0.1"

def _is_valid_local_ip(self, ip_str):
    """Check if IP is valid for local network use"""
    try:
        ip = ipaddress.IPv4Address(ip_str)
        # Accept private networks and link-local
        return (ip.is_private or 
                ip_str.startswith("169.254.") or  # Link-local
                ip_str.startswith("10.") or       # Private Class A
                ip_str.startswith("172.") or      # Private Class B  
                ip_str.startswith("192.168."))    # Private Class C
    except:
        return False

def _get_best_interface_ip(self):
    """Find the best network interface IP"""
    import netifaces
    
    # Get all interfaces
    interfaces = netifaces.interfaces()
    
    # Priority order: eth0, wlan0, then others
    priority_interfaces = ['eth0', 'wlan0', 'en0', 'en1']
    
    for interface_name in priority_interfaces:
        if interface_name in interfaces:
            try:
                addresses = netifaces.ifaddresses(interface_name)
                if netifaces.AF_INET in addresses:
                    for addr_info in addresses[netifaces.AF_INET]:
                        ip = addr_info.get('addr')
                        if ip and self._is_valid_local_ip(ip):
                            return ip
            except:
                continue
    
    # If priority interfaces don't work, try all others
    for interface_name in interfaces:
        if interface_name not in priority_interfaces and not interface_name.startswith('lo'):
            try:
                addresses = netifaces.ifaddresses(interface_name)
                if netifaces.AF_INET in addresses:
                    for addr_info in addresses[netifaces.AF_INET]:
                        ip = addr_info.get('addr')
                        if ip and self._is_valid_local_ip(ip):
                            return ip
            except:
                continue
    
    raise Exception("No suitable network interface found")

def _get_ip_from_route(self):
    """Get IP by parsing the routing table (Linux)"""
    try:
        # Get default route
        result = subprocess.run(['ip', 'route', 'show', 'default'], 
                              capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            # Parse output like: "default via 192.168.1.1 dev eth0 proto dhcp src 192.168.1.100"
            for line in result.stdout.split('\n'):
                if 'src' in line:
                    match = re.search(r'src\s+(\d+\.\d+\.\d+\.\d+)', line)
                    if match:
                        ip = match.group(1)
                        if self._is_valid_local_ip(ip):
                            return ip
                
                # Alternative: get interface and look up its IP
                match = re.search(r'dev\s+(\w+)', line)
                if match:
                    interface = match.group(1)
                    return self._get_interface_ip(interface)
    
    except Exception as e:
        raise Exception(f"Route parsing failed: {e}")
    
    raise Exception("Could not determine IP from routing table")

def _get_interface_ip(self, interface_name):
    """Get IP address of specific interface"""
    try:
        result = subprocess.run(['ip', 'addr', 'show', interface_name], 
                              capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            # Parse output for inet lines
            for line in result.stdout.split('\n'):
                if 'inet ' in line and 'scope global' in line:
                    match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', line)
                    if match:
                        ip = match.group(1)
                        if self._is_valid_local_ip(ip):
                            return ip
    
    except Exception:
        pass
    
    raise Exception(f"Could not get IP for interface {interface_name}")

# Alternative simple version without external dependencies
def _get_local_ip_simple_fallback(self, dest_ip="192.168.1.100"):
    """
    Simplified version that works in most cases without internet
    """
    try:
        # Try to connect to destination (no actual packets sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((dest_ip, 1))
            local_ip = s.getsockname()[0]
            
            # Basic validation
            if (local_ip != "127.0.0.1" and 
                not local_ip.startswith("169.254.") and  # Avoid APIPA
                "." in local_ip):
                return local_ip
    except:
        pass
    
    # Fallback: try common private network ranges
    test_destinations = [
        "192.168.1.1",   # Common home router
        "192.168.0.1",   # Alternative home router
        "10.0.0.1",      # Corporate network
        "172.16.0.1"     # Another private range
    ]
    
    for test_ip in test_destinations:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((test_ip, 1))
                local_ip = s.getsockname()[0]
                if local_ip != "127.0.0.1":
                    return local_ip
        except:
            continue
    
    # If all else fails, try to get hostname IP
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        if local_ip != "127.0.0.1":
            return local_ip
    except:
        pass
    
    return "127.0.0.1"
