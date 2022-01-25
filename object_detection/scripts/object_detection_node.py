#!/usr/bin/env python

# import debugpy
# print("Waiting for VSCode debugger...")
# debugpy.listen(5678)
# debugpy.wait_for_client()

import rospy
# import numpy as np
# import ros_numpy

# Import msg types
from darknet_ros_msgs.msg import BoundingBoxes, BoundingBox
from cv_msgs.msg import BBox, BBoxes, Point2, PointArray
from geometry_msgs.msg import PointStamped, PoseStamped, Pose
from vortex_msgs.msg import ObjectPosition
from sensor_msgs.msg import PointCloud2
from sensor_msgs import point_cloud2

# Import classes
from position_estimator import PositionEstimator
from coord_pos import CoordPosition
from pointcloud_mapping import PointCloudMapping

class ObjectDetectionNode():
    """
    Handles tasks related to object detection
    """
    cameraframe_x = 1280    # Param to set the expected width of cameraframe in pixels
    cameraframe_y = 720     # Param to set the expected height of cameraframe in pixels
    use_reduced_pc = False  # Param to change wether or not to use reduced pointcloud data

    def __init__(self):
        rospy.init_node('object_detection_node')
        self.bboxSub = rospy.Subscriber('/darknet_ros/bounding_boxes', BoundingBoxes, self.darknet_cb)
        # self.CVbboxSub = rospy.Subscriber('/gate_detection/BoundingBox', BoundingBox, self.feature_bbox_cb)
        # self.lim_pointcloudPub = rospy.Publisher('/object_detection/pointcloud_limited_to_bbox',PointCloud2, queue_size=1) 
        self.feat_detSub = rospy.Subscriber('/feature_detection/object_points', PointArray, self.feat_det_cb)
        
        # Decide which pointcloud to use, this onsly works on topics described below
        if self.use_reduced_pc:
            self.pointcloud_reducedSub = rospy.Subscriber('/pointcloud_downsize/output', PointCloud2, self.pointcloud_camera_cb)
        else:
            self.pointcloudSub = rospy.Subscriber('/zed2/zed_node/point_cloud/cloud_registered', PointCloud2, self.pointcloud_camera_cb)
        
        # TODO: Needs reevaluation
        self.estimatorPub = rospy.Publisher('/object_detection/size_estimates', BBoxes, queue_size= 1) # TODO: Needs reevaluation
        
        # Calling classes from other files
        self.position_estimator = PositionEstimator()
        self.coord_positioner = CoordPosition()
        self.pointcloud_mapper = PointCloudMapping()

    def feat_det_cb(self, msg):
        """
        TODO: fillit
        """
        headerdata = msg.header
        objectID = msg.Class
        
        # Generates an empty list and adds all the point from msg to it
        point_list = []
        for point in msg.point_array:
            point_list.append([point.x, point.y])

        # Calls function to find object centre and orientation
        # orientationdata, positiondata = self.object_orientation_from_point_list(point_list, objectID)
        orientationdata, positiondata = self.object_orientation_from_point_list(point_list)
        self.send_position_orientation_data(headerdata, positiondata, orientationdata, objectID)

    def pointcloud_camera_cb(self, msg_data):
        """
        Stores message from a PointCloud2 message into a class variable

        Args:
            msg_data: callback message from subscription

        Returns:
            class variable: self.pointcloud_data
        """
        self.pointcloud_data = msg_data

    # def feature_bbox_cb(self, data):
    #     """
    #     Args:
    #         data: bbox msg data
    #     """
    #     bounding_box = data
    #     self.republish_pointcloud_from_bbox(bounding_box)

    # def republish_pointcloud_from_bbox(self, bounding_box):
    #     """
    #     TODO: This needs explanation
    #     """
    #     # get pointcloud and bounding box data
    #     newest_msg = self.pointcloud_data       
    #     data_from_zed = ros_numpy.numpify(newest_msg)

    #     # get limits from bounding box
    #     x_min_limit = bounding_box.xmin
    #     x_max_limit = bounding_box.xmax
    #     y_min_limit = bounding_box.ymin
    #     y_max_limit = bounding_box.ymax

    #     # limiting pointcloud to bounding_box_size
    #     data_from_zed_old = np.array_split(data_from_zed, [x_min_limit], axis=0)[1]
    #     data_from_zed_old = np.array_split(data_from_zed_old, [x_max_limit-x_min_limit], axis=0)[0]
    #     data_from_zed_old = np.array_split(data_from_zed_old, [y_min_limit], axis=1)[1]
    #     data_from_zed_old = np.array_split(data_from_zed_old, [y_max_limit-y_min_limit], axis=1)[0]
        
    #     pcd_height, pcd_width = np.shape(data_from_zed_old)
    #     msg = ros_numpy.msgify(PointCloud2, data_from_zed_old)

    #     msg.header = newest_msg.header
    #     msg.height = pcd_height
    #     msg.width = pcd_width

    #     self.lim_pointcloudPub.publish(msg)

    def send_position_orientation_data(self, headerdata, positiondata, orientationdata, name):
        """
        Call to send position and orientation data for other nodes

        Args:
            headerdata: header you want to send with (frame)
            positiondata: [x, y, z] floats
            orientationdata: [x, y, z, w] floats
            name: name of detected object. String
        """
        if orientationdata:
            self.send_pose_message(headerdata, positiondata, orientationdata, name)
            self.send_ObjectPosition_message(headerdata, positiondata, orientationdata, name)
    
    def object_orientation_from_point_list(self, point_list):
        """
        Uses known points to find object and its orientation
        
        Args:
            point_list: list of points as tuples [(x,y),(x,y)]
        
        Returns:
            orientationdata = [x, y, z, w] \n
            positiondata = [x, y, z]
        """
        assert isinstance(self.pointcloud_data, PointCloud2)
        new_point_list = []
        for point in point_list:
            pt_gen = point_cloud2.read_points(self.pointcloud_data, skip_nans=True, uvs=[[point[0],point[1]]])
            for pt in pt_gen:
                new_point_list.append(pt)

        orientationdata, positiondata = self.pointcloud_mapper.points_to_plane(new_point_list)
        return orientationdata, positiondata

    def object_orientation_from_poincloud(self, pointcloud_data, threshold):
        """
        Uses pointcloud data to find closest flat object and its orientation in regards to pointcloud_data frame
        
        Args:
            pointcloud_data: The pointcloud data to analyze
            threshold: maximum distance of expected object dimensions as float cm.mm. Ex: if height is bigger than width input height

        Returns:
            orientationdata = [x, y, z, w]
            positiondata = [x, y, z]
        """
        # TODO: Rethink using this function
        assert isinstance(pointcloud_data, PointCloud2)
        generated_pointcloud_list = []
        closest_point = 200.00
        pt_gen = point_cloud2.read_points(pointcloud_data, skip_nans=True)
        
        for pt in pt_gen:
            tmp_list = list(pt)
            tmp_list = tmp_list[:3]
            if (abs(pt[2]) < closest_point) and (abs(pt[2]) > 0.2):
                closest_point = abs(pt[2])
            generated_pointcloud_list.append(tmp_list)

        object_point_list = []
        for point in generated_pointcloud_list:
            if abs(point[2]) <= (threshold + closest_point):
                object_point_list.append(point)
        
        orientationdata, positiondata = self.pointcloud_mapper.points_to_plane(object_point_list)
        return orientationdata, positiondata

    def get_pointcloud_position_of_xy_point(self, x_pixel, y_pixel):
        """
        Reads the point cloud data from a given x, y coordinate

        Args:
            x_pixel: position in x direction of point you want clouddata from
            y_pixel: position in y direction of point you want clouddata from

        Returns:
            Point cloud data for a point in the camera frame as list [x, y, z]
        """
        # Generates a readable version of the point cloud data
        is_pointcloud = isinstance(self.pointcloud_data, PointCloud2)
        if is_pointcloud:
            # Reads the point cloud data at given uvs: u = x cord, v = y cord
            pt_gen = point_cloud2.read_points(self.pointcloud_data, skip_nans=False, uvs=[[x_pixel, y_pixel]])
            for pt in pt_gen:
                self.pointcloud_x = pt[0]
                self.pointcloud_y = pt[1]
                self.pointcloud_z = pt[2]

        x, y, z = self.pointcloud_x, self.pointcloud_y, self.pointcloud_z
        return [x, y, z]

    def object_orientation_from_xy_area(self, area_with_limits):
        """
        Reads the point cloud data from a given area

        Args:
            area_with_limits: list of data [xmin, xmax, ymin, ymax]

        Returns:
            orientationdata = [x, y, z, w]
            positiondata = [x, y, z]
        """
        # Generates a readable version of the point cloud data
        assert isinstance(self.pointcloud_data, PointCloud2)

        xmin = area_with_limits[0]
        xmax = area_with_limits[1]
        ymin = area_with_limits[2]
        ymax = area_with_limits[3]

        # loops through the area data and adds points to a list
        point_list = []
        for x in range(xmin  -1, xmax -1):
            for y in range(ymin - 1, ymax - 1):
                pt_gen = point_cloud2.read_points(self.pointcloud_data, skip_nans=True, uvs=[[x,y]])
                for pt in pt_gen:
                    point_list.append(pt)

        orientationdata, positiondata = self.pointcloud_mapper.points_to_plane(point_list)
        return orientationdata, positiondata

    def darknet_cb(self, data):
        """
        Gets the data from the subscribed message BoundingBoxes and publishes the size estimates of a detected object, and the position of the object.

        Args:
            data: The message that has been recieved.

        Returns:
            Published topics:
                estimatorPub: Array of detected objects as the estimated size of these. Topic also includes angles to the objects from the camera frame.
        """
        # Allocates msg data to local variables in order to process abs size
        ArrayBoundingBoxes = BBoxes()
        ArrayBoundingBoxes.header = data.header
        ArrayBoundingBoxes.image_header = data.image_header

        # Iterate through all the detected objects and estimate sizes
        for bbox in data.bounding_boxes:

            # Unintuitively position is logged as top to bottom. We fix it so it is from bot to top
            temp_ymin = bbox.ymin
            bbox.ymin = self.cameraframe_y - bbox.ymax # TODO: needs to be updated to automatically read ymax of camera
            bbox.ymax = self.cameraframe_y - temp_ymin

            self.object_orientation_from_xy_area([bbox.xmin,bbox.xmax,bbox.ymin,bbox.ymax], bbox.Class)

            # Store depth measurement of boundingbox
            depth_mtr = bbox.z

            # Get the size estimation from the size estimator class
            object_estimator_data = self.position_estimator.main(bbox)
            redefined_angle_x = object_estimator_data[2]
            redefined_angle_y = object_estimator_data[3]

            # Build the new bounding box message
            CurrentBoundingBox = BBox()
            CurrentBoundingBox.Class = bbox.Class
            CurrentBoundingBox.probability = bbox.probability
            CurrentBoundingBox.width = 0
            CurrentBoundingBox.height = 0
            CurrentBoundingBox.z = depth_mtr
            CurrentBoundingBox.centre_angle_x = redefined_angle_x
            CurrentBoundingBox.centre_angle_y = redefined_angle_y

            # Get the position of the object relative to the camera
            position = self.coord_positioner.main(redefined_angle_x, redefined_angle_y, depth_mtr)

            # Append the new message to bounding boxes array
            ArrayBoundingBoxes.bounding_boxes.append(CurrentBoundingBox)
            
        self.estimatorPub.publish(ArrayBoundingBoxes)

    def send_pointStamped_message(self, headerdata, position, name):
        """
        Publishes a PointStamped as a topic under /object_detection/object_point

        Args:
            headerdata: Headerdata to be used as a header will not be created in this function
            position: A position xyz in the form [x, y, z] where xyz are floats
            name: name to be given to the point published, must not contain special characters.

        Returns:
            Topic:
                /object_detection/object_point/name where name is your input
        """
        # For testing
        pointPub = rospy.Publisher('/object_detection/object_point/' + name, PointStamped, queue_size= 1)
        new_point = PointStamped()
        new_point.header = headerdata
        new_point.header.stamp = rospy.get_rostime()
        new_point.point.x = position[0]
        new_point.point.y = position[1]
        new_point.point.z = position[2]
        pointPub.publish(new_point)

    def send_pose_message(self, headerdata, position_data, quaternion_data, name):
        """
        Publishes a PoseStamped as a topic under /object_detection/object_pose

        Args:
            headerdata: Headerdata to be used as a header will not be created in this function
            position_data: A position xyz in the form [x, y, z] where xyz are floats
            quaternion_data: A quaternion wxyz in the form [w, x, y, z]
            name: name to be given to the point published, must not contain special characters.

        Returns:
            Topic:
                /object_detection/object_pose/name where name is your input
        """
        posePub = rospy.Publisher('/object_detection/object_pose_rviz/' + name, PoseStamped, queue_size= 1)
        p_msg = PoseStamped()
        # Format header
        p_msg.header = headerdata
        p_msg.header.stamp = rospy.get_rostime()

        # Build pose
        p_msg.pose.position.x = position_data[0]
        p_msg.pose.position.y = position_data[1]
        p_msg.pose.position.z = position_data[2]
        p_msg.pose.orientation.x = 1
        p_msg.pose.orientation.y = quaternion_data[2]
        p_msg.pose.orientation.z = 1
        p_msg.pose.orientation.w = 1
        posePub.publish(p_msg)

    def send_ObjectPosition_message(self, headerdata, position_data, quaternion_data, name):
        """
        Publishes a PoseStamped as a topic under /object_detection/object_pose

        Args:
            headerdata: Headerdata to be used as a header will not be created in this function
            position_data: A position xyz in the form [x, y, z] where xyz are floats
            quaternion_data: A quaternion wxyz in the form [w, x, y, z]
            name: string name to be given to the point published, must not contain special characters.

        Returns:
            Topic:
                /object_detection/object_pose/name where name is your input
        """
        objposePub = rospy.Publisher('/object_detection/object_pose/' + name, ObjectPosition, queue_size= 1)
        p_msg = ObjectPosition()
        p_msg.objectID = name

        # Build pose
        p_msg.objectPose.pose.position.x = position_data[0]
        p_msg.objectPose.pose.position.y = position_data[1]
        p_msg.objectPose.pose.position.z = position_data[2]
        p_msg.objectPose.pose.orientation.x = 1
        p_msg.objectPose.pose.orientation.y = quaternion_data[2]
        p_msg.objectPose.pose.orientation.z = 1
        p_msg.objectPose.pose.orientation.w = 1
        objposePub.publish(p_msg)


if __name__ == '__main__':
    node = ObjectDetectionNode()

    while not rospy.is_shutdown():
        rospy.spin()

