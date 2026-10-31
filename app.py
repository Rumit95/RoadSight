"""The Streamlit page. Start it with:  streamlit run app.py"""
import base64
import os
import tempfile

import pandas as pd
import streamlit as st

import config
import gps
import map_view
import road_snap
from detection_stream import stream_detections
from markers import add_markers

LEGEND = "Marker color and label show the hazard type: :red[pothole]  :orange[alligator crack]  :violet[longitudinal crack]  :blue[transverse crack]  |  :green[vehicle]"


def ask_for_settings():
    confidence = st.slider("Minimum confidence", 0.05, 0.90, config.DEFAULT_CONFIDENCE, 0.05)
    frame_step = st.slider(
        "Run the model on every Nth frame",
        1,
        10,
        config.DEFAULT_FRAME_STEP,
        help="A higher number is faster. For a 30 fps video, 3 to 5 keeps up with the video on a CPU.",
    )
    follow_vehicle = st.checkbox(
        "Third-person camera behind the vehicle",
        value=True,
        help="The map turns so that the road ahead is always up. Switch it off to see the whole route.",
    )
    snap_to_road = st.checkbox(
        "Snap the GPS track to the nearest road",
        value=True,
        help="Moves every GPS point onto the closest road of OpenStreetMap, so the vehicle is drawn on the road "
        "and not beside it. Needs internet, and the area of the route is sent to an OpenStreetMap server. "
        "Not used for a simulated route.",
    )
    return {
        "confidence": confidence,
        "frame_step": frame_step,
        "follow_vehicle": follow_vehicle,
        "snap_to_road": snap_to_road,
    }


def find_demos():
    # Returns the names of the demo videos that have a GPS file with the same name.
    names = []
    if os.path.isdir(config.DEMO_DIR):
        for file_name in sorted(os.listdir(config.DEMO_DIR)):
            name, ending = os.path.splitext(file_name)
            if ending == ".mp4" and os.path.exists(os.path.join(config.DEMO_DIR, name + ".csv")):
                names.append(name)
    return names


def ask_for_uploads():
    video_column, gps_column = st.columns(2)
    with video_column:
        video_file = st.file_uploader("Upload a drive video", type=["mp4", "avi", "mov", "mkv"])
    with gps_column:
        gps_file = st.file_uploader(
            "GPS file (optional)",
            type=["csv"],
            help="A CSV with the columns latitude and longitude, and optionally time_s (seconds from the "
            "start of the video). Without time_s the rows are spread evenly over the video.",
        )
    return video_file, gps_file


def ask_for_inputs(video_file, gps_file):
    demo = None
    demos = find_demos()
    if len(demos) > 0 and st.checkbox("Use a demo video instead of uploading one"):
        demo = st.selectbox("Demo video", demos)

    st.caption("Without a GPS file, the demo uses a simulated route.")
    route_columns = st.columns(4)
    start_latitude = route_columns[0].number_input("Start latitude", value=config.DEFAULT_START_LAT, format="%.5f")
    start_longitude = route_columns[1].number_input("Start longitude", value=config.DEFAULT_START_LON, format="%.5f")
    heading = route_columns[2].number_input("Heading (degrees)", 0, 359, config.DEFAULT_HEADING)
    speed = route_columns[3].number_input("Speed (km/h)", 1, 120, config.DEFAULT_SPEED_KMH)

    return {
        "video_file": video_file,
        "gps_file": gps_file,
        "demo": demo,
        "simulated": (start_latitude, start_longitude, heading, speed),
    }


def make_route(inputs, duration_s):
    # Returns (route table, a sentence about where the positions come from, whether they are real GPS).
    if inputs["demo"] is not None:
        demo_gps = os.path.join(config.DEMO_DIR, inputs["demo"] + ".csv")
        return gps.load_gps_csv(demo_gps, duration_s), "GPS positions come from the demo GPS file.", True
    if inputs["gps_file"] is not None:
        inputs["gps_file"].seek(0)
        return gps.load_gps_csv(inputs["gps_file"], duration_s), "GPS positions come from your GPS file.", True
    route = gps.simulate_route(*inputs["simulated"], duration_s)
    return route, "GPS positions come from a simulated route (not real GPS).", False


