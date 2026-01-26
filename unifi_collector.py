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
            except: continue
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
            response = self.session.get(url, verify=False, timeout=15)
            if response.status_code == 200: return response.json()
            return []
        except: return []

    def get_sites(self):
        url = f"{self.base_url}/nms/api/v2.1/sites"
        try:
            response = self.session.get(url, verify=False, timeout=15)
            if response.status_code == 200: return response.json()
            return []
        except: return []

def download_google_map(lat_min, lat_max, lon_min, lon_max, map_type='roadmap', grid_size=4):
    """Downloads static map images in a grid (e.g., 4x4)."""
    api_key = os.getenv("GOOGLE_MAPS_KEY")
    if not api_key:
        print(f"Skipping {map_type}: GOOGLE_MAPS_KEY not found")
        return None

    lat_step = (lat_max - lat_min) / grid_size
    lon_step = (lon_max - lon_min) / grid_size

    print(f"Downloading {grid_size}x{grid_size} grid for {map_type}...")

    for row in range(grid_size):
        for col in range(grid_size):
            t_lat_max = lat_max - row * lat_step
            t_lat_min = lat_max - (row + 1) * lat_step
            t_lon_min = lon_min + col * lon_step
            t_lon_max = lon_min + (col + 1) * lon_step
            
            center_lat = (t_lat_min + t_lat_max) / 2
            center_lon = (t_lon_min + t_lon_max) / 2
            
            params = {
                "center": f"{center_lat},{center_lon}",
                "size": "640x640",
                "scale": "2",
                "maptype": map_type,
                "visible": f"{t_lat_min},{t_lon_min}|{t_lat_max},{t_lon_max}",
                "key": api_key
            }

            try:
                filename = f"map_{map_type}_{row}_{col}.png"
                response = requests.get("https://maps.googleapis.com/maps/api/staticmap", params=params, timeout=20)
                if response.status_code == 200:
                    with open(filename, 'wb') as f:
                        f.write(response.content)
                else:
                    print(f"  Error {response.status_code} for {filename}")
            except Exception as e:
                print(f"  Error downloading {filename}: {e}")

def format_data_for_touchdesigner(unifi_devs, uisp_devs, uisp_sites, get_map=False):
    combined_data = {"unifi": [], "uisp": [], "map_metadata": {}}
    
    site_map = {}
    if isinstance(uisp_sites, list):
        for site in uisp_sites:
            s_id = site.get('id')
            loc = site.get('location') or {}
            if s_id: site_map[s_id] = {'lat': loc.get('latitude'), 'lon': loc.get('longitude')}

    lats, lons = [], []
    temp_uisp = []
    if isinstance(uisp_devs, list):
        for dev in uisp_devs:
            id_info = dev.get('identification') or {}
            attr = dev.get('attributes') or {}
            loc = dev.get('location') or {}
            s_id = id_info.get('siteId')
            site_coords = site_map.get(s_id, {})
            lat = attr.get('latitude') or loc.get('latitude') or site_coords.get('lat')
            lon = attr.get('longitude') or loc.get('longitude') or site_coords.get('lon')
            if lat and lon:
                lat, lon = float(lat), float(lon)
                if abs(lat) > 0.1: temp_uisp.append((lat, lon, dev))

    if temp_uisp:
        all_lats = sorted([x[0] for x in temp_uisp])
        all_lons = sorted([x[1] for x in temp_uisp])
        med_lat, med_lon = all_lats[len(all_lats)//2], all_lons[len(all_lons)//2]

        # BALANCED FILTER: ~3km from center
        for lat, lon, dev in temp_uisp:
            if abs(lat - med_lat) < 0.03 and abs(lon - med_lon) < 0.03:
                lats.append(lat); lons.append(lon)
                id_info = dev.get('identification') or {}
                combined_data["uisp"].append({
                    'name': id_info.get('name'),
                    'model': id_info.get('model'),
                    'type': id_info.get('type'),
                    'state': dev.get('overview', {}).get('status'),
                    'lat': lat, 'lon': lon
                })

    if get_map and lats and lons:
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        
        # 5% padding
        lat_pad = (lat_max - lat_min) * 0.05 or 0.0005
        lon_pad = (lon_max - lon_min) * 0.05 or 0.0005
        lat_min -= lat_pad; lat_max += lat_pad
        lon_min -= lon_pad; lon_max += lon_pad

        combined_data["map_metadata"] = {
            "lat_min": lat_min, "lat_max": lat_max,
            "lon_min": lon_min, "lon_max": lon_max,
            "grid": "4x4"
        }
        
        # Download ULTRA-HIGH RES (4x4 grid)
        # Note: roadmap and terrain might not need 4x4, but satellite definitely does
        download_google_map(lat_min, lat_max, lon_min, lon_max, 'satellite', grid_size=4)
        download_google_map(lat_min, lat_max, lon_min, lon_max, 'roadmap', grid_size=2) # 2x2 is enough for maps

    return combined_data

if __name__ == "__main__":
    UNIFI_URL, UNIFI_KEY = os.getenv("UNIFI_URL"), os.getenv("UNIFI_KEY")
    UNIFI_SITE = os.getenv("UNIFI_SITE", "default")
    UISP_URL, UISP_KEY = os.getenv("UISP_URL"), os.getenv("UISP_KEY")
    GET_MAP = os.getenv("GET_MAP", "False").lower() == "true"

    unifi_devices = []
    if UNIFI_URL and UNIFI_KEY:
        unifi_devices = UniFiCollector(UNIFI_URL, UNIFI_KEY, site=UNIFI_SITE).get_devices()

    uisp_devices, uisp_sites = [], []
    if UISP_URL and UISP_KEY:
        uisp_coll = UISPCollector(UISP_URL, UISP_KEY)
        uisp_devices = uisp_coll.get_devices()
        uisp_sites = uisp_coll.get_sites()

    final_data = format_data_for_touchdesigner(unifi_devices, uisp_devices, uisp_sites, get_map=GET_MAP)
    with open('network_data.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)

    print(f"\n--- ULTRA HIGH-RES RESULTS ---")
    print(f"UniFi: {len(unifi_devices)} | UISP: {len(final_data['uisp'])}")
    if GET_MAP: print("4x4 Satellite grid downloaded (16 files). Check your folder!")
