import argparse
import time
from datetime import datetime

import torch
import pybullet as p
import pybullet_data
import numpy as np


# from imitate_johnny_actions.imitate_johnny_action import SimplePolicy, JOINT_ORDER
from imitate_johnny_action import SimplePolicy, JOINT_ORDER


def load_policy(checkpoint_path, device='cpu'):
    """Load trained policy from checkpoint"""
    policy = SimplePolicy(image_size=240, use_qpos=True, qpos_dim=24)
    checkpoint = torch.load(checkpoint_path, map_location=device)
    policy.load_state_dict(checkpoint)
    policy.eval()
    return policy


def get_camera_image(robot, width=240, height=240):
    """Get robot's camera view for policy input"""
    # Camera position on robot's head (adjust these values based on your URDF)
    head_link = [i for i in range(p.getNumJoints(robot)) 
                if p.getJointInfo(robot, i)[1].decode() == 'head_tilt'][0]
    
    # Get camera position and orientation
    head_pos = p.getLinkState(robot, head_link)[0]
    head_orn = p.getLinkState(robot, head_link)[1]
    rot_matrix = p.getMatrixFromQuaternion(head_orn)
    forward_vec = np.array(rot_matrix[6:9])
    up_vec = np.array(rot_matrix[3:6])
    
    # Camera parameters
    view_matrix = p.computeViewMatrix(
        head_pos + forward_vec * 0.1,  # Camera position (slightly in front of head)
        head_pos + forward_vec * 2.0,  # Look at point
        up_vec
    )
    proj_matrix = p.computeProjectionMatrixFOV(
        fov=60, aspect=1.0, nearVal=0.1, farVal=10.0
    )
    
    # Render image
    _, _, rgb, _, _ = p.getCameraImage(
        width=width, height=height,
        viewMatrix=view_matrix,
        projectionMatrix=proj_matrix,
        renderer=p.ER_BULLET_HARDWARE_OPENGL
    )
    
    # Convert to tensor and normalize
    image = torch.from_numpy(rgb[..., :3].transpose(2, 0, 1)).float() / 255.0
    return image.unsqueeze(0)  # Add batch dimension


def set_joint_angles_instantly(robot, angle_dict_to_try):
    # Enable motor control for all joints
    num_joints = p.getNumJoints(robot)
    for joint_idx in range(num_joints):
        joint_info = p.getJointInfo(robot, joint_idx)
        # print(joint_info)
        joint_name = joint_info[1].decode('utf-8')
        joint_type = joint_info[2]  # Get joint type
        
        # Set 0 position for all joints. Only control revolute and prismatic joints.
        # if joint_type in [p.JOINT_REVOLUTE]:
        #     p.setJointMotorControl2(robot, joint_idx, 
        #                            controlMode=p.POSITION_CONTROL,
        #                            targetPosition=0,  # Radians for revolute, meters for prismatic
        #                            force=100)  # Maximum force in Newtons

        # TODO make head tilt and head pan to move
        if joint_name in angle_dict_to_try and joint_type in [p.JOINT_REVOLUTE] and joint_name not in ['head_tilt', 'head_pan']:
            p.setJointMotorControl2(robot, joint_idx, 
                                controlMode=p.POSITION_CONTROL,
                                targetPosition=angle_dict_to_try[joint_name],  # Radians for revolute, meters for prismatic
                                force=100)  # Maximum force in Newtons

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=str, required=True,
                      help='Path to trained policy checkpoint')
    parser.add_argument('--device', type=str, default='cpu',
                      choices=['cpu', 'cuda'], help='Device to run policy on')
    args = parser.parse_args()

    # Load policy
    policy = load_policy(args.checkpoint, device=args.device).to(args.device)
    
    
    physicsClient = p.connect(p.GUI)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    # p.setGravity(0, 0, 0)

    p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 1, lightPosition=[1, 1, 1])
    planeId = p.loadURDF("plane.urdf")

    # Load robot URDF
    use_fixed_base = False
    use_fixed_base = True
    robot = p.loadURDF("/home/ben/all_projects/ainex_private_ws/ainex_private/src/ainex_simulations/ainex_description/urdf/ainex.urdf", [0, 0, 0.25], useFixedBase=use_fixed_base)  # Start above ground

    # Modified simulation loop
    last_time = time.time()
    while True:
        current_time = time.time()
        dt = current_time - last_time
        last_time = current_time

        # Get current observations
        image = get_camera_image(robot).to(args.device)
        qpos = torch.zeros(1, 24).to(args.device)  # Replace with actual qpos if available
        
        # Run policy
        with torch.no_grad():
            target_angles = policy(image, qpos).cpu().numpy()[0]
        
        # Convert policy output to joint dictionary
        joint_targets = {name: target_angles[i] for i, name in enumerate(JOINT_ORDER)}
        
        # Apply to simulation
        set_joint_angles_instantly(robot, joint_targets)
        
        p.stepSimulation()
        time.sleep(1./240.)  # Maintain physics timestep 