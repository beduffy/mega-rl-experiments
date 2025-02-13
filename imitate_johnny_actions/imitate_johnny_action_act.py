import os
from datetime import datetime

import torch
import numpy as np
import h5py
import argparse
from torch import nn
from torch.utils.data import Dataset, DataLoader
from collections import OrderedDict

# Instead of defining SequencePolicy, we use ACTPolicy
from act_relevant_files.policy import ACTPolicy

# Define joint order matching the URDF structure
JOINT_ORDER = [
    'r_hip_yaw', 'r_hip_roll', 'r_hip_pitch', 'r_knee', 'r_ank_pitch', 'r_ank_roll',
    'l_hip_yaw', 'l_hip_roll', 'l_hip_pitch', 'l_knee', 'l_ank_pitch', 'l_ank_roll',
    'head_pan', 'head_tilt',
    'r_sho_pitch', 'r_sho_roll', 'r_el_pitch', 'r_el_yaw', 'r_gripper',
    'l_sho_pitch', 'l_sho_roll', 'l_el_pitch', 'l_el_yaw', 'l_gripper'
]

# Hardcoded demonstration data
GREET_ANGLES = torch.tensor([
    0.0, 0.0, 0.7120943226666667, -1.0890854346666667, -0.5864306186666667, 0.0,  # Right leg
    0.0, 0.0, -0.7120943226666667, 1.0890854346666667, 0.5864306186666667, 0.0,   # Left leg
    0.0, 0.0,  # Head
    0.16755160533333335, 1.3823007440000001, 0.0, 1.25663704, 0.0,  # Right arm
    -1.9896753133333334, 0.0, 0.0, -1.8011797573333335, 0.0  # Left arm
], dtype=torch.float32)

