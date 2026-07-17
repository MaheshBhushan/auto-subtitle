import os
import re
import wave
import pyaudio
import tempfile
import threading
import subprocess
from datetime import datetime


def _list_dshow_devices():
    """Return (video_names, audio_names) reported by ffmpeg's dshow input (Windows)."""
    result = subprocess.run(
        ['ffmpeg', '-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
        stderr=subprocess.PIPE, text=True
    )
    video, audio = [], []
    for line in result.stderr.splitlines():
        match = re.search(r'"(.+)" \((video|audio)\)', line)
        if match:
            (video if match.group(2) == 'video' else audio).append(match.group(1))
    return video, audio


def _dshow_device_name(kind, index):
    """Resolve a device index to a dshow device name (Windows)."""
    video, audio = _list_dshow_devices()
    devices = video if kind == 'video' else audio
    if not devices:
        raise RuntimeError(f"No {kind} capture devices found.")
    if index >= len(devices):
        raise RuntimeError(
            f"{kind} device index {index} is out of range; "
            f"available devices: {', '.join(devices)}"
        )
    return devices[index]


def _stop_ffmpeg(process):
    """Ask ffmpeg to finish writing the output file, escalating if it hangs."""
    try:
        process.stdin.write(b'q')
        process.stdin.close()
        process.wait(timeout=10)
    except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class AudioRecorder:
    def __init__(self, output_dir=None, format=pyaudio.paInt16, channels=1, rate=16000, chunk=1024):
        """
        Initialize the audio recorder with the specified parameters.

        Args:
            output_dir: Directory to save recordings (default: temp directory)
            format: Audio format (default: 16-bit int)
            channels: Number of audio channels (default: 1 for mono)
            rate: Sample rate in Hz (default: 16000, which works well with Whisper)
            chunk: Number of frames per buffer (default: 1024)
        """
        self.format = format
        self.channels = channels
        self.rate = rate
        self.chunk = chunk
        self.output_dir = output_dir if output_dir else tempfile.gettempdir()
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.frames = []
        self.is_recording = False
        self.output_file = None
        self._thread = None

    def start_recording(self, device_index=None):
        """
        Start recording audio in a background thread.

        Args:
            device_index: PyAudio input device index (default: system default device)
        """
        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.chunk
        )

        self.frames = []
        self.is_recording = True
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        print("Recording started...")

    def _record_loop(self):
        while self.is_recording:
            try:
                data = self.stream.read(self.chunk, exception_on_overflow=False)
            except OSError:
                break
            self.frames.append(data)

    def stop_recording(self):
        """Stop recording and save the audio file. Returns None if nothing was recorded."""
        self.is_recording = False

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if not self.frames:
            print("No audio was captured; nothing to save.")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_file = os.path.join(self.output_dir, f"recording_{timestamp}.wav")

        # Save the recorded audio to a WAV file
        with wave.open(self.output_file, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.rate)
            wf.writeframes(b''.join(self.frames))

        print(f"Recording saved to {self.output_file}")
        return self.output_file

    def close(self):
        """Close the PyAudio instance"""
        self.audio.terminate()

    def __del__(self):
        """Ensure resources are cleaned up"""
        if getattr(self, 'audio', None) is not None:
            self.close()


