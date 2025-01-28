import os
import time
import numpy as np
import torch
import cv2
import pyautogui
from torch import nn
from torch.utils.data import Dataset, DataLoader
from collections import deque
import h5py
from datetime import datetime

class MouseRecorder:
    """Records mouse movements and screen content"""
    def __init__(self, screen_region=(0, 0, 1920, 1080), history_length=3):
        self.screen_region = screen_region
        self.history = deque(maxlen=history_length)
        self.recording = False
        self.data = {
            'images': [],
            'positions': [],
            'timestamps': []
        }
        
    def start_recording(self):
        self.recording = True
        self.data = {'images': [], 'positions': [], 'timestamps': []}
        
    def stop_recording(self):
        self.recording = False
        
    def capture_frame(self):
        if not self.recording:
            return
            
        # Capture screen
        img = pyautogui.screenshot(region=self.screen_region)
        img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        img = cv2.resize(img, (240, 240))
        
        # Store in history
        self.history.append(img)
        
        # Only save when history is full
        if len(self.history) == self.history.maxlen:
            self.data['images'].append(np.stack(self.history))
            self.data['positions'].append(pyautogui.position())
            self.data['timestamps'].append(time.time())

def circular_mouse_controller(radius=300, speed=2, duration=10):
    """Scripted mouse controller that moves in circles"""
    recorder = MouseRecorder()
    recorder.start_recording()
    
    start_time = time.time()
    center_x, center_y = pyautogui.size().width//2, pyautogui.size().height//2
    
    try:
        while time.time() - start_time < duration:
            angle = (time.time() - start_time) * speed
            x = center_x + int(radius * np.cos(angle))
            y = center_y + int(radius * np.sin(angle))
            pyautogui.moveTo(x, y, duration=0.01)
            recorder.capture_frame()
            time.sleep(0.01)
    finally:
        recorder.stop_recording()
        return recorder.data

class MousePolicy(nn.Module):
    """CNN that predicts mouse position from screen content"""
    def __init__(self):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(9, 32, 3, stride=2),  # Increased channels
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.Conv2d(32, 64, 3, stride=2),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((7, 7)),  # Spatial pyramid
            nn.Flatten(),
            nn.Linear(64*7*7, 512),
            nn.Dropout(0.5),
            nn.ReLU(),
            nn.Linear(512, 2),
            nn.Sigmoid()  # Output normalized coordinates
        )
        
    def forward(self, x):
        return self.cnn(x)


class MouseDataset(Dataset):
    def __init__(self, recordings, image_size=240, screen_size=(1920, 1080)):
        self.images = torch.from_numpy(np.array(recordings['images'])).float() / 255.0
        # Normalize positions to [0,1] range
        self.positions = torch.tensor(recordings['positions'], dtype=torch.float32)
        self.positions[:, 0] /= screen_size[0]  # Normalize X
        self.positions[:, 1] /= screen_size[1]  # Normalize Y
        
    def __len__(self):
        return len(self.images)
    
    def __getitem__(self, idx):
        # Get sequence of frames [T, H, W, C]
        frames = self.images[idx]
        # Merge temporal and channel dimensions [T*C, H, W]
        merged = frames.permute(0, 3, 1, 2)  # [T, C, H, W]
        merged = merged.reshape(-1, merged.shape[2], merged.shape[3])  # [T*C, H, W]
        return merged, self.positions[idx]


def train_mouse_policy(data_path='mouse_demo.hdf5', num_epochs=50):
    # Load recorded data
    with h5py.File(data_path, 'r') as f:
        recordings = {
            'images': f['images'][:],
            'positions': f['positions'][:]
        }
    
    dataset = MouseDataset(recordings)
    loader = DataLoader(dataset, batch_size=32, shuffle=True)
    
    # Initialize model and training
    policy = MousePolicy()
    optimizer = torch.optim.Adam(policy.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'min', patience=3)
    criterion = nn.MSELoss()
    
    # Get sample batch for diagnostics
    sample_images, sample_targets = next(iter(loader))
    
    for epoch in range(num_epochs):
        total_loss = 0
        policy.train()
        
        for images, targets in loader:
            optimizer.zero_grad()
            outputs = policy(images)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            
        # Print diagnostics
        avg_loss = total_loss/len(loader)
        print(f"\nEpoch {epoch} Loss: {avg_loss:.4f}")
        
        with torch.no_grad():
            policy.eval()
            preds = policy(sample_images[:5])  # First 5 samples
            print("Sample Predictions vs Targets:")
            for i, (pred, target) in enumerate(zip(preds, sample_targets[:5])):
                pred_x, pred_y = pred.tolist()
                target_x, target_y = target.tolist()
                print(f"  Sample {i}:")
                print(f"    X: {pred_x:7.10f} (pred) vs {target_x:7.10f} (target)")
                print(f"    Y: {pred_y:7.10f} (pred) vs {target_y:7.10f} (target)")
                print(f"    Total Error: {((pred_x-target_x)**2 + (pred_y-target_y)**2)**0.5:.10f}px")
        
        scheduler.step(avg_loss)  # Update learning rate

    # Save trained model
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    torch.save(policy.state_dict(), f"mouse_policy_{timestamp}.pth")


def run_policy(policy_path):
    """Run trained policy to generate mouse movements"""
    policy = MousePolicy()
    policy.load_state_dict(torch.load(policy_path))
    policy.eval()
    
    recorder = MouseRecorder()
    recorder.start_recording() 
    
    try:
        while True:
            recorder.capture_frame()
            print('got frame')
            if len(recorder.history) < recorder.history.maxlen:
                print('not enough frames')
                continue
                
            # Prepare input tensor matching training format
            current_frame = np.stack(recorder.history)  # [T, H, W, C]
            input_tensor = torch.from_numpy(current_frame).float()/255.0
            input_tensor = input_tensor.permute(0, 3, 1, 2)  # [T, C, H, W]
            input_tensor = input_tensor.reshape(-1, input_tensor.shape[2], input_tensor.shape[3])  # [T*C, H, W]
            input_tensor = input_tensor.unsqueeze(0)  # Add batch dimension
            
            # Get prediction and denormalize
            with torch.no_grad():
                pred_normalized = policy(input_tensor)[0].numpy()
            pred_x = int(pred_normalized[0] * 1920)
            pred_y = int(pred_normalized[1] * 1080)
            
            print(f'Moving to ({pred_x}, {pred_y})')
            pyautogui.moveTo(pred_x, pred_y, duration=0.01)
            
    except KeyboardInterrupt:
        print("Stopping policy execution")


if __name__ == "__main__":
    # # To record demonstration:
    # demo_data = circular_mouse_controller(duration=60)
    # with h5py.File('mouse_demo.hdf5', 'w') as f:
    #     f.create_dataset('images', data=demo_data['images'])
    #     f.create_dataset('positions', data=demo_data['positions'])
    
    # To train:
    # train_mouse_policy(num_epochs=50)
    
    # To run (use latest policy):
    run_policy("mouse_policy_20250128_102830.pth")