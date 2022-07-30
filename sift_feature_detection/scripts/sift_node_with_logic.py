#!/usr/bin/env python

import cv2 as cv
from cv_bridge import CvBridge, CvBridgeError
import glob
import numpy as np

#ROS imports
import rospy
from rospkg import RosPack
import tf.transformations
from sensor_msgs.msg import Image
from cv_msgs.msg import Point2, PointArray
from geometry_msgs.msg import PoseStamped
from darknet_ros_msgs.msg import BoundingBox, BoundingBoxes
from std_msgs.msg import String
from cv_msgs.msg import Centeroid, CenteroidArray


# Contains visualization tools
from draw_tools import DrawTools

from Hough_Transform_orientation_based import HoughMajingo_ob


class SiftFeature:
    '''
    This node:

    * Reads images from a folder, generates kp (keypoints) and des (descriptors) and stores them for the session

    * Compares stored kp and des with the ones from the camera image.

    * When matches are within the threshold the homography and perspective trasform (opencv functions) gets applied

    * The corner points from the read images gets found in the cam image, aswell as the centeroid


    * Bounding box and found points gets drawn unless commented out

    '''
    
    def __init__(self):

        ##################
        ##### Params #####
        ##################

        # Image rate 
        self.get_image_rate = 0

        #  grayscale = 0, color = 1
        self.colormode = 0

        # Minimum matches needed for drawing bounding box
        self.MIN_MATCH_COUNT = 8

        # Scale the bounding box (Only downscale)
        self.scale = 0.999

        self.canny_threshold1 = 100
        self.canny_threshold2 = 200

        #################
        ###### Node #####
        #################

        #Name of the node
        node_name = "sift_feature"

        # ROS node init
        rospy.init_node(node_name)

        #Subscribe topic
        image_sub = "/zed2/zed_node/rgb/image_rect_color"
        # image_sub = "/cv/image_preprocessing/CLAHE/zed2"
        
        rospy.Subscriber(image_sub, Image, self.callback)

        mission_topic_subscribe = "/fsm/state"
        self.mission_topic_sub = rospy.Subscriber(mission_topic_subscribe, String, self.update_object_search)
        
        # Publisher
        self.detections_pub = rospy.Publisher('/feature_detection/sift_bbox_image', Image, queue_size=1)
        self.i2rcpPub = rospy.Publisher('/feature_detection/i2rcp_image', Image, queue_size= 1)
        self.detections_hough_pub = rospy.Publisher('/feature_detection/sift_bbox_image_hough', Image, queue_size= 1)


        #self.cornerpoints_pub = rospy.Publisher('/feature_detection/sift_object_points', BoundingBoxes, queue_size= 1)
        self.detection_centeroid_pub = rospy.Publisher('/feature_detection/sift_detection_centeroid', CenteroidArray, queue_size=1)
        self.BBoxPointsPub = rospy.Publisher('/feature_detection/sift_detection_bbox', BoundingBoxes, queue_size= 1)

        ##########################
        #### Mission specific ####
        ##########################

        #Subscribe topic
        mission_topic_subscribe = "/fsm/state"
        rospy.Subscriber(mission_topic_subscribe, String, self.update_mission)
        self.landmark_server_names = ["gate", "buoy","torpedo_poster","torpedo_target","octagon"]

        # Gate logic
        self.image_types = ["bootlegger", "gman"]
        self.gman_detected = 0
        self.bootlegger_detected = 0

        # buoy
        self.image_types_hough = ["badge"]
        self.image_types_buoys = ["badge", "tommy"]
        self.badge_detected = 0
        self.tommy_detected = 0

        # Torpedo
        # self.image_types_torpedo = ["torpedo_poster_bootlegger", "torpedo_poster_gman"]
        self.torpedo_poster_gman_detected = 0
        self.torpedo_poster_bootlegger_detected = 0

        # Torpedo holes
        # self.image_types_torpedo_holes = ["botlegger_circle", "bootlegger_square","gman_circle", "gman_star"]
        self.image_types = ["botlegger_circle", "bootlegger_square","gman_circle", "gman_star"]
        self.circle_search = False

        self.torpedo_hole_detected = 0

        ################
        ###CV stuff ####
        ################
        self.drawtools = DrawTools()

        self.bridge = CvBridge() 

        # Initiate SIFT detector 
        self.sift = cv.SIFT_create() # self.sift = cv.xfeatures2d.SIFT_create() # (opencv version 3.4.x) 

        ###############################
        ##### kp and des cam feed #####
        ###############################

        rp = RosPack()
        path = str(rp.get_path('sift_feature_detection')) + '/data/sift_images/'

        self.image_list = []
        self.kp = []
        self.des = []

        for i in range(len(self.image_types)):
            temp_path = glob.glob(path + self.image_types[i] + "/*.png")
            temp = [cv.imread(file, self.colormode) for file in temp_path]
            self.image_list.append(temp)
            temp_path = None

        # Gets keypoints and descriptors for every loaded image
        for image_type in self.image_list:
            kp_temp = []
            des_temp = []
            for image in image_type:
                k, d = self.sift.detectAndCompute(image,None)
                #rospy.loginfo("print k %s", k)
                kp_temp.append(k)
                des_temp.append(d)
            
            self.kp.append(kp_temp)
            self.des.append(des_temp)

        ############################
        ##### kp and des hough #####
        ############################
        self.image_list_hough = []
        self.kp_hough = []
        self.des_hough = []

        for i in range(len(self.image_types_hough)):
            temp_path = glob.glob(path + self.image_types_hough[i] + "/*.png")
            temp = [cv.imread(file, self.colormode) for file in temp_path]
            self.image_list_hough.append(temp)
            temp_path = None

        # Gets keypoints and descriptors for every loaded image
        for image_type in self.image_list_hough:
            kp_temp_hough = []
            des_temp_hough = []
            for image in image_type:
                k, d = self.sift.detectAndCompute(image,None)
                #rospy.loginfo("print k %s", k)
                kp_temp_hough.append(k)
                des_temp_hough.append(d)
            
            self.kp_hough.append(kp_temp_hough)
            self.des_hough.append(des_temp_hough)
        
        ############
        ##Init end##
        ############

    def update_object_search(self, mission):
        self.mission_topic = mission.data.split("/")[1]

        if mission == "execute/gate":
            self.image_list.remove("bootlegger")
            self.image_list.remove("gman")

            self.image_list.append(self.image_types_torpedo)

        if self.mission_topic == "execute/buoy":
            self.image_list.remove("badge")
            self.image_list.remove("tommy")
            
        if self.mission_topic == "torpedo_poster":
            self.circle_search = True

        if self.mission_topic == "torpedo_target":
            self.image_list.remove("torpedo_poster_bootlegger")
            self.image_list.remove("torpedo_poster_gman")

        # if self.mission_topic == "octagon":

    # def detect_shape(self, cam_image):


    def add_centeroid(self, img_type, centeroid):
        pub = Centeroid()
        pub.name = img_type
        pub.centre_x = centeroid[0]
        pub.centre_y = centeroid[1]
        pub.centre_z = 0

        self.CentroidArray_message.centeroid.append(pub)

    def scale_bounding_box(self, dst):
        '''
        This function downscales a square to a smaller square (no upscale).
        Use small scaling like 0.999 if your bounding box gets crazy when
        choosing a small number.

            p1-----------p4
            | \        /  |
            |   p1s  p4s  |
            |             |
            |   p2s  p3s  |
            |  /        \ |
            p2------------p3

        Returns:
            dst_scaled as a (4,1,2) array and a (4,2) array
        '''
        sf = self.scale - 1
        sf1 = 1 + np.abs(sf)
        sf2 = 1 - np.abs(sf)

        points = np.reshape(dst, (4,2))

        p1 = points[0]
        p2 = points[1]
        p3 = points[2]
        p4 = points[3]
        
        p1 = p1*sf1
        p2[0], p2[1] = p2[0]*sf1, p2[1]*sf2
        p3 = p3*sf2
        p4[0], p4[1] = p4[0]*sf2, p4[1]*sf1 

        dst_scaled = np.array([p1, p2, p3, p4])

        return np.reshape(dst_scaled,(4,1,2)), dst_scaled

    def build_bounding_boxes_msg(self, bbox_points, obj_class):
        bbox = BoundingBox()
        bbox.probability = 69.69
        bbox.xmin = int(bbox_points[0][0])
        bbox.ymin = int(bbox_points[0][1])
        bbox.xmax = int(bbox_points[2][0])
        bbox.ymax = int(bbox_points[2][1])
        bbox.z = 100000.0
        bbox.id = 0
        bbox.Class = obj_class

        new_bbox_points_msg = BoundingBoxes()
        new_bbox_points_msg.header.stamp = rospy.get_rostime()
        new_bbox_points_msg.header.frame_id = "zed_left_optical_camera_sensor"
        new_bbox_points_msg.bounding_boxes.append(bbox)

        return new_bbox_points_msg

    def compare_matches(self, cam_image, flann, kp2, des2, single_image_list, kp, des, image_type):

        good_best = []

        for i in range(len(single_image_list)):
            matches = flann.knnMatch(des[i],des2,k=2)

            # store all the good matches as per Lowe's ratio test.
            good = []
            for m,n in matches:
                if m.distance < 0.7*n.distance:
                    good.append(m)

            if len(good) > len(good_best):
                good_best = good

        if len(good_best)>self.MIN_MATCH_COUNT:
            src_pts = np.float32([ kp[i][m.queryIdx].pt for m in good ]).reshape(-1,1,2)
            dst_pts = np.float32([ kp2[m.trainIdx].pt for m in good ]).reshape(-1,1,2)
            M, mask = cv.findHomography(src_pts, dst_pts, cv.RANSAC,5.0)
            matchesMask = mask.ravel().tolist()

            if len(single_image_list[i].shape) == 2:
                h,w = single_image_list[i].shape
            else:
                h, w, _ = single_image_list[i].shape

            pts = np.float32([ [0,0],[0,h-1],[w-1,h-1],[w-1,0] ]).reshape(-1,1,2)
            dst = cv.perspectiveTransform(pts,M)

            # Scales the bounding box
            dst_scaled_cv_packed, dst_scaled = self.scale_bounding_box(dst)
                
            #self.publish_centeroid(i, centeroid, orientation)
            msg = self.build_bounding_boxes_msg(dst_scaled, image_type)

            self.BBoxPointsPub.publish(msg)

            # Add centeroid
            centeroid = self.drawtools.find_centeroid(dst)
            self.add_centeroid(image_type, centeroid)

            # Only for visual effects (draws bounding box, cornerpoints, etc...)
            cam_image = self.drawtools.draw_all(cam_image, dst, dst_scaled_cv_packed, image_type, centeroid=True,)

        else:
            print( "Not enough matches are found - {}/{}".format(len(good_best), self.MIN_MATCH_COUNT) )
            matchesMask = None

        return cam_image

    def cv_image_publisher(self, publisher, image, msg_encoding="bgra8"):
        pub_img = self.bridge.cv2_to_imgmsg(image, encoding=msg_encoding)
        publisher.publish(pub_img)

    def hough(self, cam_image):
        t1 = 60 # 100
        t2 = 150 # 200
        bb_arr, center, hough_img, edges = HoughMajingo_ob.main(cam_image, t1, t2)   # self.canny_threshold1, self.canny_threshold2, self.cv_image
        self.cv_image_publisher(self.i2rcpPub, edges, 'mono8')

        return edges


    def callback(self, cam_image_ros):
        try:
            cam_image = self.bridge.imgmsg_to_cv2(cam_image_ros, "passthrough")
            if self.colormode == 0:
                cam_image = cv.cvtColor(cam_image, cv.COLOR_BGR2GRAY)      
        except CvBridgeError, e:
            rospy.logerr("CvBridge Error: {0}".format(e))

        # Creates a CenteroidArray
        self.CentroidArray_message = CenteroidArray()

        # Huffin on some sift
        edges_image = self.hough(cam_image)

        kp2, des2 = self.sift.detectAndCompute(cam_image, None)
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm = FLANN_INDEX_KDTREE, trees = 5)
        search_params = dict(checks = 50)
        flann = cv.FlannBasedMatcher(index_params, search_params)
        
        rospy.loginfo(len(self.image_list))
        for i in range(len(self.image_list)):
            single_image_list = self.image_list[i]
            kp = self.kp[i]
            des = self.des[i]
            image_type = self.image_types[i]
            cam_image = self.compare_matches(cam_image, flann, kp2, des2, single_image_list, kp, des, image_type)

        if self.colormode == 0:
            self.cv_image_publisher(self.detections_pub, cam_image, msg_encoding="mono8")
        else:
            self.cv_image_publisher(self.detections_pub, cam_image, msg_encoding="bgra8")

        

        for i in range(len(self.image_list_hough)):
            single_image_list_hough = self.image_list_hough[i]
            kp_hough = self.kp_hough[i]
            des_hough = self.des_hough[i]
            rospy.loginfo("des length: %s",len(self.kp_hough))
            image_type = self.image_types_hough[i]
            edges_image = self.compare_matches(edges_image, flann, kp2, des2, single_image_list_hough, kp_hough, des_hough, image_type)

        self.cv_image_publisher(self.detections_hough_pub, edges_image, msg_encoding="mono8")

                # Centeroid message
        self.CentroidArray_message.header.stamp = rospy.get_rostime()
        self.CentroidArray_message.header.frame_id = "zed_left_camera_sensor"

        self.detection_centeroid_pub.publish(self.CentroidArray_message)
        
        #rospy.sleep(self.get_image_rate)
        

if __name__ == '__main__':
    feature = SiftFeature()
    while not rospy.is_shutdown():     
        try:
            rospy.spin()
        except rospy.ROSInterruptException:
            pass
    