class VideoRecorder:
    def __init__(self, output_dir=None, fps=30, resolution="1280x720"):
        """
        Initialize the video recorder with the specified parameters.

        Args:
            output_dir: Directory to save recordings (default: temp directory)
            fps: Frames per second (default: 30)
            resolution: Video resolution (default: 1280x720)
        """
        self.output_dir = output_dir if output_dir else tempfile.gettempdir()
        self.fps = fps
        self.resolution = resolution
        self.process = None
        self.output_file = None
        self.is_recording = False

    def start_recording(self, device_index=0):
        """
        Start recording video from the specified device.

        Args:
            device_index: Index of the video capture device (default: 0 for default camera)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_file = os.path.join(self.output_dir, f"video_{timestamp}.mp4")

        # Command to start recording with ffmpeg
        if os.name == 'nt':  # Windows
            device_name = _dshow_device_name('video', device_index)
            command = [
                'ffmpeg',
                '-f', 'dshow',
                '-i', f'video={device_name}',
                '-r', str(self.fps),
                '-s', self.resolution,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-y',
                self.output_file
            ]
        else:  # Linux/Mac
            command = [
                'ffmpeg',
                '-f', 'v4l2',
                '-i', f'/dev/video{device_index}',
                '-r', str(self.fps),
                '-s', self.resolution,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-y',
                self.output_file
            ]

        # Start the ffmpeg process
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        self.is_recording = True
        print("Video recording started...")

    def stop_recording(self):
        """Stop recording video"""
        if self.process and self.is_recording:
            _stop_ffmpeg(self.process)
            self.is_recording = False
            if not os.path.exists(self.output_file) or os.path.getsize(self.output_file) == 0:
                print("Video recording failed: ffmpeg did not produce an output file.")
                return None
            print(f"Video recording saved to {self.output_file}")
            return self.output_file
        return None


class AudioVideoRecorder:
    def __init__(self, output_dir=None, fps=30, resolution="1280x720"):
        """
        Initialize a combined audio and video recorder.

        Args:
            output_dir: Directory to save recordings (default: temp directory)
            fps: Frames per second (default: 30)
            resolution: Video resolution (default: 1280x720)
        """
        self.output_dir = output_dir if output_dir else tempfile.gettempdir()
        self.fps = fps
        self.resolution = resolution
        self.process = None
        self.output_file = None
        self.is_recording = False

    def start_recording(self, video_device_index=0, audio_device_index=None):
        """
        Start recording audio and video from the specified devices.

        Args:
            video_device_index: Index of the video capture device (default: 0)
            audio_device_index: Index of the audio capture device (default: system default)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_file = os.path.join(self.output_dir, f"recording_{timestamp}.mp4")

        # Command to start recording with ffmpeg
        if os.name == 'nt':  # Windows
            video_name = _dshow_device_name('video', video_device_index)
            audio_name = _dshow_device_name('audio', audio_device_index or 0)
            command = [
                'ffmpeg',
                '-f', 'dshow',
                '-i', f'video={video_name}:audio={audio_name}',
                '-r', str(self.fps),
                '-s', self.resolution,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-preset', 'ultrafast',
                '-y',
                self.output_file
            ]
        else:  # Linux/Mac
            audio_input = 'default' if audio_device_index is None else f'hw:{audio_device_index}'
            command = [
                'ffmpeg',
                '-f', 'v4l2',
                '-i', f'/dev/video{video_device_index}',
                '-f', 'alsa',
                '-i', audio_input,
                '-r', str(self.fps),
                '-s', self.resolution,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-preset', 'ultrafast',
                '-y',
                self.output_file
            ]

        # Start the ffmpeg process
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        self.is_recording = True
        print("Audio and video recording started...")

    def stop_recording(self):
        """Stop recording audio and video"""
        if self.process and self.is_recording:
            _stop_ffmpeg(self.process)
            self.is_recording = False
            if not os.path.exists(self.output_file) or os.path.getsize(self.output_file) == 0:
                print("Recording failed: ffmpeg did not produce an output file.")
                return None
            print(f"Recording saved to {self.output_file}")
            return self.output_file
        return None

    def list_devices(self):
        """List available audio and video devices"""
        if os.name == 'nt':  # Windows
            video, audio = _list_dshow_devices()
            print("Video devices:")
            for i, name in enumerate(video):
                print(f"  {i}: {name}")
            print("Audio devices:")
            for i, name in enumerate(audio):
                print(f"  {i}: {name}")
        else:  # Linux/Mac
            print("Video devices:")
            try:
                result = subprocess.run(['v4l2-ctl', '--list-devices'],
                                        stdout=subprocess.PIPE, text=True)
                print(result.stdout)
            except FileNotFoundError:
                import glob
                for device in sorted(glob.glob('/dev/video*')):
                    print(f"  {device}")
            print("Audio devices:")
            try:
                result = subprocess.run(['arecord', '-l'],
                                        stdout=subprocess.PIPE, text=True)
                print(result.stdout)
            except FileNotFoundError:
                print("  (install alsa-utils to list audio devices)")
