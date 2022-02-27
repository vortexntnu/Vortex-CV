# Vortex-CV
A repository for a set of computer vision (CV) modules, developed by students in Vortex NTNU for use in the AUV and ASV software stacks. The modules are meant to be pipelined serially with the end goal of classifying objects and determining their poses (positions and according orientations) in 3D space. Having that in mind, the individual modules are built to be able to use individually for singular goals, e.g. shape detection, pose estimation, etc.

## Table of contents
* [Overview](#overview)
* [Prerequisites](#prerequisites)
* [Setup](#setup)

## Overview
Dataflow diagram over the modules:
![dataflow diagram](https://github.com/vortexntnu/Vortex-CV/blob/main/docs/Vortex-CV_dataflow.jpg?raw=true)

Summary of the packages and their functionalities:
| Folder/Package        | Contents |
|-----------------------|--------------------------------------------------------------------------------------------------------------------------------|
| vision_launch         | A wrapper package for the whole stack - a top-level module for configurating and launching all of the necessary 'online' CV systems. |
| feature_detection     | Feature-based object detection and classification system, i.e. colour-, shape-, line-, point-, etc. fitting algorithm composites. |
| pointcloud_processing | Point(s) in 3D space and depth data handling for pose calculation of objects (point arrays) in the world. |
| object_ekf            | Object pose filtering and estimation using an Extended Kalman Filter. (WIP) |
| camera_calibration    | Calibration of intrinsic camera lense parameters, as well as extrinsic stereo camera parameters. Based on OpenCV calibration package. (WIP) |
| cv_utils              | A package meant for standalone CV utility programs/ROS launches. |
| cv_msgs               | Custom messages used in CV/OD pipeline. |

## Prerequisites
- Python 2.7
- ROS Melodic
- NumPy
- scikit-learn
- opencv-python

### Github dependencies
- [Dynamic dynamic reconfigure python](https://github.com/pal-robotics/ddynamic_reconfigure_python)
- [Darknet ROS ZED](https://github.com/vortexntnu/darknet_ros_zed)

## Setup
With all the dependencies installed:
```
$ cd ~/ && mkdir -p cv_ws/src & cd ~/cv_ws/src
$ git clone https://github.com/pal-robotics/ddynamic_reconfigure_python
$ git clone https://github.com/vortexntnu/darknet_ros_zed --recursive
$ git clone https://github.com/vortexntnu/Vortex-CV
```

```
$ cd ~/cv_ws && catkin build
```
In regards to any errors you get when building Darknet ROS, as well as integration with ZED2 camera, check out the object detection wiki in Vortex-AUV: 
https://github.com/vortexntnu/Vortex-AUV/wiki/Object-detection

```
$ source devel/setup.bash
$ roslaunch vision_launch vision_launch.launch
```
