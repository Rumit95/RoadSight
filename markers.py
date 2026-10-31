"""Keeps the list of damage markers that are drawn on the map."""
import config
from gps import distance_m


def add_markers(markers, detections, frame_number, time_s, position, map_position):
    # position is the recorded GPS (latitude, longitude). map_position is where the vehicle is drawn on the map.
    # Adds one marker per detection at the vehicle, unless the same kind of damage already has a marker
    # nearby. Returns how many markers were added.
    added = 0
    for detection in detections:
        if has_marker_nearby(markers, detection["class_name"], map_position):
            continue
        markers.append(
            {
                "frame": frame_number,
                "time_s": round(time_s, 2),
                "class_name": detection["class_name"],
                "confidence": round(detection["confidence"], 2),
                "label": detection.get("label", detection["class_name"]),
                "info": detection.get("info", {}),
                "latitude": position[0],
                "longitude": position[1],
                "map_latitude": map_position[0],
                "map_longitude": map_position[1],
            }
        )
        added = added + 1
    return added


def has_marker_nearby(markers, class_name, map_position):
    for marker in markers:
        if marker["class_name"] != class_name:
            continue
        distance = distance_m(marker["map_latitude"], marker["map_longitude"], map_position[0], map_position[1])
        if distance < config.MIN_MARKER_DISTANCE_M:
            return True
    return False
