from setuptools import setup, find_packages

setup(
    version="1.0",
    name="auto_subtitle",
    packages=find_packages(),
    author="Miguel Piedrafita",
    install_requires=[
        'openai-whisper',
        'ffmpeg-python',
        'openai',
        'pyaudio',
    ],
    description="Automatically generate and embed subtitles into your videos, record meetings, and generate meeting minutes",
    entry_points={
        'console_scripts': ['auto_subtitle=auto_subtitle.cli:main'],
    },
    include_package_data=True,
)
