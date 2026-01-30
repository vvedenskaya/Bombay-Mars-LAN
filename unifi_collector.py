import requests
import json
import urllib3
import os
import math
from dotenv import load_dotenv
from PIL import Image

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

    def get_datalinks(self):
        url = f"{self.base_url}/nms/api/v2.1/data-links?siteLinksOnly=true"
        try:
            print(f"Requesting UISP data-links from: {url}")
            response = self.session.get(url, verify=False, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    print(f"DEBUG: First UISP link structure keys: {data[0].keys()}")
                return data
            print(f"UISP Link Error: {response.status_code}")
            return []
        except Exception as e:
            print(f"Error requesting UISP data-links: {e}")
            return []

def calculate_zoom_level(lat_min, lat_max, lon_min, lon_max, grid_size, tile_size_pixels=1280):
    """Calculate the zoom level for perfect tile alignment."""
    lat_range = lat_max - lat_min
    lon_range = lon_max - lon_min
    center_lat = (lat_min + lat_max) / 2
    target_lat_per_tile = lat_range / grid_size
    target_lon_per_tile = lon_range / grid_size
    
    lon_degrees_per_pixel = target_lon_per_tile / tile_size_pixels
    zoom_lon = math.log2(360 / (256 * lon_degrees_per_pixel))
    
    lat_degrees_per_pixel = target_lat_per_tile / tile_size_pixels
    zoom_lat = math.log2(360 / (256 * lat_degrees_per_pixel * math.cos(math.radians(center_lat))))
    
    zoom = min(zoom_lon, zoom_lat)
    return max(0, min(21, int(zoom)))

def download_google_map(lat_min, lat_max, lon_min, lon_max, map_type='roadmap', grid_size=4):
    """Downloads static map images in a grid with no overlap."""
    api_key = os.getenv("GOOGLE_MAPS_KEY")
    if not api_key:
        print(f"Skipping {map_type}: GOOGLE_MAPS_KEY not found")
        return None

    zoom = calculate_zoom_level(lat_min, lat_max, lon_min, lon_max, grid_size)
    lat_step = (lat_max - lat_min) / grid_size
    lon_step = (lon_max - lon_min) / grid_size

    print(f"Downloading {grid_size}x{grid_size} grid for {map_type} (zoom={zoom})...")

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
                "zoom": str(zoom),
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
                    print(f"  ✓ {filename}")
                else:
                    print(f"  ✗ Error {response.status_code} for {filename}")
            except Exception as e:
                print(f"  ✗ Error downloading {filename}: {e}")

def stitch_maps(map_type, grid_size):
    """Stitches together map tiles into one image."""
    print(f"\nStitching {map_type} tiles...")
    tiles = []
    for row in range(grid_size):
        for col in range(grid_size):
            filename = f"map_{map_type}_{row}_{col}.png"
            if os.path.exists(filename):
                tiles.append((row, col, filename))
            else:
                return None
    
    first_tile = Image.open(tiles[0][2])
    tile_width, tile_height = first_tile.size
    stitched = Image.new('RGB', (tile_width * grid_size, tile_height * grid_size))
    
    for row, col, filename in tiles:
        tile = Image.open(filename)
        stitched.paste(tile, (col * tile_width, row * tile_height))
        tile.close()
    
    output_filename = f"map_{map_type}_stitched.png"
    stitched.save(output_filename)
    print(f"  ✓ Stitched into {output_filename}")
    return output_filename

def format_data_for_touchdesigner(unifi_devs, uisp_devs, uisp_sites, uisp_links, get_map=False):
    combined_data = {"unifi": [], "uisp": [], "links": [], "map_metadata": {}}
    
    site_map = {}
    if isinstance(uisp_sites, list):
        for site in uisp_sites:
            s_id = site.get('id')
            loc = site.get('location') or {}
            if s_id: site_map[s_id] = {'lat': loc.get('latitude'), 'lon': loc.get('longitude')}

    if isinstance(unifi_devs, list):
        for dev in unifi_devs:
            mac = dev.get('mac')
            uplink_mac = dev.get('uplink_mac') or dev.get('uplink', {}).get('uplink_mac')
            combined_data["unifi"].append({
                'id': mac, 'name': dev.get('name', mac), 'type': dev.get('type'),
                'model': dev.get('model'), 'state': dev.get('state', 'online'), 
                'clients': dev.get('num_sta', 0), 'x': dev.get('x'), 'y': dev.get('y')
            })
            if uplink_mac:
                combined_data["links"].append({"from": uplink_mac, "to": mac, "type": "wired_unifi"})

    lats, lons = [], []
    temp_uisp = []
    if isinstance(uisp_devs, list):
        for dev in uisp_devs:
            id_info = dev.get('identification') or {}
            attr = dev.get('attributes') or {}
            loc = dev.get('location') or {}
            s_id = id_info.get('siteId')
            d_id = id_info.get('id')
            site_coords = site_map.get(s_id, {})
            lat = attr.get('latitude') or loc.get('latitude') or site_coords.get('lat')
            lon = attr.get('longitude') or loc.get('longitude') or site_coords.get('lon')
            if lat and lon:
                lat, lon = float(lat), float(lon)
                if abs(lat) > 0.1: temp_uisp.append((lat, lon, d_id, dev))

    if temp_uisp:
        all_lats = sorted([x[0] for x in temp_uisp])
        all_lons = sorted([x[1] for x in temp_uisp])
        med_lat, med_lon = all_lats[len(all_lats)//2], all_lons[len(all_lons)//2]
        for lat, lon, d_id, dev in temp_uisp:
            if abs(lat - med_lat) < 0.03 and abs(lon - med_lon) < 0.03:
                lats.append(lat); lons.append(lon)
                id_info = dev.get('identification') or {}
                combined_data["uisp"].append({
                    'id': d_id, 'name': id_info.get('name'), 'model': id_info.get('model'),
                    'type': id_info.get('type'), 'state': dev.get('overview', {}).get('status'),
                    'lat': lat, 'lon': lon
                })

    if isinstance(uisp_links, list):
        for link in uisp_links:
            from_data = link.get('from') or {}
            to_data = link.get('to') or {}
            from_dev_ident = (from_data.get('device') or {}).get('identification') or {}
            from_site_ident = (from_data.get('site') or {}).get('identification') or {}
            to_dev_ident = (to_data.get('device') or {}).get('identification') or {}
            to_site_ident = (to_data.get('site') or {}).get('identification') or {}
            side_a = from_dev_ident.get('id') or from_site_ident.get('id') or link.get('deviceIdA') or link.get('siteIdA')
            side_b = to_dev_ident.get('id') or to_site_ident.get('id') or link.get('deviceIdB') or link.get('siteIdB')
            if side_a and side_b:
                signal = link.get('signal') or (from_data.get('device') or {}).get('overview', {}).get('signal')
                combined_data["links"].append({
                    "from": side_a, "to": side_b, "type": link.get('type', 'wireless_uisp'),
                    "state": link.get('state', 'active'), "signal": signal
                })

    if get_map and lats and lons:
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        lat_pad = (lat_max - lat_min) * 0.1 or 0.001
        lon_pad = (lon_max - lon_min) * 0.1 or 0.001
        lat_min -= lat_pad; lat_max += lat_pad
        lon_min -= lon_pad; lon_max += lon_pad
        grid_size = 4
        combined_data["map_metadata"] = {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max, "grid": f"{grid_size}x{grid_size}"}
        download_google_map(lat_min, lat_max, lon_min, lon_max, 'satellite', grid_size=grid_size)
        download_google_map(lat_min, lat_max, lon_min, lon_max, 'roadmap', grid_size=grid_size)
        stitch_maps('satellite', grid_size)
        stitch_maps('roadmap', grid_size)

    return combined_data

def export_to_tsv(data, filename='network_data.tsv'):
    import csv
    all_devices = []
    for source in ['uisp', 'unifi']:
        if isinstance(data.get(source), list):
            for device in data[source]:
                all_devices.append({
                    'name': device.get('name', ''), 'model': device.get('model', ''),
                    'type': device.get('type', ''), 'state': device.get('state', ''),
                    'lat': device.get('lat', ''), 'lon': device.get('lon', '')
                })
    if all_devices:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'model', 'type', 'state', 'lat', 'lon'], delimiter='\t')
            writer.writeheader()
            writer.writerows(all_devices)
        print(f"  ✓ Exported {len(all_devices)} devices to {filename}")

