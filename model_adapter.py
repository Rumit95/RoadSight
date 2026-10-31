"""Turns the raw output of the model into the detections that the page shows.

This is the only file that knows what the model returns. To use a different model:
  1. Point WEIGHTS in config.py to the new weights.
  2. If the model tells more than a class and a confidence, return it from read_detections:
       "label"  short model-provided text shown in the detailed results
       "info"   extra facts as name -> value; they show in the detailed results table
The map uses the hazard class for its marker color and short label. The detailed results also include
the model-provided label and facts.
Every value must be plain text or a number, and an info name must not be one of the table columns
(frame, time_s, class_name, confidence, label, latitude, longitude).
"""


def read_detections(model, result):
    # Returns one dict per thing the model found in this frame.
    detections = []
    for box in result.boxes:
        class_name = model.names[int(box.cls[0])]
        confidence = float(box.conf[0])
        x_center, y_center, width, height = box.xywh[0].tolist()
        detections.append(
            {
                "class_name": class_name,
                "confidence": confidence,
                "label": f"{class_name.replace('_', ' ')} {confidence:.0%}",
                "info": {"box_width_px": round(width), "box_height_px": round(height)},
            }
        )
    return detections