def prepare_route(inputs, settings, duration_s):
    # Returns (GPS route, route drawn on the map, text about it, whether the route was snapped to the roads).
    route, source_text, real_gps = make_route(inputs, duration_s)
    if not (settings["snap_to_road"] and real_gps):
        return route, route, source_text, False

    map_route, note = road_snap.snap_to_roads(route)
    return route, map_route, f"{source_text} {note}", map_route is not route


def for_display(table, snapped):
    # The map positions only differ from the GPS positions when the track was snapped to the road.
    return table if snapped else table.drop(columns=["map_latitude", "map_longitude"])


def markers_table(markers, snapped):
    # The extra facts of the model ("info") become columns of their own.
    table = pd.DataFrame(markers)
    facts = pd.DataFrame(list(table["info"]))
    facts.columns = [name if name not in table.columns else f"info_{name}" for name in facts.columns]
    table = pd.concat([table.drop(columns=["info"]), facts], axis=1)
    return for_display(table, snapped)


def info_text(frame, time_s, latitude, longitude, detections, source_text):
    return (
        f"Frame **{frame}** | Time **{time_s:.1f} s** | Latitude **{latitude:.6f}** | "
        f"Longitude **{longitude:.6f}** | Detections in this frame **{detections}**  \n"
        f"{source_text}"
    )


def process_video(video_path, inputs, settings, boxes):
    # Shows every frame and marker while the video runs. Returns the results, or None if it failed.
    frames = []
    markers = []
    route = None
    map_route = None
    source_text = ""
    snapped = False
    total_frames = 0
    picture = None
    camera_heading = None

    stream = stream_detections(video_path, settings["confidence"], settings["frame_step"])
    try:
        for message in stream:
            if message["type"] == "error":
                boxes["status"].error("The detector stopped:\n\n" + message["message"])
                return None

            if message["type"] == "start":
                total_frames = message["total_frames"]
                boxes["status"].info("Preparing the route map...")
                try:
                    route, map_route, source_text, snapped = prepare_route(inputs, settings, message["duration_s"] or 3600)
                except ValueError as error:
                    boxes["status"].error(str(error))
                    return None
                boxes["map"].pydeck_chart(map_view.build_map(map_route, markers, None, None, False), height=config.MAP_HEIGHT)
                boxes["status"].info("Tracking the drive...")

            if message["type"] == "frame":
                time_s = message["time_s"]
                position = gps.position_at(route, time_s)  # as recorded
                map_position = gps.position_at(map_route, time_s)  # where the vehicle is drawn
                camera_heading = gps.blend_heading(camera_heading, gps.heading_at(map_route, time_s))
                detections = message["detections"]
                added = add_markers(markers, detections, message["frame"], time_s, position, map_position)
                frames.append(
                    {
                        "frame": message["frame"],
                        "time_s": round(time_s, 2),
                        "latitude": position[0],
                        "longitude": position[1],
                        "map_latitude": map_position[0],
                        "map_longitude": map_position[1],
                        "detections": len(detections),
                    }
                )

                picture = base64.b64decode(message["image"])
                boxes["picture"].image(picture)
                boxes["info"].markdown(
                    info_text(message["frame"], time_s, position[0], position[1], len(detections), source_text)
                )
                if total_frames > 0:
                    done = min(message["frame"] / total_frames, 1.0)
                    boxes["progress"].progress(done, text=f"Frame {message['frame']} of {total_frames}")

                if added > 0 or len(frames) % config.MAP_UPDATE_EVERY == 0:
                    deck = map_view.build_map(map_route, markers, map_position, camera_heading, settings["follow_vehicle"])
                    boxes["map"].pydeck_chart(deck, height=config.MAP_HEIGHT)
                if added > 0:
                    boxes["table"].dataframe(markers_table(markers, snapped), hide_index=True)
    finally:
        stream.close()  # stops the detector if the page was stopped half way
        boxes["progress"].empty()
    if len(frames) > 0:
        boxes["status"].success(f"Demo complete - {len(markers)} road hazards found.")

    return {
        "frames": frames,
        "markers": markers,
        "route": map_route,
        "picture": picture,
        "source_text": source_text,
        "snapped": snapped,
    }