all_greet_action_lines = [
    {'l_ank_roll': 0.0, 'r_ank_roll': 0.0, 'l_ank_pitch': 0.5864306186666667, 'r_ank_pitch': -0.5864306186666667, 'l_knee': 1.0890854346666667, 'r_knee': -1.0890854346666667, 'l_hip_pitch': -0.7120943226666667, 'r_hip_pitch': 0.7120943226666667, 'l_hip_roll': 0.0, 'r_hip_roll': 0.0, 'l_hip_yaw': 0.0, 'r_hip_yaw': 0.0, 'l_sho_pitch': 0.16755160533333335, 'r_sho_pitch': -1.9896753133333334, 'l_sho_roll': 1.3823007440000001, 'r_sho_roll': 0.0, 'l_el_pitch': 0.0, 'r_el_pitch': 0.0, 'l_el_yaw': -1.8011797573333335, 'r_el_yaw': 1.25663704, 'l_gripper': 0.0, 'r_gripper': 0.0},
    {'l_ank_roll': 0.0, 'r_ank_roll': 0.0, 'l_ank_pitch': 0.5864306186666667, 'r_ank_pitch': -0.5864306186666667, 'l_knee': 1.0890854346666667, 'r_knee': -1.0890854346666667, 'l_hip_pitch': -0.7120943226666667, 'r_hip_pitch': 0.7120943226666667, 'l_hip_roll': 0.0, 'r_hip_roll': 0.0, 'l_hip_yaw': 0.0, 'r_hip_yaw': 0.0, 'l_sho_pitch': 0.16755160533333335, 'r_sho_pitch': -1.9896753133333334, 'l_sho_roll': 1.3823007440000001, 'r_sho_roll': 0.0, 'l_el_pitch': 0.0, 'r_el_pitch': 0.0, 'l_el_yaw': -1.8011797573333335, 'r_el_yaw': 1.25663704, 'l_gripper': 0.0, 'r_gripper': 0.0},
    {'l_ank_roll': 0.0, 'r_ank_roll': 0.0, 'l_ank_pitch': 0.5864306186666667, 'r_ank_pitch': -0.5864306186666667, 'l_knee': 1.0890854346666667, 'r_knee': -1.0890854346666667, 'l_hip_pitch': -0.7120943226666667, 'r_hip_pitch': 0.7120943226666667, 'l_hip_roll': 0.0, 'r_hip_roll': 0.0, 'l_hip_yaw': 0.0, 'r_hip_yaw': 0.0, 'l_sho_pitch': 0.16755160533333335, 'r_sho_pitch': -1.9896753133333334, 'l_sho_roll': 1.3823007440000001, 'r_sho_roll': 0.0, 'l_el_pitch': 0.0, 'r_el_pitch': 0.0, 'l_el_yaw': -1.8011797573333335, 'r_el_yaw': 1.88495556, 'l_gripper': 0.0, 'r_gripper': 0.0},
    {'l_ank_roll': 0.0, 'r_ank_roll': 0.0, 'l_ank_pitch': 0.5864306186666667, 'r_ank_pitch': -0.5864306186666667, 'l_knee': 1.0890854346666667, 'r_knee': -1.0890854346666667, 'l_hip_pitch': -0.7120943226666667, 'r_hip_pitch': 0.7120943226666667, 'l_hip_roll': 0.0, 'r_hip_roll': 0.0, 'l_hip_yaw': 0.0, 'r_hip_yaw': 0.0, 'l_sho_pitch': 0.16755160533333335, 'r_sho_pitch': -1.9896753133333334, 'l_sho_roll': 1.3823007440000001, 'r_sho_roll': 0.0, 'l_el_pitch': 0.0, 'r_el_pitch': 0.0, 'l_el_yaw': -1.8011797573333335, 'r_el_yaw': 1.25663704, 'l_gripper': 0.0, 'r_gripper': 0.0},
    {'l_ank_roll': 0.0, 'r_ank_roll': 0.0, 'l_ank_pitch': 0.5864306186666667, 'r_ank_pitch': -0.5864306186666667, 'l_knee': 1.0890854346666667, 'r_knee': -1.0890854346666667, 'l_hip_pitch': -0.7120943226666667, 'r_hip_pitch': 0.7120943226666667, 'l_hip_roll': 0.0, 'r_hip_roll': 0.0, 'l_hip_yaw': 0.0, 'r_hip_yaw': 0.0, 'l_sho_pitch': 0.16755160533333335, 'r_sho_pitch': -1.9896753133333334, 'l_sho_roll': 1.3823007440000001, 'r_sho_roll': 0.0, 'l_el_pitch': 0.0, 'r_el_pitch': 0.0, 'l_el_yaw': -1.8011797573333335, 'r_el_yaw': 1.88495556, 'l_gripper': 0.0, 'r_gripper': 0.0},
    {'l_ank_roll': 0.0, 'r_ank_roll': 0.0, 'l_ank_pitch': 0.5864306186666667, 'r_ank_pitch': -0.5864306186666667, 'l_knee': 1.0890854346666667, 'r_knee': -1.0890854346666667, 'l_hip_pitch': -0.7120943226666667, 'r_hip_pitch': 0.7120943226666667, 'l_hip_roll': 0.0, 'r_hip_roll': 0.0, 'l_hip_yaw': 0.0, 'r_hip_yaw': 0.0, 'l_sho_pitch': 0.16755160533333335, 'r_sho_pitch': -1.9896753133333334, 'l_sho_roll': 1.3823007440000001, 'r_sho_roll': 0.0, 'l_el_pitch': 0.0, 'r_el_pitch': 0.0, 'l_el_yaw': -1.8011797573333335, 'r_el_yaw': 1.25663704, 'l_gripper': 0.0, 'r_gripper': 0.0},
    {'l_ank_roll': 0.0, 'r_ank_roll': 0.0, 'l_ank_pitch': 0.5864306186666667, 'r_ank_pitch': -0.5864306186666667, 'l_knee': 1.0890854346666667, 'r_knee': -1.0890854346666667, 'l_hip_pitch': -0.7120943226666667, 'r_hip_pitch': 0.7120943226666667, 'l_hip_roll': 0.0, 'r_hip_roll': 0.0, 'l_hip_yaw': 0.0, 'r_hip_yaw': 0.0, 'l_sho_pitch': 0.16755160533333335, 'r_sho_pitch': -0.16755160533333335, 'l_sho_roll': 1.3823007440000001, 'r_sho_roll': -1.3823007440000001, 'l_el_pitch': 0.0, 'r_el_pitch': 0.0, 'l_el_yaw': -1.8011797573333335, 'r_el_yaw': 1.8011797573333335, 'l_gripper': 0.0, 'r_gripper': 0.0}
]

# Modified dataset class for sequence prediction
class ServoDataset(Dataset):
    """Dataset for sequence prediction with sliding window"""
    def __init__(self, action_sequences, num_samples=1000, window_size=3, image_size=240):
        # Convert each sequence from list of dicts to list of tensors
        self.action_sequences = [
            [self.dict_to_tensor(step) for step in seq] 
            for seq in action_sequences
        ]
        self.window_size = window_size
        self.images = torch.rand(num_samples, 3, image_size, image_size)
        
        # Create sequence targets with proper windowing
        self.targets = []
        for _ in range(num_samples):
            seq_idx = np.random.randint(0, len(self.action_sequences))
            seq = self.action_sequences[seq_idx]
            start = np.random.randint(0, len(seq) - self.window_size + 1)
            window = seq[start:start + self.window_size]
            self.targets.append(torch.stack(window))
        
    def dict_to_tensor(self, action_dict):
        return torch.tensor([
            action_dict.get(name, 0.0)  # Use 0.0 as default for missing joints
            for name in JOINT_ORDER
        ], dtype=torch.float32)
    
    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        """Returns a single sample from the dataset.
        
        For temporal dataset, consecutive indices represent temporal sequence:
        idx:     0  1  2  3  4  5  6  7  8  9 ...
        target:  1  2  3  4  5  6  7  8  9  8 ...
        """
        return self.images[idx], torch.zeros(24), self.targets[idx]  # (image, qpos, sequence_target)


