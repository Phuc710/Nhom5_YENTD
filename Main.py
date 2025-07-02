from PIL import Image
import cv2
import torch
import math
import function.utils_rotate as utils_rotate
import os
import time
import argparse
import function.helper as helper

# load model
print("Loading LP_detector_nano_61.pt model...")
yolo_LP_detect = torch.hub.load('yolov5', 'custom', path='model/LP_detector_nano_61.pt', force_reload=True, source='local')
yolo_LP_detect.conf = 0.50 # Adjusted confidence for detector

print("Loading LP_ocr_nano_62.pt model...")
yolo_license_plate = torch.hub.load('yolov5', 'custom', path='model/LP_ocr_nano_62.pt', force_reload=True, source='local')
yolo_license_plate.conf = 0.60

prev_frame_time = 0
new_frame_time = 0

camera_index = 0
vid = cv2.VideoCapture(camera_index)

while not vid.isOpened():
    print(f"Error: Could not open camera at index {camera_index}.")
    camera_index += 1
    if camera_index > 5:
        print("Error: Failed to open camera after trying multiple indices (0 to 5).")
        print("Please ensure your laptop camera is working and not in use by other applications.")
        print("Exiting program.")
        exit()
    print(f"Trying camera at index {camera_index}...")
    vid = cv2.VideoCapture(camera_index)

print(f"Successfully opened camera at index {camera_index}.")

while(True):
    ret, frame = vid.read()

    if not ret:
        print("Failed to grab frame. Exiting...")
        break

    with torch.no_grad(): # Use torch.no_grad()
        plates = yolo_LP_detect(frame, size=320) # Reduced detection resolution
        list_plates = plates.pandas().xyxy[0].values.tolist()
        list_read_plates = set()
        for plate in list_plates:
            flag = 0
            x = int(plate[0])
            y = int(plate[1])
            w = int(plate[2] - plate[0])
            h = int(plate[3] - plate[1])

            # Ensure crop_img is valid before proceeding
            if h > 0 and w > 0:
                crop_img = frame[y:y+h, x:x+w]
                cv2.rectangle(frame, (int(plate[0]),int(plate[1])), (int(plate[2]),int(plate[3])), color = (0,0,225), thickness = 2)

                # Removed redundant cv2.imwrite and cv2.imread
                lp = ""
                for cc in range(0,2):
                    for ct in range(0,2):
                        lp = helper.read_plate(yolo_license_plate, utils_rotate.deskew(crop_img, cc, ct))
                        if lp != "unknown":
                            list_read_plates.add(lp)
                            cv2.putText(frame, lp, (int(plate[0]), int(plate[1]-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36,255,12), 2)
                            flag = 1
                            break
                    if flag == 1:
                        break
    
    new_frame_time = time.time()
    fps = 1/(new_frame_time-prev_frame_time)
    prev_frame_time = new_frame_time
    fps = int(fps)
    cv2.putText(frame, str(fps), (7, 70), cv2.FONT_HERSHEY_SIMPLEX, 3, (100, 255, 0), 3, cv2.LINE_AA)
    cv2.imshow('frame', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

vid.release()
cv2.destroyAllWindows()