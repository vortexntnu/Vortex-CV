#!/usr/bin/env python

#import debugpy
#print("Waiting for VSCode debugger...")
#debugpy.listen(5678)
#debugpy.wait_for_client()

##EKF imports
#from logging import exception
from re import X
from this import d

from ekf_python2.gaussparams_py2 import MultiVarGaussian
from ekf_python2.dynamicmodels_py2 import landmark_gate
from ekf_python2.measurementmodels_py2 import NED_linear_landmark
from ekf_python2.ekf_py2 import EKF
import ThreeD_orientation_model_sym

#Math imports
import numpy as np
from numpy import linalg as nla

#ROS imports
import rospy
from vortex_msgs.msg import ObjectPosition
from geometry_msgs.msg import PoseStamped, TransformStamped
import tf.transformations as tft
import tf2_ros

class EKFNode:
    

    def __init__(self):
        ########################################
        ####Things you can change yourself####
        ########################################

        #Name of the node
        node_name = "ekf_vision"

        #Frame names, e.g. "odom" and "cam"
        self.parent_frame = 'mocap' 
        self.child_frame = 'auv/camerafront_link'
        self.object_frame = "object_truth"

        #Set to 1 for global coords for the object(use tf-frames to get the distance from gate to camera), 
        #Set to 0 for recieving distance from gate to camera using "object_topic_subscribe"
        self.using_global_fake_object = 1 
        self.n = np.random.normal(0, 0.2**2, 3) #Noise added TODO is there a better way to disturbe the filter (Ivan)
        
        #Subscribe topic
        object_topic_subscribe = "/object_detection/object_pose/gate"

        
        ##################
        ####EKF stuff####
        ##################

        # Geometric parameters
        self.gate_prior = [0, 0] # z, roll, pitch of gate

        # Tuning parameters
        self.sigma_a = 1/5*np.array([0.05, 0.05, 0.05, 0.05, 0.05, 0.05])
        self.sigma_z = 2*np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])

        self.R = np.diag(self.sigma_z)
        # Making gate model object
        self.gate_model = landmark_gate(self.sigma_a)

        # The measurement Jacobian lambda
        self.H_lam = ThreeD_orientation_model_sym.init()

        #Gauss prev values
        self.x_hat0 = np.array([0, 0, 0, 0, 0, 0]) 
        self.P_hat0 = np.diag(self.sigma_z)
        self.prev_gauss = MultiVarGaussian(self.x_hat0, self.P_hat0)
        self.prev_quat = [0, 0, 0, 1]
        ################
        ###ROS stuff####
        ################

        # ROS node init
        rospy.init_node(node_name)
        self.last_time = rospy.get_time()

        now = rospy.get_rostime()
        rospy.loginfo("Current time %i %i", now.secs, now.nsecs)

        # Subscriber to gate pose and orientation 
        self.object_pose_sub = rospy.Subscriber(object_topic_subscribe, PoseStamped, self.obj_pose_callback, queue_size=1)
      
        # Publisher to autonomous
        self.gate_pose_pub = rospy.Publisher('/fsm/object_positions_in', ObjectPosition, queue_size=1)

        #TF stuff
        self.__tfBuffer = tf2_ros.Buffer() # TODO Add a tf buffer length? tf2_ros.Buffer(rospy.Duration(1200.0)) (Kristian)
        self.__listener = tf2_ros.TransformListener(self.__tfBuffer)
        self.__tfBroadcaster = tf2_ros.TransformBroadcaster()

        #The init will only continue if a transform between parent frame and child frame can be found
        while self.__tfBuffer.can_transform(self.parent_frame, self.child_frame, rospy.Time()) == 0:
            try:
                rospy.loginfo("No transform between "+str(self.parent_frame) +' and ' + str(self.child_frame))
                rospy.sleep(2)
            except: #, tf2_ros.ExtrapolationException  (tf2_ros.LookupException, tf2_ros.ConnectivityException)
                rospy.sleep(2)
                continue
        
        rospy.loginfo("Transform between "+str(self.parent_frame) +' and ' + str(self.child_frame) + 'found.')
        
        ############
        ##Init end##
        ############

    def get_Ts(self): # TODO inspect how well this works (Ivan)
        Ts = rospy.get_time() - self.last_time
        return Ts

    def generate_noisy_measurement(self, z_noiseless):
        
        noise = np.array([0.05, 0.05, 0.05, 0.001, 0.001, 0.001])
        noise_bad = np.array([1.5, 1.5, 1.5, np.pi/4, np.pi/4, np.pi/4])

        a = np.random.uniform(0,1)
        if a >= 0.075:
            z_noised = z_noiseless + np.random.normal(0, noise)
            return z_noised
        else:
            z_noised = z_noiseless + np.random.normal(0, noise_bad)
            return z_noised
    
    def ekf_function(self, pw_wc, Rot_wc, Rot_cl, z):

        measurement_model = NED_linear_landmark(self.sigma_z, pw_wc, Rot_wc, Rot_cl, self.H_lam)

        Ts = self.get_Ts()

        my_ekf = EKF(self.gate_model, measurement_model)

        gauss_x_pred, gauss_z_pred, gauss_est = my_ekf.step_with_info(self.prev_gauss, z, Ts)
        
        self.last_time = rospy.get_time()
        self.prev_gauss = gauss_est # instantiate last estimate and time

        return gauss_x_pred, gauss_z_pred, gauss_est

    def est_to_pose(self, x_hat):
        x = x_hat[0]
        y = x_hat[1]
        z = x_hat[2]
        pos = [x, y, z]

        euler_angs = [x_hat[3], x_hat[4], x_hat[5]]
        return pos, euler_angs

    def transformbroadcast(self, parent_frame, p):
        t = TransformStamped()
        t.header.stamp = rospy.Time.now()
        t.header.frame_id = parent_frame
        t.child_frame_id = "object_"+str(p.objectID)
        t.transform.translation.x = p.objectPose.pose.position.x
        t.transform.translation.y = p.objectPose.pose.position.y
        t.transform.translation.z = p.objectPose.pose.position.z
        t.transform.rotation.x = p.objectPose.pose.orientation.x
        t.transform.rotation.y = p.objectPose.pose.orientation.y
        t.transform.rotation.z = p.objectPose.pose.orientation.z
        t.transform.rotation.w = p.objectPose.pose.orientation.w
        self.__tfBroadcaster.sendTransform(t)

        
    def publish_gate(self, object_name, ekf_position, ekf_pose_quaterion):
        p = ObjectPosition() 
        #p.pose.header[]
        p.objectID = object_name
        p.objectPose.pose.position.x = ekf_position[0]
        p.objectPose.pose.position.y = ekf_position[1]
        p.objectPose.pose.position.z = ekf_position[2]
        p.objectPose.pose.orientation.x = ekf_pose_quaterion[0]
        p.objectPose.pose.orientation.y = ekf_pose_quaterion[1]
        p.objectPose.pose.orientation.z = ekf_pose_quaterion[2]
        p.objectPose.pose.orientation.w = ekf_pose_quaterion[3]
        
        self.gate_pose_pub.publish(p)
        rospy.loginfo("Object published: %s", object_name)
        self.transformbroadcast(self.parent_frame, p)

    def transformbroadcast_camera_gate(self, parent_frame, child_frame, msg_position, msg_pose):
        t = TransformStamped()
        t.header.stamp = rospy.Time.now()
        t.header.frame_id = parent_frame
        t.child_frame_id = "object_"+str(child_frame)
        t.transform.translation.x = msg_position[0]
        t.transform.translation.y = msg_position[1]
        t.transform.translation.z = msg_position[2]
        t.transform.rotation.x =    msg_pose[0]
        t.transform.rotation.y =    msg_pose[1]
        t.transform.rotation.z =    msg_pose[2]
        t.transform.rotation.w =    msg_pose[3]
        self.__tfBroadcaster.sendTransform(t)

    def obj_pose_callback(self, msg):
        rospy.loginfo("Object data recieved for: %s", msg.header.frame_id)
        
        if self.using_global_fake_object == 1:
            tf_lookup_cg = self.__tfBuffer.lookup_transform(self.child_frame, self.object_frame, rospy.Time(), rospy.Duration(2))
            
            obj_pose_position_c = np.array([tf_lookup_cg.transform.translation.x,
                                            tf_lookup_cg.transform.translation.y,
                                            tf_lookup_cg.transform.translation.z])
            
            tf_lookup_wg = self.__tfBuffer.lookup_transform(self.parent_frame, self.object_frame, rospy.Time(), rospy.Duration(2))
            obj_pose_pose_c  = np.array([tf_lookup_cg.transform.rotation.x, 
                                         tf_lookup_cg.transform.rotation.y,
                                         tf_lookup_cg.transform.rotation.z,
                                         tf_lookup_cg.transform.rotation.w])
        else:
            #Gate in world frame for cyb pool
            obj_pose_position_c = np.array([msg.pose.position.x, 
                                            msg.pose.position.y, 
                                            msg.pose.position.z])

           
            obj_pose_pose_c = np.array([msg.pose.orientation.x,
                                        msg.pose.orientation.y,
                                        msg.pose.orientation.z,
                                        msg.pose.orientation.w])
        
        self.transformbroadcast_camera_gate(self.child_frame, "gate_detected", obj_pose_position_c, obj_pose_pose_c)
        tf_lookup_wg = self.__tfBuffer.lookup_transform(self.parent_frame, "object_gate_detected", rospy.Time(), rospy.Duration(2))
        
        obj_pose_position_wg = np.array([tf_lookup_wg.transform.translation.x, 
                                         tf_lookup_wg.transform.translation.y, 
                                         tf_lookup_wg.transform.translation.z])
           
        obj_pose_pose_wg = np.array([tf_lookup_wg.transform.rotation.x,
                                     tf_lookup_wg.transform.rotation.y,
                                     tf_lookup_wg.transform.rotation.z,
                                     tf_lookup_wg.transform.rotation.w])
        



        tf_lookup_wc = self.__tfBuffer.lookup_transform(self.parent_frame, self.child_frame, rospy.Time(), rospy.Duration(5))
        
        # Assumption: this is the matrix that transforms a vector from world to camera (parent to child)
        # New working assumption: this is actually from child to parent (camera to world)
        # The new working assumption is the current best estimate.. kill me
        
        #Go directly from quaternion to matrix
        Rot_wc = tft.quaternion_matrix([tf_lookup_wc.transform.rotation.x, 
                                        tf_lookup_wc.transform.rotation.y,
                                        tf_lookup_wc.transform.rotation.z,
                                        tf_lookup_wc.transform.rotation.w])

        #Rot_lw = tft.euler_matrix(self.prev_gauss.mean[3], self.prev_gauss.mean[4], self.prev_gauss.mean[5], "sxyz")


        pw_wc = np.array([tf_lookup_wc.transform.translation.x,
                          tf_lookup_wc.transform.translation.y,
                          tf_lookup_wc.transform.translation.z])

        Rot_wc = Rot_wc[0:3, 0:3]
        #Rot_lw = Rot_lw[0:3, 0:3]
        Rot_lw = np.eye(3)

        Rot_cl = np.matmul(Rot_wc, Rot_lw).T # ignore the notation for now
        
        #TODO add pose estimation capabilities to the EKF as position works now (Ivan + Kristian)
        # For generating a measurement:
        #obj_pose_pose_w = tft.quaternion_multiply(, obj_pose_pose_c)
        z_phi, z_theta, z_psi = tft.euler_from_quaternion(obj_pose_pose_wg, axes='sxyz')

        z = obj_pose_position_c
        z = np.append(z, [z_phi, z_theta, z_psi])

        z = self.generate_noisy_measurement(z)
        
        rospy.loginfo (msg.pose.orientation.z)
        #Data from EKF
        gauss_x_pred, gauss_z_pred, gauss_est = self.ekf_function(pw_wc, Rot_wc, Rot_cl, z)
        x_hat = gauss_est.mean

        ekf_position, ekf_pose = self.est_to_pose(x_hat)
        ekf_pose_quaterion = tft.quaternion_from_euler(ekf_pose[0], ekf_pose[1], ekf_pose[2])

        #Publish data and transform the data
        self.publish_gate(msg.header.frame_id ,ekf_position, ekf_pose_quaterion)
    
    def gate_hypotheses(self, z):
        N = np.shape(self.active_hypotheses[0])
        gated_hypotheses = []
        m_distances = []

        for i in range(N):
            error = z - self.active_filters[0].mean
            mahalanobis_distance = np.matmul(error.T, nla.solve(self.active_filters[0].cov + self.R, error))

            if mahalanobis_distance <= self.gate_sq:
                gated_hypotheses.append(i+1)
                m_distances.append(mahalanobis_distance)

        return gated_hypotheses, m_distances
        
    def associate(self, z):
        N = np.shape(self.active_hypotheses[0])
        distances = np.zeros((N, 1))

        for i in range(N):
            distances[i] = self.active_filters[i].mahalanobis_distance(z)
        
    def gmm_callback(self, msg):
        
        measurement_position = np.array([
            msg.pose.position.x,
            msg.pose.position.y,
            msg.pose.position.z])
        measurement_orientation = np.array([
            msg.pose.orientation.x,
            msg.pose.orientation.y,
            msg.pose.orientation.y,
            msg.pose.orientation.w])

        z_phi, z_theta, z_psi = tft.euler_from_quaternion(measurement_orientation, axes = "sxyz")
        z_eulers = np.array([z_phi, z_theta, z_psi])

        z = np.append(measurement_position, z_eulers)
        z_gauss = MultiVarGaussian(z, self.R)

        gated_inds, m_distences = self.gate_hypotheses(self.active_hypotheses, z)

        self.active_hypotheses, ass_ind = self.hypotheses_update(gated_inds, m_distences)
        self.hypotheses_prob = self.probabilities_update(ass_ind)

        self.active_filters = self.filter_update(ass_ind, z)

if __name__ == '__main__':
    while not rospy.is_shutdown():     
        try:
            ekf_vision = EKFNode()
            rospy.spin()
        except rospy.ROSInterruptException:
            pass
    
