# RoadSight - Road Damage Map

## What it does

Upload a video driven along a road. The trained YOLO model finds potholes and cracks frame by frame.
The main screen keeps the drive video and road map side by side, with video and optional GPS upload
fields readily available. The video shows the model detections; the map follows the route and marks
detected damage. Expand "Settings & details" to choose a sample, adjust model/map settings, and see
progress, GPS/model details, and result tables or downloads.
A video file has no GPS inside it, so the positions come from a GPS file you upload, or from a
simulated route.

The app source runs independently of the training project. You need a compatible trained YOLO
checkpoint, but you do not need the training code or dataset to run the app.

## Setup and run

Use Python 3.10 or newer. From a terminal in the `roadsight_app` folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Obtain a compatible model checkpoint separately and place it inside the app folder at:

    roadsight_app\models\road_damage.pt

Create the `models` folder if it does not exist. The app expects the checkpoint file to be named
`road_damage.pt` and stored there; it does not load model files from outside the `roadsight_app`
folder. The app repository does not include model weights, and the training project is not needed
to run it. Obtain a compatible checkpoint from a source whose terms permit your intended use.

If you put the file in the default location, run the app with:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The app opens at http://localhost:8501. Press Ctrl+C in the terminal to stop it. The `.gitignore`
excludes local model files by default.

## Publishing to GitHub

To publish only the app, create/push the Git repository from this `roadsight_app` folder rather
than the parent workspace. This keeps the separate training project and its local environment out
of the app repository. The `.gitignore` excludes local checkpoints, KITTI demo media/GPS, caches,
datasets, and generated training runs.

## Try it without your own drive data

Real driving with a real GPS position for every frame (KITTI, recorded in Karlsruhe, Germany):

```powershell
.\.venv\Scripts\python.exe download_kitti_demo.py
```

This downloads drives 0001 and 0005 and keeps only the left color camera and GPS files. Other drives
of 2011-09-26 work too:

```powershell
.\.venv\Scripts\python.exe download_kitti_demo.py 0002 0011
```

Then tick "Use a demo video instead of uploading one" in the app and pick a drive. KITTI roads are
smooth, so expect few or no potholes. Lower the minimum confidence to see anything.

KITTI Raw is licensed CC BY-NC-SA 3.0. Attribute the dataset and do not publish the downloaded
video/GPS files. They are excluded by this project's `.gitignore`.

## Using the app


1. Upload a video (mp4, avi, mov or mkv, up to 1 GB) using the main-screen upload field. Optionally
   upload a GPS file (CSV) beside it.
2. Expand "Settings & details" to choose a downloaded sample drive or adjust model/map settings.
   Without a GPS file, a simulated straight route is used; set its start point, direction, and speed
   in the same section.
3. Select "Start demo" inside the section. Use its "Stop" button to end early.
   (A demo video always uses its own GPS file, even if you also uploaded one.)
The "Settings & details" section also contains:
  - Minimum confidence: higher shows fewer, more certain detections.
  - Run the model on every Nth frame: higher is faster. For a 30 fps video use 3 to 5 on a CPU.
  - Third-person camera behind the vehicle: the map turns so the road ahead is always up.
    Switch it off to see the whole route from above instead.
  - Snap the GPS track to the nearest road: see SNAPPING TO THE ROAD below.
Progress, frame/GPS information, the map legend, detected-hazard results, frame positions, and CSV
downloads are kept in this section so the video and map remain the focus of the main screen.


## GPS file format

    time_s,latitude,longitude
    0,17.4435,78.3772
    0.5,17.4435,78.3773
    1.0,17.4435,78.3775

time_s is the number of seconds from the start of the video. If the column is missing, the rows are
spread evenly over the length of the video. Other columns are ignored.


## How the markers are placed
A marker is put at the vehicle position of the frame where the damage was seen. The damage itself
is usually a few meters ahead of the vehicle, so treat the position as approximate.
A marker is skipped if the same kind of damage already has a marker within 8 meters, so one pothole
is not drawn dozens of times. Two damages of one kind in the same spot also share one marker.
The circle color and short label show the kind of damage. Confidence, coordinates, and model details
are available in the results under "Settings & details." The car, the route line and the circles have
the same size on the screen at every zoom level. Change the sizes in config.py (MARKER_RADIUS_PX,
CAR_LENGTH_PX, ROUTE_WIDTH_PX and so on).


