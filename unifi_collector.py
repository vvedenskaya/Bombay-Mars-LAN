import requests
import json
import urllib3
import os

# Disable SSL warnings for self-signed certificates (common for local controllers)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class UniFiCollector:
    def __init__(self, base_url, api_key, site='default'):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.site = site
        self.session = requests.Session()
        # Set the API key in headers for all requests
        self.session.headers.update({
            'X-API-KEY': self.api_key,
            'Accept': 'application/json'
        })

    def get_devices(self):
        """Get list of all devices (APs, Switches, etc.) from UniFi"""
        # API keys in newer UniFi versions typically use the proxy path or direct API
        # We'll try the standard stat/device endpoint
        endpoint = f"/proxy/network/api/s/{self.site}/stat/device"
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.get(url, verify=False, timeout=10)
            if response.status_code == 200:
                return response.json().get('data', [])
            
            # If 404, try legacy path
            if response.status_code == 404:
                url = f"{self.base_url}/api/s/{self.site}/stat/device"
                response = self.session.get(url, verify=False, timeout=10)
                if response.status_code == 200:
                    return response.json().get('data', [])

            print(f"UniFi Error: {response.status_code} - {response.text}")
            return []
        except Exception as e:
            print(f"Error requesting UniFi devices: {e}")
            return []

class UISPCollector:
    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        # UISP uses x-auth-token for API keys
        self.session.headers.update({
            'x-auth-token': self.api_key,
            'Accept': 'application/json'
        })

    def get_devices(self):
        """Get list of all devices from UISP"""
        url = f"{self.base_url}/api/v1.0/devices"
        try:
            response = self.session.get(url, verify=False, timeout=10)
            if response.status_code == 200:
                return response.json()
            print(f"UISP Error: {response.status_code} - {response.text}")
            return []
        except Exception as e:
            print(f"Error requesting UISP devices: {e}")
            return []

def format_data_for_touchdesigner(unifi_devs, uisp_devs):
    """Combine and format data for TouchDesigner"""
    combined_data = {
        "unifi": [],
        "uisp": []
    }

    for dev in unifi_devs:
        combined_data["unifi"].append({
            'name': dev.get('name', dev.get('mac')),
            'type': dev.get('type'),
            'model': dev.get('model'),
            'state': dev.get('state'), # 1 = online, 0 = offline
            'clients': dev.get('num_sta', 0),
            'x': dev.get('x'),
            'y': dev.get('y'),
            'source': 'unifi'
        })

    for dev in uisp_devs:
        id_info = dev.get('identification', {})
        attr = dev.get('attributes', {})
        combined_data["uisp"].append({
            'name': id_info.get('name'),
            'model': id_info.get('model'),
            'type': id_info.get('type'),
            'state': dev.get('overview', {}).get('status'), # online/offline/etc
            'lat': attr.get('latitude'),
            'lon': attr.get('longitude'),
            'source': 'uisp'
        })

    return combined_data

if __name__ == "__main__":
    # Load from environment variables or hardcode for now
    # It's recommended to use a .env file
    UNIFI_URL = os.getenv("UNIFI_URL", "https://your-unifi-ip")
    UNIFI_KEY = os.getenv("UNIFI_KEY", "your-unifi-api-key")
    
    UISP_URL = os.getenv("UISP_URL", "https://your-uisp-ip")
    UISP_KEY = os.getenv("UISP_KEY", "your-uisp-api-key")

    print("Connecting to UniFi...")
    unifi_collector = UniFiCollector(UNIFI_URL, UNIFI_KEY)
    unifi_devices = unifi_collector.get_devices()

    print("Connecting to UISP...")
    uisp_collector = UISPCollector(UISP_URL, UISP_KEY)
    uisp_devices = uisp_collector.get_devices()

    # Process and Save
    final_data = format_data_for_touchdesigner(unifi_devices, uisp_devices)
    
    with open('network_data.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)

    print(f"Done! Collected {len(unifi_devices)} UniFi and {len(uisp_devices)} UISP devices.")
    print("Data saved to network_data.json")
