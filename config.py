"""Settings for the road damage app, all in one place."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

# Place the model checkpoint in roadsight_app\models\road_damage.pt.
WEIGHTS = os.path.join(ROOT, "models", "road_damage.pt")
IMAGE_SIZE = 640

# Demo videos: demo\NAME.mp4 with the GPS positions of its frames in demo\NAME.csv.
DEMO_DIR = os.path.join(ROOT, "demo")

DEFAULT_CONFIDENCE = 0.10
DEFAULT_FRAME_STEP = 2  # run the model on every 2nd frame

DISPLAY_WIDTH = 800  # width in pixels of the picture sent to the page
MAP_UPDATE_EVERY = 1  # redraw the map every this many processed frames
MAP_HEIGHT = 450

# Third-person camera behind the vehicle, looking along the direction of travel.
CAMERA_ZOOM = 19
CAMERA_PITCH = 60  # degrees from looking straight down; the street background disappears above 60
CAMERA_AHEAD_M = 20  # the camera looks at a point this far ahead, so the vehicle sits low on the screen

# Overview of the whole route (used when the third-person camera is switched off, and after the video).
OVERVIEW_PITCH = 50

# Sizes are given in screen pixels so they look the same at every zoom level.
MARKER_RADIUS_PX = 7  # the circle drawn where damage was found
LABEL_SIZE_PX = 13  # the text next to each circle
CAR_LENGTH_PX = 24
CAR_WIDTH_PX = 11
CAR_HEIGHT_PX = 6
DOT_RADIUS_PX = 5  # the vehicle as seen in the overview of the route
ROUTE_WIDTH_PX = 2  # the thin line of the route

# Snapping the GPS track onto the roads of OpenStreetMap, so the car is drawn on the road.
CACHE_DIR = os.path.join(ROOT, "cache")  # downloaded roads are kept here, delete it to refresh them
SNAP_MAX_M = 20  # a GPS point farther than this from every road stays where it is

# A marker is skipped if the same kind of damage already has a marker closer than this.
MIN_MARKER_DISTANCE_M = 8

# Simulated route used when no GPS file is given: a straight stretch of HITEC City Road in Hyderabad, India.
DEFAULT_START_LAT = 17.44336
DEFAULT_START_LON = 78.37721
DEFAULT_HEADING = 179  # degrees: 0 is north, 90 is east
DEFAULT_SPEED_KMH = 30

# Marker colors (red, green, blue) by class name. The legend in app.py uses the same colors.
# A class that is not listed here, for example from another model, gets the same red as a pothole.
CLASS_COLORS = {
    "pothole": [220, 30, 30],
    "alligator_crack": [255, 140, 0],
    "longitudinal_crack": [150, 60, 200],
    "transverse_crack": [30, 120, 255],
}
OTHER_COLOR = [220, 30, 30]
