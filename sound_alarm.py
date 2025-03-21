import pyaudio
import numpy as np
import time
import threading
import subprocess
import os

class SoundLevelAlarm:
    def __init__(self, threshold_db=70, sample_rate=44100, chunk_size=1024, 
                 update_interval=0.5, alarm_duration=1.0):
        """
        Initialize a sound level alarm.
        
        Parameters:
        - threshold_db: The dB threshold that triggers the alarm
        - sample_rate: Audio sampling rate
        - chunk_size: Number of audio frames per buffer
        - update_interval: How often to check sound levels (seconds)
        - alarm_duration: How long the alarm sounds (seconds)
        """
        self.threshold_db = threshold_db
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.update_interval = update_interval
        self.alarm_duration = alarm_duration
        
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.running = False
        self.current_db = 0
        
    def start_monitoring(self):
        """Start monitoring sound levels."""
        self.running = True
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )
        
        # Start monitoring in a separate thread
        monitor_thread = threading.Thread(target=self._monitor_loop)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        print(f"Monitoring started. Alarm will trigger above {self.threshold_db} dB")
        return monitor_thread
        
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            self.current_db = self._get_db_level()
            print(f"Current sound level: {self.current_db:.1f} dB")
            
            if self.current_db > self.threshold_db:
                print(f"ALARM! Sound level ({self.current_db:.1f} dB) exceeded threshold ({self.threshold_db} dB)")
                self._trigger_alarm()
                
            time.sleep(self.update_interval)
    
    def _get_db_level(self):
        """Measure current dB level."""
        try:
            # Read audio data
            data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            # Convert to numpy array
            audio_data = np.frombuffer(data, dtype=np.int16)
            
            # Compute RMS value
            rms = np.sqrt(np.mean(np.square(audio_data)))
            # Avoid log(0) errors
            if rms < 1:
                rms = 1
                
            # Convert to dB
            # Using reference of 1 as the maximum value for int16 (32767)
            db = 20 * np.log10(rms / 32767)
            
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
            # First try using paplay (PulseAudio)
            subprocess.call(['paplay', '--volume=65536', '/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga'], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
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
    
    # Create alarm with 70dB threshold (adjust based on your environment)
    alarm = SoundLevelAlarm(threshold_db=70)
    
    try:
        # Start monitoring
        monitor_thread = alarm.start_monitoring()
        
        # Run for a period or until keyboard interrupt
        while True:
            command = input("\nEnter command (q=quit, t=change threshold): ")
            if command.lower() == 'q':
                break
            elif command.lower().startswith('t'):
                try:
                    new_threshold = float(command[1:].strip())
                    alarm.set_threshold(new_threshold)
                except:
                    print("Invalid threshold format. Example: t75")
    
    except KeyboardInterrupt:
        print("\nProgram interrupted.")
    
    finally:
        # Clean up
        alarm.stop_monitoring()
        print("Program ended.")