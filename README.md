# Automatic subtitles in your videos

This repository uses `ffmpeg` and [OpenAI's Whisper](https://openai.com/blog/whisper) to automatically generate and overlay subtitles on any video. It also provides functionality to record meetings and generate meeting minutes using AI.

## Features

- Generate and overlay subtitles on videos
- Record audio and video from your devices
- Transcribe recordings automatically
- Generate meeting minutes from subtitles using AI

## Installation

To get started, you'll need Python 3.7 or newer. Install the binary by running the following command:

    pip install git+https://github.com/m1guelpf/auto-subtitle.git

You'll also need to install [`ffmpeg`](https://ffmpeg.org/), which is available from most package managers:

```bash
# on Ubuntu or Debian
sudo apt update && sudo apt install ffmpeg

# on MacOS using Homebrew (https://brew.sh/)
brew install ffmpeg

# on Windows using Chocolatey (https://chocolatey.org/)
choco install ffmpeg
```

For the meeting minutes generation feature, you'll need an OpenAI API key. You can set it as an environment variable:

```bash
# on Linux/Mac
export OPENAI_API_KEY=your_api_key_here

# on Windows
set OPENAI_API_KEY=your_api_key_here
```

## Usage

### Generating Subtitles

The following command will generate a `subtitled/video.mp4` file containing the input video with overlayed subtitles.

    auto_subtitle subtitle /path/to/video.mp4 -o subtitled/

The default setting (which selects the `small` model) works well for transcribing English. You can optionally use a bigger model for better results (especially with other languages). The available models are `tiny`, `tiny.en`, `base`, `base.en`, `small`, `small.en`, `medium`, `medium.en`, `large`.

    auto_subtitle subtitle /path/to/video.mp4 --model medium

Adding `--task translate` will translate the subtitles into English:

    auto_subtitle subtitle /path/to/video.mp4 --task translate

### Recording Meetings

You can record audio, video, or both using the following commands:

    # Record audio only
    auto_subtitle record --type audio -o recordings/

    # Record video only
    auto_subtitle record --type video -o recordings/

    # Record both audio and video (default)
    auto_subtitle record -o recordings/

To list available recording devices:

    auto_subtitle record --list_devices

To specify which devices to use:

    auto_subtitle record --video_device 1 --audio_device 2

After recording, you'll be prompted to generate subtitles and meeting minutes.

### Generating Meeting Minutes

To generate meeting minutes from an existing SRT file:

    auto_subtitle summarize /path/to/subtitles.srt -o meeting_minutes.md

By default, the summary is generated in Markdown format. You can also generate it as plain text:

    auto_subtitle summarize /path/to/subtitles.srt --format text

You can specify a different OpenAI model to use:

    auto_subtitle summarize /path/to/subtitles.srt --model gpt-4

## Help

Run the following to view all available options:

    auto_subtitle --help
    auto_subtitle subtitle --help
    auto_subtitle record --help
    auto_subtitle summarize --help

## License

This script is open-source and licensed under the MIT License. For more details, check the [LICENSE](LICENSE) file.
