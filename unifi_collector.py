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
                        if isinstance(res_json, list): return res_json
                        return res_json.get('data', [])
                    except: continue
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
        url = f"{self.base_url}/nms/api/v2.1/devices"
        try:
            print(f"Requesting UISP devices from: {url}")
            response = self.session.get(url, verify=False, timeout=15)
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"Error requesting UISP devices: {e}")
            return []

    def get_sites(self):
        url = f"{self.base_url}/nms/api/v2.1/sites"
        try:
            print(f"Requesting UISP sites from: {url}")
            response = self.session.get(url, verify=False, timeout=15)
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"Error requesting UISP sites: {e}")
            return []

def download_google_map(lat_min, lat_max, lon_min, lon_max, map_type='roadmap'):
    """
    Downloads a static map image from Google Maps Static API.
    map_type can be: roadmap, satellite, terrain, hybrid
    """
    api_key = os.getenv("GOOGLE_MAPS_KEY")
    if not api_key:
        print(f"Skipping {map_type} map: GOOGLE_MAPS_KEY not found in .env")
        return None

    center_lat = (lat_min + lat_max) / 2
    center_lon = (lon_min + lon_max) / 2
    
    # Calculate span for Google API (delta lat/lon)
    # Google Static Maps also supports paths/polygons to define a box,
    # but for a square map, we use the center and a zoom level or markers.
    # To ensure the box is covered, we'll use the 'visible' parameter.
    
    url = "https://maps.googleapis.com/maps/api/staticmap"
    params = {
        "center": f"{center_lat},{center_lon}",
        "size": "640x640", # Max size for free tier
        "scale": "2",     # Get 1280x1280 (High DPI)
        "maptype": map_type,
        "visible": f"{lat_min},{lon_min}|{lat_max},{lon_max}",
        "key": api_key
    }

    try:
        print(f"Downloading Google {map_type} map...")
        response = requests.get(url, params=params, timeout=20)
        if response.status_code == 200:
            filename = f"map_{map_type}.png"
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"Saved {filename}")
            return filename
        else:
            print(f"Google API Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error downloading Google map: {e}")
    return None

def format_data_for_touchdesigner(unifi_devs, uisp_devs, uisp_sites, get_map=False):
    combined_data = {"unifi": [], "uisp": [], "map_metadata": {}}
    
    site_map = {}
    if isinstance(uisp_sites, list):
        for site in uisp_sites:
            s_id = site.get('id')
            location = site.get('location', {})
            if s_id:
                site_map[s_id] = {
                    'lat': location.get('latitude'),
                    'lon': location.get('longitude')
                }

    # UniFi & UISP Processing (same as before)
    lats, lons = [], []
    
    # UniFi
    if isinstance(unifi_devs, list):
        for dev in unifi_devs:
            combined_data["unifi"].append({
                'name': dev.get('name', dev.get('mac')),
                'type': dev.get('type'),
                'model': dev.get('model'),
                'state': dev.get('state', 'online'), 
                'clients': dev.get('num_sta', 0),
                'x': dev.get('x'), 'y': dev.get('y')
            })

    # UISP
    if isinstance(uisp_devs, list):
        for dev in uisp_devs:
            id_info = dev.get('identification') or {}
            overview = dev.get('overview') or {}
            attr = dev.get('attributes') or {}
            loc = dev.get('location') or {}
            s_id = id_info.get('siteId')
            
            site_coords = site_map.get(s_id, {})
            lat = attr.get('latitude') or loc.get('latitude') or site_coords.get('lat')
            lon = attr.get('longitude') or loc.get('longitude') or site_coords.get('lon')
            
            if lat and lon:
                lats.append(float(lat))
                lons.append(float(lon))
            
            combined_data["uisp"].append({
                'name': id_info.get('name'),
                'model': id_info.get('model'),
                'type': id_info.get('type'),
                'state': overview.get('status'),
                'lat': lat, 'lon': lon
            })

    # Google Maps Generation
    if get_map and lats and lons:
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        
        # Padding
        lat_pad = (lat_max - lat_min) * 0.2 or 0.002
        lon_pad = (lon_max - lon_min) * 0.2 or 0.002
        lat_min -= lat_pad; lat_max += lat_pad
        lon_min -= lon_pad; lon_max += lon_pad

        combined_data["map_metadata"] = {
            "lat_min": lat_min, "lat_max": lat_max,
            "lon_min": lon_min, "lon_max": lon_max,
            "center": [(lat_min+lat_max)/2, (lon_min+lon_max)/2]
        }
        
        # Download maps using Google API
        download_google_map(lat_min, lat_max, lon_min, lon_max, 'roadmap')
        download_google_map(lat_min, lat_max, lon_min, lon_max, 'satellite')
        download_google_map(lat_min, lat_max, lon_min, lon_max, 'terrain')

    return combined_data

if __name__ == "__main__":
    UNIFI_URL = os.getenv("UNIFI_URL")
    UNIFI_KEY = os.getenv("UNIFI_KEY")
    UNIFI_SITE = os.getenv("UNIFI_SITE", "default")
    UISP_URL = os.getenv("UISP_URL")
    UISP_KEY = os.getenv("UISP_KEY")
    GET_MAP = os.getenv("GET_MAP", "False").lower() == "true"

    unifi_devices = []
    if UNIFI_URL and UNIFI_KEY:
        unifi_collector = UniFiCollector(UNIFI_URL, UNIFI_KEY, site=UNIFI_SITE)
        unifi_devices = unifi_collector.get_devices()

    uisp_devices = []
    uisp_sites = []
    if UISP_URL and UISP_KEY:
        uisp_collector = UISPCollector(UISP_URL, UISP_KEY)
        uisp_devices = uisp_collector.get_devices()
        uisp_sites = uisp_collector.get_sites()

    final_data = format_data_for_touchdesigner(unifi_devices, uisp_devices, uisp_sites, get_map=GET_MAP)
    with open('network_data.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)

    print(f"\n--- Final Results ---")
    print(f"UniFi: {len(unifi_devices)} devices")
    print(f"UISP: {len(uisp_devices)} devices")
    if GET_MAP:
        print("Google Maps generation enabled. Check map_*.png files.")
    print("Data saved to network_data.json")
