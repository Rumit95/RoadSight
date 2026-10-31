"""Snaps a GPS track onto the nearest roads of OpenStreetMap, so the vehicle is drawn on the road.

The roads come from the public Overpass server of OpenStreetMap, the same data the map background
is drawn from. They are saved in the cache folder, so a route is downloaded only once.
"""
import hashlib
import json
import math
import os
import time

import numpy as np
import requests
import urllib3

import config
from gps import METERS_PER_DEGREE_LATITUDE

urllib3.util.connection.HAS_IPV6 = False  # IPv6 connections hang on some corporate networks

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "RoadSight/0.1 (local demo app)", "Accept": "application/json"}
ROAD_TYPES = (
    "motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street"
    "|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link"
)
MAX_QUERY_POINTS = 150  # a long route is described to the server by this many points
SERVER_PATIENCE_S = 60  # give up asking the servers after this long
SAME_DIRECTION = 0.77  # a road counts as running the same way as the vehicle within about 40 degrees


def snap_to_roads(route):
    # Returns (route with every point moved onto the nearest road, a sentence about it for the page).
    # If the roads cannot be loaded, the original route is returned unchanged.
    try:
        roads = load_roads(route)
    except RuntimeError as error:
        return route, f"The roads could not be loaded ({error}), so the track is drawn as recorded."
    if len(roads) == 0:
        return route, "No road was found near the GPS track, so it is drawn as recorded."

    snapped, shifts = snap_points(route, roads)
    moved = shifts[shifts > 0.05]
    if len(moved) == 0:
        return route, f"No GPS point was within {config.SNAP_MAX_M} m of a road, so the track is drawn as recorded."
    note = (
        f"On the map the track is snapped to the nearest road: {len(moved)} of {len(route)} points moved, "
        f"{moved.mean():.1f} m on average and {moved.max():.1f} m at most."
    )
    return snapped, note


def load_roads(route):
    # Returns a list of roads, each a list of (latitude, longitude) points.
    points = sample_points(route)
    key = hashlib.md5(json.dumps(points).encode()).hexdigest()[:16]
    cache_path = os.path.join(config.CACHE_DIR, f"roads_{key}.json")
    if os.path.exists(cache_path):
        with open(cache_path) as cache_file:
            return json.load(cache_file)

    roads = download_roads(points)
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(cache_path, "w") as cache_file:
        json.dump(roads, cache_file)
    return roads


def sample_points(route):
    count = min(len(route), MAX_QUERY_POINTS)
    rows = np.linspace(0, len(route) - 1, count).astype(int)
    return [[round(float(route["latitude"].iloc[row]), 5), round(float(route["longitude"].iloc[row]), 5)] for row in rows]


def download_roads(points):
    # Asks the Overpass servers for every road within reach of the line through the points.
    coordinates = ",".join(f"{latitude},{longitude}" for latitude, longitude in points)
    reach = config.SNAP_MAX_M + 30
    query = f'[out:json][timeout:25];way["highway"~"^({ROAD_TYPES})$"](around:{reach},{coordinates});out geom;'

    deadline = time.time() + SERVER_PATIENCE_S
    last_error = "no answer"
    for attempt in range(2):
        for url in OVERPASS_URLS:
            if time.time() > deadline:
                raise RuntimeError(last_error)
            try:
                response = requests.post(url, data={"data": query}, headers=HEADERS, timeout=25)
                response.raise_for_status()
                ways = [way for way in response.json()["elements"] if way["type"] == "way"]
                return [[(point["lat"], point["lon"]) for point in way["geometry"]] for way in ways]
            except (requests.RequestException, KeyError, ValueError) as error:
                last_error = f"{type(error).__name__} from {url.split('/')[2]}"
        time.sleep(2)
    raise RuntimeError(last_error)


def snap_points(route, roads):
    # Works in meters east (x) and north (y) of the middle of the route.
    latitude0 = float(route["latitude"].mean())
    longitude0 = float(route["longitude"].mean())
    meters_per_degree_longitude = METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(latitude0))

    def to_xy(latitudes, longitudes):
        x = (np.asarray(longitudes) - longitude0) * meters_per_degree_longitude
        y = (np.asarray(latitudes) - latitude0) * METERS_PER_DEGREE_LATITUDE
        return np.column_stack([x, y])

    starts, ends = [], []
    for road in roads:
        xy = to_xy([p[0] for p in road], [p[1] for p in road])
        starts.append(xy[:-1])
        ends.append(xy[1:])
    starts, ends = np.vstack(starts), np.vstack(ends)

    points = to_xy(route["latitude"].values, route["longitude"].values)
    corrections = np.zeros_like(points)
    for i in range(len(points)):
        # The direction of travel, from the points a little before and after this one.
        direction = points[min(i + 2, len(points) - 1)] - points[max(i - 2, 0)]
        length = np.hypot(*direction)
        direction = direction / length if length >= 1 else None
        corrections[i] = nearest_point_on_roads(points[i], starts, ends, direction) - points[i]

    # Averaging the corrections over about a second keeps the path smooth at junctions, where the nearest
    # road suddenly changes. The track keeps its own shape and is pulled onto the road.
    corrections = moving_average(corrections, points_per_second(route))
    snapped = points + corrections

    result = route.copy()
    result["latitude"] = latitude0 + snapped[:, 1] / METERS_PER_DEGREE_LATITUDE
    result["longitude"] = longitude0 + snapped[:, 0] / meters_per_degree_longitude
    return result, np.hypot(*corrections.T)


def points_per_second(route):
    spacing = float(np.median(np.diff(route["time_s"].values)))
    return max(1, round(1 / spacing)) if spacing > 0 else 1


def moving_average(values, half_window):
    # Average over the points up to half_window before and after each point. Near the ends it uses fewer points.
    half_window = max(0, min(half_window, (len(values) - 1) // 2))
    kernel = np.ones(2 * half_window + 1)
    counts = np.convolve(np.ones(len(values)), kernel, mode="same")
    return np.column_stack([np.convolve(values[:, k], kernel, mode="same") / counts for k in range(values.shape[1])])


def nearest_point_on_roads(point, starts, ends, direction):
    # Returns the closest point on any road segment, or the point itself if no road is close enough.
    segments = ends - starts
    length_squared = np.maximum((segments**2).sum(axis=1), 1e-9)
    along = np.clip(((point - starts) * segments).sum(axis=1) / length_squared, 0, 1)
    closest = starts + along[:, None] * segments
    distance = np.hypot(*(point - closest).T)

    best = int(np.argmin(distance))
    if direction is not None:
        # Prefer roads that run the same way as the vehicle, so it does not jump onto a crossing road.
        same_way = np.abs((segments * direction).sum(axis=1)) / np.sqrt(length_squared) >= SAME_DIRECTION
        if same_way.any() and distance[same_way].min() <= config.SNAP_MAX_M:
            best = int(np.flatnonzero(same_way)[np.argmin(distance[same_way])])

    return closest[best] if distance[best] <= config.SNAP_MAX_M else point
