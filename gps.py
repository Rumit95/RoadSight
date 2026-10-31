"""GPS helpers: read a GPS file, make a simulated route, and find the position and direction at a time."""
import math

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6371000
METERS_PER_DEGREE_LATITUDE = 111320
MIN_MOVE_M = 2  # the vehicle must have moved this far before a direction is trusted
HEADING_SMOOTHING = 0.3  # 1 turns the camera at once, a smaller number turns it more slowly


def load_gps_csv(file, duration_s):
    # Needs the columns latitude and longitude. A time_s column (seconds from the video start) is optional.
    table = pd.read_csv(file)
    table.columns = [name.strip().lower() for name in table.columns]

    for needed in ["latitude", "longitude"]:
        if needed not in table.columns:
            raise ValueError(f"The GPS file needs a '{needed}' column. Columns found: {list(table.columns)}")

    if "time_s" not in table.columns:
        # Without times, the rows are spread evenly over the length of the video.
        table["time_s"] = np.linspace(0, duration_s, len(table))

    try:
        table = table[["time_s", "latitude", "longitude"]].astype(float)
    except ValueError:
        raise ValueError("time_s, latitude and longitude in the GPS file must contain numbers only.")

    table = table.dropna().sort_values("time_s").reset_index(drop=True)
    if len(table) < 2:
        raise ValueError("The GPS file needs at least 2 rows with numbers in them.")
    if table["latitude"].abs().max() > 90 or table["longitude"].abs().max() > 180:
        raise ValueError("Latitude must be between -90 and 90 and longitude between -180 and 180. Are they swapped?")
    return table


def simulate_route(start_latitude, start_longitude, heading_degrees, speed_kmh, duration_s):
    # A straight route at constant speed.
    times = np.arange(0, duration_s + 0.5, 0.5)
    latitudes, longitudes = move_point(start_latitude, start_longitude, heading_degrees, times * speed_kmh / 3.6)
    return pd.DataFrame({"time_s": times, "latitude": latitudes, "longitude": longitudes})


def move_point(latitude, longitude, heading_degrees, meters):
    # Moves a point in a direction (0 north, 90 east). Good enough for distances up to a few kilometers.
    # `meters` can be one number or a numpy array.
    heading = math.radians(heading_degrees)
    north = meters * math.cos(heading)
    east = meters * math.sin(heading)
    new_latitude = latitude + north / METERS_PER_DEGREE_LATITUDE
    new_longitude = longitude + east / (METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(latitude)))
    return new_latitude, new_longitude


def position_at(route, time_s):
    # Returns (latitude, longitude) at the given time, between the two nearest GPS rows.
    latitude = np.interp(time_s, route["time_s"], route["latitude"])
    longitude = np.interp(time_s, route["time_s"], route["longitude"])
    return float(latitude), float(longitude)


def distance_m(latitude1, longitude1, latitude2, longitude2):
    # Distance in meters between two points (haversine formula).
    lat1, lat2 = math.radians(latitude1), math.radians(latitude2)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(longitude2 - longitude1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_degrees(latitude1, longitude1, latitude2, longitude2):
    # Direction from point 1 to point 2 in degrees (0 north, 90 east).
    lat1, lat2 = math.radians(latitude1), math.radians(latitude2)
    delta_lon = math.radians(longitude2 - longitude1)
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return math.degrees(math.atan2(y, x)) % 360


def heading_at(route, time_s):
    # Direction of travel at a time, from the positions a moment before and after it.
    # Returns None while the vehicle has hardly moved, because the direction is not known then.
    for window_s in [1.0, 2.0, 4.0]:
        before = position_at(route, time_s - window_s)
        after = position_at(route, time_s + window_s)
        if distance_m(*before, *after) >= MIN_MOVE_M:
            return bearing_degrees(*before, *after)
    return None


def blend_heading(previous, new):
    # Turns the camera part of the way towards the new heading, so the map does not jerk.
    if new is None:
        return previous
    if previous is None:
        return new
    difference = (new - previous + 180) % 360 - 180  # the short way round, from -180 to 180
    return (previous + HEADING_SMOOTHING * difference) % 360
