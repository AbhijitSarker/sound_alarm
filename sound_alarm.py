import pyaudio
import numpy as np
import time
import threading
import subprocess
import os

class SoundLevelAlarm:
    def __init__(self, threshold_db=70, sample_rate=44100, chunk_size=1024, 
                 update_interval=0.5, alarm_duration=1.0, input_device=None, output_device=None,
                 cooldown_time=3.0):
        """
        Initialize a sound level alarm.
        
        Parameters:
        - threshold_db: The dB threshold that triggers the alarm
        - sample_rate: Audio sampling rate
        - chunk_size: Number of audio frames per buffer
        - update_interval: How often to check sound levels (seconds)
        - alarm_duration: How long the alarm sounds (seconds)
        - input_device: Index of input device to use (None = default)
        - output_device: Index of output device to use (None = default)
        - cooldown_time: Time in seconds to wait before triggering another alarm
        """
        self.threshold_db = threshold_db
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.update_interval = update_interval
        self.alarm_duration = alarm_duration
        self.input_device = input_device
        self.output_device = output_device
        self.cooldown_time = cooldown_time
        
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.running = False
        self.current_db = 0
        self.last_alarm_time = 0
        
    def start_monitoring(self):
        """Start monitoring sound levels."""
        self.running = True
        try:
            self.stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.input_device,
                frames_per_buffer=self.chunk_size
            )
            
            # Start monitoring in a separate thread
            monitor_thread = threading.Thread(target=self._monitor_loop)
            monitor_thread.daemon = True
            monitor_thread.start()
            
            print(f"Monitoring started. Alarm will trigger above {self.threshold_db} dB")
            return monitor_thread
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            print("Try selecting a different input device.")
            self.running = False
            return None
        
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            self.current_db = self._get_db_level()
            print(f"Current sound level: {self.current_db:.1f} dB")
            
            current_time = time.time()
            time_since_last_alarm = current_time - self.last_alarm_time
            
            if self.current_db > self.threshold_db and time_since_last_alarm > self.cooldown_time:
                print(f"ALARM! Sound level ({self.current_db:.1f} dB) exceeded threshold ({self.threshold_db} dB)")
                self._trigger_alarm()
                self.last_alarm_time = current_time
                
            time.sleep(self.update_interval)
    
    def _get_db_level(self):
        """Measure current dB level."""
        try:
            # Read audio data
            data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            # Convert to numpy array
            audio_data = np.frombuffer(data, dtype=np.int16)
            
            # Compute RMS value with error handling
            # Add small epsilon to prevent invalid value in sqrt
            square_sum = np.mean(np.square(audio_data))
            if square_sum <= 0:
                return 0  # Return zero dB for silent input
                
            rms = np.sqrt(square_sum)
                
            # Convert to dB
            # Using reference of 1 as the maximum value for int16 (32767)
            db = 20 * np.log10(max(rms, 1) / 32767)
            
            # dB values will be negative (since reference is max value)
            # Convert to positive scale for easier understanding
            db_positive = 96 + db  # Adding 96 makes typical quiet room ~30-40dB
            
            return max(0, db_positive)  # Prevent negative values
        except Exception as e:
            print(f"Error measuring sound level: {e}")
            return 0
    
    def _trigger_alarm(self):
        """Trigger the alarm sound for Linux systems."""
        try:
            # First try using paplay (PulseAudio) with device selection
            cmd = ['paplay', '--volume=65536']
            
            # Add output device parameter if specified
            if self.output_device is not None:
                device_name = self.get_pulse_device_name(self.output_device)
                if device_name:
                    cmd.extend(['-d', device_name])
            
            cmd.append('/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga')
            
            subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            try:
                # Try using SoX if paplay is not available
                subprocess.call(['play', '-q', '-n', 'synth', str(self.alarm_duration), 
                               'sine', '1000', 'vol', '0.7'],
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL)
            except:
                # Fall back to console bell if neither method works
                print('\a')
    
    def get_pulse_device_name(self, device_index):
        """Convert PyAudio device index to PulseAudio device name"""
        try:
            device_info = self.p.get_device_info_by_index(device_index)
            return device_info.get('name')
        except:
            return None
    
    def stop_monitoring(self):
        """Stop monitoring sound levels."""
        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()
        print("Monitoring stopped.")
    
    def set_threshold(self, new_threshold):
        """Change the dB threshold."""
        self.threshold_db = new_threshold
        print(f"Threshold updated to {self.threshold_db} dB")
        
    def set_cooldown(self, new_cooldown):
        """Change the cooldown time between alarms."""
        self.cooldown_time = float(new_cooldown)
        print(f"Cooldown time updated to {self.cooldown_time} seconds")
        
    def calculate_ambient_noise(self, duration=5.0):
        """Measure the ambient noise level for a period of time."""
        if not self.stream:
            print("Error: Audio stream not active")
            return None
            
        print(f"Measuring ambient noise for {duration} seconds...")
        start_time = time.time()
        db_values = []
        
        while time.time() - start_time < duration:
            db = self._get_db_level()
            if db > 0:  # Filter out error readings
                db_values.append(db)
            time.sleep(0.1)
        
        if not db_values:
            print("Error: Could not measure ambient noise")
            return None
            
        avg_db = sum(db_values) / len(db_values)
        print(f"Ambient noise level: {avg_db:.1f} dB")
        return avg_db

