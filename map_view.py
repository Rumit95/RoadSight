"""Builds the 3D map with pydeck (deck.gl, open source) on a free OpenStreetMap-based basemap."""
import math

import pandas as pd
import pydeck as pdk

import config
from gps import distance_m, move_point

VEHICLE_COLOR = [0, 170, 80]
ROUTE_COLOR = [30, 100, 255, 200]
MARKER_OUTLINE_COLOR = [255, 255, 255]
LABEL_COLOR = [30, 30, 30]
LABEL_BACKGROUND = [255, 255, 255, 225]
METERS_PER_PIXEL_AT_ZOOM_0 = 78271.5  # at the equator, for the 512 pixel tiles that deck.gl uses
OVERVIEW_PIXELS = 400  # the whole route is fitted into about this many pixels


def build_map(route, markers, vehicle, heading, follow_vehicle):
    # route: table with latitude and longitude. markers: list of dicts.
    # vehicle: (latitude, longitude) or None. heading: direction of travel in degrees, or None.
    # With follow_vehicle the camera sits behind the vehicle and looks along its direction of travel.
    # Otherwise the whole route is shown from above at an angle.
    third_person = vehicle is not None and follow_vehicle
    if heading is None:
        heading = 0

    if third_person:
        view = third_person_view(vehicle, heading)
    else:
        view = overview_view(route)
    meters_per_pixel = METERS_PER_PIXEL_AT_ZOOM_0 * math.cos(math.radians(view.latitude)) / 2**view.zoom

    layers = [route_layer(route)]
    if len(markers) > 0:
        table = marker_table(markers)
        layers.append(marker_layer(table))
        layers.append(label_layer(table))
    if third_person:
        layers.append(car_layer(vehicle, heading, meters_per_pixel))
    elif vehicle is not None:
        layers.append(dot_layer(vehicle))

    return pdk.Deck(layers=layers, initial_view_state=view, map_provider="carto", map_style="light")


def third_person_view(vehicle, heading):
    # The camera looks at a point ahead of the vehicle, with the map turned so that "up" is the direction of travel.
    latitude, longitude = move_point(vehicle[0], vehicle[1], heading, config.CAMERA_AHEAD_M)
    return pdk.ViewState(
        latitude=latitude,
        longitude=longitude,
        zoom=config.CAMERA_ZOOM,
        pitch=config.CAMERA_PITCH,
        bearing=heading,
    )


def overview_view(route):
    low, high = float(route["latitude"].min()), float(route["latitude"].max())
    left, right = float(route["longitude"].min()), float(route["longitude"].max())
    latitude, longitude = (low + high) / 2, (left + right) / 2

    size_m = max(distance_m(low, longitude, high, longitude), distance_m(latitude, left, latitude, right), 1)
    zoom = math.log2(METERS_PER_PIXEL_AT_ZOOM_0 * math.cos(math.radians(latitude)) * OVERVIEW_PIXELS / size_m)
    zoom = max(8, min(zoom - 0.5, 18))  # a little room around the route, and never closer than street level
    return pdk.ViewState(latitude=latitude, longitude=longitude, zoom=zoom, pitch=config.OVERVIEW_PITCH, bearing=0)


def route_layer(route):
    # The width is clamped to the same number of pixels at every zoom level, so the line stays thin.
    path = [[row.longitude, row.latitude] for row in route.itertuples()]
    return pdk.Layer(
        "PathLayer",
        data=[{"path": path}],
        get_path="path",
        get_color=ROUTE_COLOR,
        get_width=0.1,
        width_min_pixels=config.ROUTE_WIDTH_PX,
        width_max_pixels=config.ROUTE_WIDTH_PX,
    )


def marker_table(markers):
    # Keep the main map labels short; full model details are shown in the results table.
    table = pd.DataFrame(markers)[["class_name", "map_latitude", "map_longitude"]].copy()
    table["color"] = [config.CLASS_COLORS.get(name, config.OTHER_COLOR) for name in table["class_name"]]
    table["map_label"] = table["class_name"].str.replace("_", " ", regex=False)
    return table


def marker_layer(table):
    # A flat circle on the road at the place where damage was found. Its color shows the kind of damage.
    # The radius is clamped to the same number of pixels at every zoom level.
    return pdk.Layer(
        "ScatterplotLayer",
        data=table,
        get_position=["map_longitude", "map_latitude"],
        get_fill_color="color",
        get_radius=1,
        radius_min_pixels=config.MARKER_RADIUS_PX,
        radius_max_pixels=config.MARKER_RADIUS_PX,
        stroked=True,
        get_line_color=MARKER_OUTLINE_COLOR,
        get_line_width=0.1,
        line_width_min_pixels=2,
        line_width_max_pixels=2,
    )


def label_layer(table):
    # Show only the hazard type beside each circle; model details stay in the results section.
    return pdk.Layer(
        "TextLayer",
        data=table,
        get_position=["map_longitude", "map_latitude"],
        get_text="map_label",
        get_size=config.LABEL_SIZE_PX,
        get_color=LABEL_COLOR,
        get_pixel_offset=[0, -(config.MARKER_RADIUS_PX + 6)],
        get_text_anchor="'middle'",
        get_alignment_baseline="'bottom'",
        character_set="'auto'",
        background=True,
        get_background_color=LABEL_BACKGROUND,
        background_padding=[4, 2],
    )


def car_layer(vehicle, heading, meters_per_pixel):
    # A small box pointing in the direction of travel.
    latitude, longitude = vehicle
    half_length = config.CAR_LENGTH_PX * meters_per_pixel / 2
    half_width = config.CAR_WIDTH_PX * meters_per_pixel / 2
    corners = []
    for forward, side in [(1, 1), (1, -1), (-1, -1), (-1, 1)]:
        corner_latitude, corner_longitude = move_point(latitude, longitude, heading, forward * half_length)
        corner_latitude, corner_longitude = move_point(corner_latitude, corner_longitude, heading + 90, side * half_width)
        corners.append([corner_longitude, corner_latitude])
    return pdk.Layer(
        "PolygonLayer",
        data=[{"polygon": corners}],
        get_polygon="polygon",
        get_fill_color=VEHICLE_COLOR,
        get_elevation=config.CAR_HEIGHT_PX * meters_per_pixel,
        extruded=True,
    )


def dot_layer(vehicle):
    latitude, longitude = vehicle
    data = [{"longitude": longitude, "latitude": latitude}]
    return pdk.Layer(
        "ScatterplotLayer",
        data=data,
        get_position=["longitude", "latitude"],
        get_fill_color=VEHICLE_COLOR,
        get_radius=1,
        radius_min_pixels=config.DOT_RADIUS_PX,
        radius_max_pixels=config.DOT_RADIUS_PX,
    )
