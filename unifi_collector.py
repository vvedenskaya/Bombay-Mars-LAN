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

def calculate_zoom_level(lat_min, lat_max, lon_min, lon_max, grid_size, tile_size_pixels=1280):
    """
    Calculate the zoom level that ensures tiles cover exactly the right area without overlap.
    Each tile is 1280x1280 pixels (640x640 at scale 2).
    Accounts for Mercator projection where latitude coverage varies.
    """
    lat_range = lat_max - lat_min
    lon_range = lon_max - lon_min
    center_lat = (lat_min + lat_max) / 2
    
    # Target coverage per tile in degrees
    target_lat_per_tile = lat_range / grid_size
    target_lon_per_tile = lon_range / grid_size
    
    # For Google Maps Static API with Web Mercator projection:
    # At zoom z, longitude degrees per pixel = 360 / (256 * 2^z)
    # Latitude degrees per pixel = (360 / (256 * 2^z)) / cos(latitude)
    # But for small areas, we can approximate
    
    # Calculate required zoom for longitude (more straightforward)
    # lon_degrees_per_pixel = 360 / (256 * 2^z)
    # Solving: 2^z = 360 / (256 * lon_degrees_per_pixel)
    # z = log2(360 / (256 * lon_degrees_per_pixel))
    lon_degrees_per_pixel = target_lon_per_tile / tile_size_pixels
    zoom_lon = math.log2(360 / (256 * lon_degrees_per_pixel))
    
    # For latitude, account for Mercator projection
    # lat_degrees_per_pixel ≈ (360 / (256 * 2^z)) / cos(lat)
    lat_degrees_per_pixel = target_lat_per_tile / tile_size_pixels
    zoom_lat = math.log2(360 / (256 * lat_degrees_per_pixel * math.cos(math.radians(center_lat))))
    
    # Use the more restrictive zoom (higher number = more zoomed in)
    zoom = min(zoom_lon, zoom_lat)
    
    # Clamp to valid zoom range (0-21 for Google Maps)
    zoom = max(0, min(21, int(zoom)))
    
    return zoom