def list_audio_devices():
    """List all available audio input and output devices."""
    p = pyaudio.PyAudio()
    
    print("\n=== Available Audio Devices ===")
    print("ID\tInput/Output\tDevice Name")
    print("-" * 50)
    
    input_devices = []
    output_devices = []
    
    for i in range(p.get_device_count()):
        device_info = p.get_device_info_by_index(i)
        name = device_info.get('name')
        
        # Check if it's an input device
        if device_info.get('maxInputChannels') > 0:
            input_devices.append((i, name))
            print(f"{i}\tInput\t\t{name}")
        
        # Check if it's an output device
        if device_info.get('maxOutputChannels') > 0:
            output_devices.append((i, name))
            print(f"{i}\tOutput\t\t{name}")
    
    p.terminate()
    print("-" * 50)
    
    return input_devices, output_devices

# Example usage
if __name__ == "__main__":
    # Check for necessary packages
    missing_packages = []
    
    # Try to check for PulseAudio
    try:
        subprocess.call(['paplay', '--version'], 
                       stdout=subprocess.DEVNULL, 
                       stderr=subprocess.DEVNULL)
    except:
        missing_packages.append("pulseaudio or pulseaudio-utils")
    
    # Try to check for SoX
    try:
        subprocess.call(['play', '--version'], 
                       stdout=subprocess.DEVNULL, 
                       stderr=subprocess.DEVNULL)
    except:
        missing_packages.append("sox")
    
    if missing_packages:
        print("Note: For best alarm sounds, consider installing these packages:")
        print("sudo apt-get install " + " ".join(missing_packages))
        print("Continuing with console bell as fallback...\n")
    
    # List available devices
    input_devices, output_devices = list_audio_devices()
    
    # Default to None (system default) if no selection is made
    selected_input = None
    selected_output = None
    
    # Allow user to select input device
    if input_devices:
        try:
            select_input = input("\nSelect input device ID (or press Enter for default): ").strip()
            if select_input:
                selected_input = int(select_input)
                print(f"Selected input device: {next((name for id, name in input_devices if id == selected_input), 'Unknown')}")
        except ValueError:
            print("Invalid input device ID, using default")
    
    # Allow user to select output device
    if output_devices:
        try:
            select_output = input("Select output device ID (or press Enter for default): ").strip()
            if select_output:
                selected_output = int(select_output)
                print(f"Selected output device: {next((name for id, name in output_devices if id == selected_output), 'Unknown')}")
        except ValueError:
            print("Invalid output device ID, using default")
    
    # Set threshold
    try:
        threshold_input = input("Enter dB threshold (or press Enter for default 70dB): ").strip()
        threshold = float(threshold_input) if threshold_input else 70
    except ValueError:
        print("Invalid threshold value, using default 70dB")
        threshold = 70
        
    # Set cooldown time
    try:
        cooldown_input = input("Enter cooldown time between alarms in seconds (or press Enter for default 3s): ").strip()
        cooldown = float(cooldown_input) if cooldown_input else 3.0
    except ValueError:
        print("Invalid cooldown value, using default 3 seconds")
        cooldown = 3.0
    
    # Create alarm with selected devices
    alarm = SoundLevelAlarm(
        threshold_db=threshold,
        input_device=selected_input,
        output_device=selected_output,
        cooldown_time=cooldown
    )
    
    try:
        # Start monitoring
        monitor_thread = alarm.start_monitoring()
        if not monitor_thread:
            print("Failed to start monitoring. Exiting.")
            exit(1)
            
        # Option to calibrate based on ambient noise
        calibrate = input("Would you like to calibrate based on ambient noise? (y/n): ").lower().strip()
        if calibrate == 'y':
            ambient_db = alarm.calculate_ambient_noise(5.0)
            if ambient_db:
                suggested_threshold = ambient_db + 10
                set_to_suggested = input(f"Set threshold to {suggested_threshold:.1f} dB? (y/n): ").lower().strip()
                if set_to_suggested == 'y':
                    alarm.set_threshold(suggested_threshold)
        
        # Run for a period or until keyboard interrupt
        print("\nCommands:")
        print("  q - Quit")
        print("  t<number> - Change threshold (e.g., t75)")
        print("  c<number> - Change cooldown time in seconds (e.g., c5)")
        print("  a - Measure ambient noise and suggest threshold")
        
        while True:
            command = input("\nEnter command: ")
            if command.lower() == 'q':
                break
            elif command.lower().startswith('t'):
                try:
                    new_threshold = float(command[1:].strip())
                    alarm.set_threshold(new_threshold)
                except:
                    print("Invalid threshold format. Example: t75")
            elif command.lower().startswith('c'):
                try:
                    new_cooldown = float(command[1:].strip())
                    alarm.set_cooldown(new_cooldown)
                except:
                    print("Invalid cooldown format. Example: c5")
            elif command.lower() == 'a':
                ambient_db = alarm.calculate_ambient_noise(5.0)
                if ambient_db:
                    suggested_threshold = ambient_db + 10
                    print(f"Suggested threshold: {suggested_threshold:.1f} dB")
                    set_to_suggested = input(f"Set threshold to {suggested_threshold:.1f} dB? (y/n): ").lower().strip()
                    if set_to_suggested == 'y':
                        alarm.set_threshold(suggested_threshold)
    
    except KeyboardInterrupt:
        print("\nProgram interrupted.")
    
    finally:
        # Clean up
        alarm.stop_monitoring()
        print("Program ended.")