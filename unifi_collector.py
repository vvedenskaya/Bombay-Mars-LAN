import requests
import json
import urllib3
import os
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

class UniFiCollector:
    def __init__(self, base_url, api_key, site='default'):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.site = site
        self.session = requests.Session()
        self.session.headers.update({
            'x-api-key': self.api_key,
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0'
        })

    def get_devices(self):
        # Added the 'integration/v1' paths which are common for hosted controllers
        paths = [
            f"/proxy/network/integration/v1/sites/{self.site}/devices",
            f"/proxy/network/api/s/{self.site}/stat/device",
            f"/api/s/{self.site}/stat/device"
        ]
        
        for path in paths:
            url = f"{self.base_url}{path}"
            try:
                print(f"Trying UniFi path: {url}")
                response = self.session.get(url, verify=False, timeout=15)
                
                if response.status_code == 200:
                    try:
                        res_json = response.json()
                        # 'integration' API usually returns data directly or in a 'data' key
                        if isinstance(res_json, list): return res_json
                        return res_json.get('data', [])
                    except:
                        continue
                else:
                    print(f"  Result: {response.status_code}")
            except Exception as e:
                print(f"  Error on {path}: {e}")
        return []

class UISPCollector:
    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'x-auth-token': self.api_key,
            'Accept': 'application/json'
        })

    def get_devices(self):
        # We know v2.1 works for you!
        url = f"{self.base_url}/nms/api/v2.1/devices"
        try:
            print(f"Requesting UISP devices from: {url}")
            response = self.session.get(url, verify=False, timeout=15)
            if response.status_code == 200:
                return response.json()
            print(f"UISP Error: {response.status_code}")
            return []
        except Exception as e:
            print(f"Error requesting UISP: {e}")
            return []

def format_data_for_touchdesigner(unifi_devs, uisp_devs):
    combined_data = {"unifi": [], "uisp": []}
    
    # Process UniFi
    if isinstance(unifi_devs, list):
        for dev in unifi_devs:
            combined_data["unifi"].append({
                'name': dev.get('name', dev.get('mac')),
                'type': dev.get('type'),
                'model': dev.get('model'),
                'state': dev.get('state', 'online'), 
                'clients': dev.get('num_sta', 0),
                'x': dev.get('x'),
                'y': dev.get('y')
            })

    # Process UISP
    if isinstance(uisp_devs, list):
        for dev in uisp_devs:
            id_info = dev.get('identification', {})
            overview = dev.get('overview', {})
            combined_data["uisp"].append({
                'name': id_info.get('name'),
                'model': id_info.get('model'),
                'type': id_info.get('type'),
                'state': overview.get('status'),
                'lat': dev.get('attributes', {}).get('latitude'),
                'lon': dev.get('attributes', {}).get('longitude')
            })
    return combined_data

if __name__ == "__main__":
    UNIFI_URL = os.getenv("UNIFI_URL")
    UNIFI_KEY = os.getenv("UNIFI_KEY")
    UNIFI_SITE = os.getenv("UNIFI_SITE", "default")
    UISP_URL = os.getenv("UISP_URL")
    UISP_KEY = os.getenv("UISP_KEY")

    unifi_devices = []
    if UNIFI_URL and UNIFI_KEY:
        unifi_collector = UniFiCollector(UNIFI_URL, UNIFI_KEY, site=UNIFI_SITE)
        unifi_devices = unifi_collector.get_devices()

    uisp_devices = []
    if UISP_URL and UISP_KEY:
        uisp_collector = UISPCollector(UISP_URL, UISP_KEY)
        uisp_devices = uisp_collector.get_devices()

    final_data = format_data_for_touchdesigner(unifi_devices, uisp_devices)
    with open('network_data.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)

    print(f"\n--- Final Results ---")
    print(f"UniFi: {len(unifi_devices)} devices")
    print(f"UISP: {len(uisp_devices)} devices")
    print("Data saved to network_data.json")