## The text next to a circle, and using another model
The map shows only the hazard type next to each circle. The confidence and extra facts in the detailed
results come from the model, not from the map code. They are made in one small file, model_adapter.py,
which is the only file that knows what the model returns.
To switch to another model:
  1. Set WEIGHTS in config.py to the new weights.
  2. If the model tells more than a class and a confidence (a depth, a severity, a size, a repair
     advice...), return it from read_detections in model_adapter.py:
      "label"  the short text in the detailed results, for example "depth 4 cm | HIGH"
      "info"   more facts as name -> value, for example {"depth_cm": 4, "severity": "high"}
The map marker color and short label use the detected class. The detailed results include the
model-provided label and facts. A class that is not listed in CLASS_COLORS gets a red circle like a
pothole. The facts in "info" become extra columns of the damage table and its CSV.


## Snapping to the road
A GPS track is often a few meters away from the road. On KITTI drive 0001 it runs 4.2 meters beside
the road line of the map, so the car would drive next to the road instead of on it.
With "Snap the GPS track to the nearest road" switched on (the default), every GPS point is moved onto
the closest road of OpenStreetMap, which is the data the map background is drawn from. The page says
how far the points were moved. Details:
  - The roads are asked from the public Overpass server of OpenStreetMap. Only the area around the
    route is sent. They are saved in the cache folder, so the same route works offline the next time.
    Delete the cache folder to download them again.
  - Roads that run the same way as the vehicle are preferred, and the correction is averaged over
    about a second, so the car does not jump onto a crossing road at a junction.
  - A point more than 20 meters from every road (SNAP_MAX_M) stays where it is.
  - If the server does not answer, the page says so and shows the track as recorded.
  - It is not used for a simulated route.
  - The latitude and longitude in the page and in the tables are always the recorded GPS values.
    The map_latitude and map_longitude columns show where the car and the circles are drawn.
  - Footpaths and service roads are not used, so a car in a car park or on a private road is not
    pulled onto the nearest street.


## Project files
  app.py                The Streamlit page: layout and the loop that updates the boxes.
  detector_worker.py    Runs YOLO on the video in a separate process and prints one line per frame.
  model_adapter.py      Turns the model output into label and details for the map. Change it for a new model.
  detection_stream.py   Starts the worker and hands its results to the page.
  gps.py                Reads the GPS file, makes the simulated route, finds the position and direction at a time.
  road_snap.py          Downloads the roads of OpenStreetMap and moves the GPS track onto them.
  markers.py            Decides which damage gets a marker on the map.
  map_view.py           Builds the 3D map with pydeck: third-person camera, car, route and circles.
  config.py             All settings: model path, colors, camera angle, marker and label size and spacing.
  download_kitti_demo.py  Downloads KITTI drives and makes demo videos with real per-frame GPS.
  .streamlit\config.toml  Upload limit (1 GB) and no usage-statistics prompt.


## Good to know
- YOLO runs in its own process because importing PyTorch inside Streamlit crashed on this PC.
- The map is drawn with deck.gl (open source). Its street background comes from CARTO using
  OpenStreetMap data and needs internet in the browser. No account or key is needed.
  The 3D comes from the tilted view and the extruded car. The buildings on the street background are flat.
- The direction of travel comes from the GPS positions a moment before and after each frame. It needs
  the vehicle to have moved at least 2 meters, so while it stands still the camera keeps its last
  direction. With a GPS that records only once a second, the camera turns in small steps.
- The camera tilt is limited to 60 degrees. Above that the street background disappears.
- YOLO runs at a lower priority than the page. At normal priority the map background did not load
  while the model was busy.
- Only the latest run is kept. Refreshing the browser page clears it.
- If the model finds nothing, lower the minimum confidence. The model is only as good as its training.


## Common problems
  "The model weights were not found"   Place the checkpoint at models\road_damage.pt.
  The map shows no streets             The browser needs internet access to reach the map tiles.
  Upload fails for a large video       Raise maxUploadSize in .streamlit\config.toml.
  "The GPS file needs a ... column"    Check the column names: latitude and longitude.

## License and external services

RoadSight source code is licensed under GNU AGPL version 3. See [LICENSE](LICENSE). Third-party
packages and model weights have their own license terms; check those terms before distributing or
hosting the app. KITTI data is not included. The map uses CARTO map tiles and road snapping can send
the route area to a public OpenStreetMap Overpass server; see the settings help before enabling it.