def train(policy, train_loader, num_epochs=50, lr=1e-4, device='cpu'):
    optimizer = torch.optim.Adam(policy.parameters(), lr=lr)
    criterion = nn.MSELoss()
    best_loss = float('inf')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    for epoch in range(num_epochs):
        policy.train()
        total_loss = 0  # Reset each epoch
        joint_errors = {name: 0.0 for name in JOINT_ORDER}
        
        for batch_idx, (images, qpos, targets) in enumerate(train_loader):
            images = images.to(device)
            if images.dim() == 4:
                images = images.unsqueeze(1)  # add camera dimension; now shape (B, 1, C, H, W)
            # If the channel dimension is 1, replicate channels to have 3
            if images.shape[2] == 1:
                images = images.repeat(1, 1, 3, 1, 1)  
            qpos = qpos.to(device)
            targets = targets.to(device)
            
            # For ACTPolicy, we assume the forward signature is (qpos, images)
            preds = policy(qpos, images)
            # Since ACTPolicy predicts a single step (shape: [B, 24]), compare with the first timestep of target sequence
            loss = criterion(preds, targets[:,0,:])
            
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            
            # Calculate per-joint errors
            with torch.no_grad():
                errors = torch.abs(preds - targets[:,0,:]).mean(dim=0)  # Average over batch
                for i, name in enumerate(JOINT_ORDER):
                    joint_errors[name] += errors[i].item()
        
        # Save checkpoint every 10 epochs
        if epoch % 10 == 0:
            ckpt_path = f'checkpoints/policy_epoch{epoch}_{timestamp}.pth'
            torch.save(policy.state_dict(), ckpt_path)
        
        # Print diagnostics
        avg_loss = total_loss / len(train_loader)
        print(f'Epoch {epoch}: Loss: {avg_loss:.6f}')
        
        # Print sample predictions
        with torch.no_grad():
            sample_img, sample_qpos, sample_target = next(iter(train_loader))
            # Ensure sample_img has correct shape [B, num_cam, C, H, W]
            if sample_img.dim() == 4:
                sample_img = sample_img.unsqueeze(1)
            if sample_img.shape[2] == 1:
                sample_img = sample_img.repeat(1, 1, 3, 1, 1)
            sample_pred = policy(sample_qpos[:1].to(device), sample_img[:1].to(device))

            print("\nSample prediction vs target (first timestep):")
            for j in range(5):  # First 5 joints
                name = JOINT_ORDER[j]
                pred_val = sample_pred[0,j].item()
                target_val = sample_target[0,0,j].item()
                error_val = abs(pred_val - target_val)
                print(f"  {name:15}: Pred: {pred_val:.5f} vs Target: {target_val:.5f} (err: {error_val:.5f})")

        # Update best model
        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save(policy.state_dict(), f'best_policy_{timestamp}.pth')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_path', type=str, default='',  # Keep argument but don't use it
                      help='Not used, preserved for compatibility')
    parser.add_argument('--num_epochs', type=int, default=500,
                      help='Number of training epochs')
    parser.add_argument('--batch_size', type=int, default=32,
                      help='Training batch size')
    parser.add_argument('--lr', type=float, default=1e-4,
                      help='Learning rate')
    parser.add_argument('--device', type=str, default='cpu',
                      choices=['cpu', 'cuda'], 
                      help='Device to train on (cpu or cuda)')
    args = parser.parse_args()
    
    # Set device
    device = torch.device(args.device)
    print(f"Training on {device}")
    
    # Create synthetic dataset
    greet_sequences = [all_greet_action_lines]  # Can add more sequences
    dataset = ServoDataset(action_sequences=greet_sequences, num_samples=1000)
    train_loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)
    
    # Configure ACTPolicy to mimic the original SequencePolicy behavior
    policy_config = {
        'num_queries': 1,
        'kl_weight': 1,
        'task_name': 'imitate_johnny_act',
        'device': args.device,
        'num_actions': 24,
        'state_dim': 24,
        'hidden_dim': 512,
        'dim_feedforward': 3200,
        'lr_backbone': 1e-5,
        'backbone': 'resnet18',
        'enc_layers': 2,
        'dec_layers': 2,
        'nheads': 8,
        'dropout': 0.1,
        'camera_names': ['dummy'],
    }
    
    policy = ACTPolicy(policy_config).to(device)
    
    train(policy, train_loader, num_epochs=args.num_epochs, lr=args.lr, device=device)
    
    # Save trained policy with timestamp and epochs
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    save_path = f'servo_policy_24dof_{timestamp}_ep{args.num_epochs}.pth'
    torch.save(policy.state_dict(), save_path)


if __name__ == '__main__':
    main() 