if __name__ == "__main__":
    UNIFI_URL, UNIFI_KEY = os.getenv("UNIFI_URL"), os.getenv("UNIFI_KEY")
    UNIFI_SITE = os.getenv("UNIFI_SITE", "default")
    UISP_URL, UISP_KEY = os.getenv("UISP_URL"), os.getenv("UISP_KEY")
    GET_MAP = os.getenv("GET_MAP", "False").lower() == "true"

    unifi_devices = UniFiCollector(UNIFI_URL, UNIFI_KEY, site=UNIFI_SITE).get_devices() if UNIFI_URL else []
    uisp_devices, uisp_sites, uisp_links = [], [], []
    if UISP_URL and UISP_KEY:
        uisp_coll = UISPCollector(UISP_URL, UISP_KEY)
        uisp_devices = uisp_coll.get_devices()
        uisp_sites = uisp_coll.get_sites()
        uisp_links = uisp_coll.get_datalinks()

    final_data = format_data_for_touchdesigner(unifi_devices, uisp_devices, uisp_sites, uisp_links, get_map=GET_MAP)
    with open('network_data.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)
    export_to_tsv(final_data)
    print(f"\n--- Results ---")
    print(f"UniFi: {len(unifi_devices)} | UISP: {len(final_data['uisp'])} | Links: {len(final_data['links'])}")
