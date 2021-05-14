#!/usr/bin/python3
import math
import numpy as np
import cv2
import math
import ht301_hacklib
import utils
import time
import os
import sys
import cv2
import fcntl
#import asyncio
#from mavsdk import System
from dronekit import connect
from v4l2 import (
    v4l2_format, VIDIOC_G_FMT, V4L2_BUF_TYPE_VIDEO_OUTPUT, V4L2_PIX_FMT_RGB24,
    V4L2_FIELD_NONE, VIDIOC_S_FMT
)

########### init ###########

#vehicle = connect("/dev/openhd_microservice1", wait_ready=True, baud=115200) # address of the openhd mavlink router

rc_channel = '8' # aux channel 4 = channel 8, for cycle colormaps
ch_state = False
prev_ch_state = False

VIDEO_IN = "/dev/video0"
VIDEO_OUT = "/dev/video5"
VID_WIDTH = 384
VID_HEIGHT = 288

flipped_camera = True
draw_temp = True
calibration_offset = True

# list of used colormaps. all available colormaps here: https://docs.opencv.org/master/d3/d50/group__imgproc__colormap.html#ga9a805d8262bcbe273f16be9ea2055a65
colormaps = [cv2.COLORMAP_BONE, cv2.COLORMAP_PINK, -1, cv2.COLORMAP_INFERNO, cv2.COLORMAP_TURBO] # add -1 for dde algorithm
selectedmap = 1 # selected map on startup. default is 0

############################

# cycle colormaps
def cyclecolormaps():
    if selectedmap < len(colormaps) - 1:
        selectedmap += 1
    else:
        selectedmap = 0

def main():

    ########### camera #############

    # create camera object. initial calibration will be executed by constructor
    cap = ht301_hacklib.HT301()

    # read calibration array from file
    offset = np.load("noise_pattern_calibration.npy")

    # create a Contrast Limited Adaptive Histogram Equalization object. default: 5.0, (6, 6)
    clahe = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(6, 6))

    # open v4l2 output device
    videooutput = os.open(VIDEO_OUT, os.O_RDWR)

    # configure parameters for output device
    vid_format = v4l2_format()
    vid_format.type = V4L2_BUF_TYPE_VIDEO_OUTPUT
    if fcntl.ioctl(videooutput, VIDIOC_G_FMT, vid_format) < 0:
        print("ERROR: unable to get video format!")
        return -1

    framesize = VID_WIDTH * VID_HEIGHT * 3
    vid_format.fmt.pix.width = VID_WIDTH
    vid_format.fmt.pix.height = VID_HEIGHT

    # pixel format
    vid_format.fmt.pix.pixelformat = V4L2_PIX_FMT_RGB24
    vid_format.fmt.pix.sizeimage = framesize
    vid_format.fmt.pix.field = V4L2_FIELD_NONE

    if fcntl.ioctl(videooutput, VIDIOC_S_FMT, vid_format) < 0:
        print("ERROR: unable to set video format!")
        return -1

    ################################

    # video loop
    while(True):
        # cycle only one map per button press
        #if vehicle.channels[rc_channel] > 1800:
        #    ch_state = True
        #    if prev_ch_state == False:
        #        cyclecolormaps()
        #else:
        #    ch_state = False
        #prev_ch_state = ch_state

        ret, frame = cap.read() # read frame from thermal camera
        info, lut = cap.info() # get hottest and coldest spot and its temperatures

        if selectedmap != 0: # do not apply anything when 0 is selected. original frame
            # automatic gain control
            frame = frame.astype(np.float32)
            if calibration_offset == True: # apply calibration offset
                frame = frame - offset + np.mean(offset)
            frame = (255*((frame - frame.min())/(frame.max()-frame.min()))).astype(np.uint8) # cast frame to values from 0 to 255

            if colormaps[selectedmap] == -1:
                # digital detail enhancement algorithm
                framebuffer = frame
                clahe.apply(framebuffer, frame)
                frame = cv2.applyColorMap(frame, colormaps[1])
            else:
                # apply colormap
                frame = cv2.applyColorMap(frame, colormaps[selectedmap])

        if flipped_camera == True: # rotate the temperature points with the image if the thermal camera is mounted upside down
            (coldx, coldy) = info['Tmin_point']
            (warmx, warmy) = info['Tmax_point']
            coldestpoint = (VID_WIDTH - coldx, VID_HEIGHT - coldy)
            warmestpoint = (VID_WIDTH - warmx, VID_HEIGHT - warmy)
            frame = cv2.flip(frame, -1) # flip the frame
        else:
            coldestpoint = info['Tmin_point']
            warmestpoint = info['Tmax_point']

        if draw_temp: # color: BGR
            utils.drawTemperature(frame, coldestpoint, info['Tmin_C'], (255, 0, 0)) # coldest spot
            utils.drawTemperature(frame, warmestpoint, info['Tmax_C'], (0, 0, 255)) # hottest spot
            #utils.drawTemperature(frame, info['Tcenter_point'], info['Tcenter_C'], (0, 255, 255)) # center spot

        # output
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # convert opencv bgr to rgb for the v4l2 pixelformat
        written = os.write(videooutput, frame.data) # write frame to output device

    cap.release()
    #vehicle.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