def download_google_map(lat_min, lat_max, lon_min, lon_max, map_type='roadmap', grid_size=4):
    """
    Downloads static map images in a grid with no overlap for perfect stitching.
    Uses consistent zoom level and precise tile centers.
    """
    api_key = os.getenv("GOOGLE_MAPS_KEY")
    if not api_key:
        print(f"Skipping {map_type}: GOOGLE_MAPS_KEY not found")
        return None

    # Calculate zoom level for perfect tile alignment
    zoom = calculate_zoom_level(lat_min, lat_max, lon_min, lon_max, grid_size)
    
    # Calculate exact tile boundaries (no overlap)
    lat_step = (lat_max - lat_min) / grid_size
    lon_step = (lon_max - lon_min) / grid_size

    print(f"Downloading {grid_size}x{grid_size} grid for {map_type} (zoom={zoom})...")

    for row in range(grid_size):
        for col in range(grid_size):
            # Calculate exact tile boundaries
            t_lat_min = lat_min + row * lat_step
            t_lat_max = lat_min + (row + 1) * lat_step
            t_lon_min = lon_min + col * lon_step
            t_lon_max = lon_min + (col + 1) * lon_step
            
            # Center of this tile
            center_lat = (t_lat_min + t_lat_max) / 2
            center_lon = (t_lon_min + t_lon_max) / 2
            
            # Use zoom + center instead of visible for precise control
            # Size: 640x640 at scale 2 = 1280x1280 pixels per tile
            params = {
                "center": f"{center_lat},{center_lon}",
                "zoom": str(zoom),
                "size": "640x640",
                "scale": "2",
                "maptype": map_type,
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
    """
    Stitches together all downloaded map tiles for a given map type.
    Tiles are arranged in a grid: row 0 col 0 is top-left, row increases downward, col increases rightward.
    """
    print(f"\nStitching {map_type} tiles...")
    
    # Find all tiles for this map type
    tiles = []
    for row in range(grid_size):
        for col in range(grid_size):
            filename = f"map_{map_type}_{row}_{col}.png"
            if os.path.exists(filename):
                tiles.append((row, col, filename))
            else:
                print(f"  ⚠ Warning: {filename} not found, skipping stitch")
                return None
    
    if not tiles:
        print(f"  ✗ No tiles found for {map_type}")
        return None
    
    # Load first tile to get dimensions
    first_tile = Image.open(tiles[0][2])
    tile_width, tile_height = first_tile.size
    
    # Create the stitched canvas
    canvas_width = tile_width * grid_size
    canvas_height = tile_height * grid_size
    stitched = Image.new('RGB', (canvas_width, canvas_height))
    
    # Paste each tile in the correct position
    # Note: row 0 = lowest latitude (south) = bottom of image
    #       row (grid_size-1) = highest latitude (north) = top of image
    #       col 0 = lowest longitude (west) = left of image
    #       col (grid_size-1) = highest longitude (east) = right of image
    for row, col, filename in tiles:
        tile = Image.open(filename)
        x_offset = col * tile_width
        # Flip rows: row 0 (south) goes to bottom, row max (north) goes to top
        y_offset = (grid_size - 1 - row) * tile_height
        stitched.paste(tile, (x_offset, y_offset))
        tile.close()
    
    # Save the stitched image
    output_filename = f"map_{map_type}_stitched.png"
    stitched.save(output_filename)
    print(f"  ✓ Stitched {len(tiles)} tiles into {output_filename} ({canvas_width}x{canvas_height} pixels)")
    
    return output_filename

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

        # Use same grid size for both map types for consistent stitching
        grid_size = 4  # 4x4 = 16 tiles per map type
        
        combined_data["map_metadata"] = {
            "lat_min": lat_min, "lat_max": lat_max,
            "lon_min": lon_min, "lon_max": lon_max,
            "grid": f"{grid_size}x{grid_size}"
        }
        
        # Download both roadmap and satellite with same grid size for perfect stitching
        download_google_map(lat_min, lat_max, lon_min, lon_max, 'satellite', grid_size=grid_size)
        download_google_map(lat_min, lat_max, lon_min, lon_max, 'roadmap', grid_size=grid_size)
        
        # Automatically stitch the downloaded tiles
        stitch_maps('satellite', grid_size)
        stitch_maps('roadmap', grid_size)

    return combined_data

def export_to_tsv(data, filename='network_data.tsv'):
    """
    Exports network data to a TSV file with columns: name, model, type, state, lat, lon
    Combines both unifi and uisp devices.
    """
    import csv
    
    # Combine all devices from both sources
    all_devices = []
    
    # Add UISP devices
    if isinstance(data.get('uisp'), list):
        for device in data['uisp']:
            all_devices.append({
                'name': device.get('name', ''),
                'model': device.get('model', ''),
                'type': device.get('type', ''),
                'state': device.get('state', ''),
                'lat': device.get('lat', ''),
                'lon': device.get('lon', '')
            })
    
    # Add UniFi devices
    if isinstance(data.get('unifi'), list):
        for device in data['unifi']:
            all_devices.append({
                'name': device.get('name', ''),
                'model': device.get('model', ''),
                'type': device.get('type', ''),
                'state': device.get('state', ''),
                'lat': device.get('lat', ''),
                'lon': device.get('lon', '')
            })
    
    # Write to TSV file
    if all_devices:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['name', 'model', 'type', 'state', 'lat', 'lon']
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
            writer.writeheader()
            writer.writerows(all_devices)
        print(f"  ✓ Exported {len(all_devices)} devices to {filename}")
        return filename
    else:
        print(f"  ⚠ No devices found to export to TSV")
        return None

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
    
    # Export to TSV
    export_to_tsv(final_data)

    print(f"\n--- ULTRA HIGH-RES RESULTS ---")
    print(f"UniFi: {len(unifi_devices)} | UISP: {len(final_data['uisp'])}")
    if GET_MAP: 
        grid_size = final_data.get('map_metadata', {}).get('grid', '4x4')
        print(f"{grid_size} grid downloaded and automatically stitched for both roadmap and satellite!")
        print(f"  → Individual tiles: map_{{type}}_{{row}}_{{col}}.png")
        print(f"  → Stitched images: map_satellite_stitched.png, map_roadmap_stitched.png")
