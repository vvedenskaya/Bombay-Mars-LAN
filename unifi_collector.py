import requests
import json
import urllib3

# Disable SSL warnings for self-signed certificates (common for local controllers)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class UniFiCollector:
    def __init__(self, base_url, username, password, site='default'):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.site = site
        self.session = requests.Session()
        self.is_unifi_os = False # Will be determined automatically

    def login(self):
        """Authenticate with the controller"""
        # Try path for UniFi OS (UDM, Cloud Key Gen2)
        login_url = f"{self.base_url}/api/auth/login"
        payload = {
            'username': self.username,
            'password': self.password,
            'remember': True
        }
        
        try:
            response = self.session.post(login_url, json=payload, verify=False, timeout=10)
            if response.status_code == 200:
                print("Login successful (UniFi OS)")
                self.is_unifi_os = True
                return True
            
            # If failed, try legacy path (Self-hosted Controller)
            login_url = f"{self.base_url}/api/login"
            response = self.session.post(login_url, json=payload, verify=False, timeout=10)
            if response.status_code == 200:
                print("Login successful (Legacy Controller)")
                self.is_unifi_os = False
                return True
            
            print(f"Login failed: {response.status_code}")
            return False
        except Exception as e:
            print(f"Error during login attempt: {e}")
            return False

    def get_devices(self):
        """Get list of all devices (APs, Switches, etc.)"""
        endpoint = f"/api/s/{self.site}/stat/device"
        if self.is_unifi_os:
            url = f"{self.base_url}/proxy/network{endpoint}"
        else:
            url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.get(url, verify=False, timeout=10)
            if response.status_code == 200:
                return response.json().get('data', [])
            else:
                print(f"Error fetching data: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error requesting devices: {e}")
            return []

    def format_for_map(self, devices):
        """Format data for Godot"""
        map_data = []
        for dev in devices:
            map_data.append({
                'name': dev.get('name', dev.get('mac')),
                'type': dev.get('type'),
                'model': dev.get('model'),
                'ip': dev.get('ip'),
                'mac': dev.get('mac'),
                'state': dev.get('state'), # 1 = online, 0 = offline
                'clients': dev.get('num_sta', 0),
                'satisfaction': dev.get('satisfaction', 0),
                # If x/y coordinates are set in UniFi Floorplan, they will be here:
                'x': dev.get('x'),
                'y': dev.get('y')
            })
        return map_data

if __name__ == "__main__":
    # REPLACE THESE WITH YOUR ACTUAL CREDENTIALS
    UNIFI_URL = "https://192.168.1.1" # Your controller IP
    USERNAME = "admin"
    PASSWORD = "your_password"
    
    collector = UniFiCollector(UNIFI_URL, USERNAME, PASSWORD)
    
    if collector.login():
        devices = collector.get_devices()
        formatted_data = collector.format_for_map(devices)
        
        # Save as JSON for Touch Des
        with open('unifi_data.json', 'w', encoding='utf-8') as f:
            json.dump(formatted_data, f, indent=4, ensure_ascii=False)
            
        print(f"Devices collected: {len(formatted_data)}")
        print("Data saved to unifi_data.json")
    else:
        print("Could not connect to UniFi.")