def show_results(results, boxes):
    if len(results["frames"]) == 0:
        boxes["status"].warning("No frames were processed.")
        return

    frames = pd.DataFrame(results["frames"])
    last = results["frames"][-1]
    boxes["picture"].image(results["picture"])
    boxes["info"].markdown(
        info_text(last["frame"], last["time_s"], last["latitude"], last["longitude"], last["detections"], results["source_text"])
    )
    vehicle = (last["map_latitude"], last["map_longitude"])
    boxes["map"].pydeck_chart(map_view.build_map(results["route"], results["markers"], vehicle, None, False), height=config.MAP_HEIGHT)

    boxes["status"].success(f"Demo complete - {len(results['markers'])} road hazards found.")
    with boxes["table"].container():
        if len(results["markers"]) > 0:
            markers = markers_table(results["markers"], results["snapped"])
            st.subheader("Detected road hazards")
            st.dataframe(markers, hide_index=True)
            st.download_button("Download hazard list (CSV)", markers.to_csv(index=False), "damage.csv", "text/csv")
        else:
            st.info("No road damage was found. Try lowering the confidence setting.")

        st.subheader("Frame positions")
        frames = for_display(frames, results["snapped"])
        st.dataframe(frames, hide_index=True)
        st.download_button("Download frame positions (CSV)", frames.to_csv(index=False), "frames.csv", "text/csv")


def save_upload(video_file):
    suffix = os.path.splitext(video_file.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(video_file.getbuffer())
    return temp_file.name


def main():
    st.set_page_config(page_title="RoadSight demo", layout="wide")
    st.title("RoadSight")
    st.caption("See road hazards detected in a drive and where they appear on the map.")

    if not os.path.exists(config.WEIGHTS):
        st.error(
            f"The model weights were not found: {config.WEIGHTS}. "
            "Place a compatible checkpoint in the app's models folder at models/road_damage.pt."
        )
        st.stop()

    video_file, gps_file = ask_for_uploads()
    left, right = st.columns(2)
    with left:
        st.subheader("Drive video")
        picture = st.empty()
    with right:
        st.subheader("Road map")
        map_placeholder = st.empty()

    picture.info("Your drive video will appear here.")
    map_placeholder.info("The route and detected hazards will appear here.")

    with st.expander("Settings & details", expanded=False):
        st.caption("Choose a sample drive or adjust processing and route settings.")
        settings = ask_for_settings()
        inputs = ask_for_inputs(video_file, gps_file)
        st.caption(LEGEND)

    start_column, stop_column, _ = st.columns([1, 1, 3])
    can_start = inputs["video_file"] is not None or inputs["demo"] is not None
    start = start_column.button("Start demo", type="primary", disabled=not can_start)
    stop_column.button("Stop", help="Stop processing the current drive.")
    boxes = {
        "picture": picture,
        "map": map_placeholder,
        "status": st.empty(),
        "progress": st.empty(),
        "info": st.empty(),
        "table": st.empty(),
    }

    if start:
        if inputs["demo"] is not None:
            video_path = os.path.join(config.DEMO_DIR, inputs["demo"] + ".mp4")
        else:
            video_path = save_upload(inputs["video_file"])
        try:
            results = process_video(video_path, inputs, settings, boxes)
        finally:
            if inputs["demo"] is None:
                try:
                    os.remove(video_path)
                except OSError:
                    pass  # still in use; Windows cleans the temp folder later
        if results is not None:
            st.session_state["results"] = results
            show_results(results, boxes)
    elif "results" in st.session_state:
        show_results(st.session_state["results"], boxes)


main()
