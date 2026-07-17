import os
import sys
import ffmpeg
import whisper
import argparse
import warnings
import tempfile
import time
from .utils import filename, str2bool, write_srt
from .recorder import AudioRecorder, VideoRecorder, AudioVideoRecorder
from .summarizer import SubtitleSummarizer


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Subtitle command (original functionality)
    subtitle_parser = subparsers.add_parser("subtitle", help="Generate subtitles for video files")
    subtitle_parser.add_argument("video", nargs="+", type=str,
                        help="paths to video files to transcribe")
    subtitle_parser.add_argument("--model", default="small",
                        choices=whisper.available_models(), help="name of the Whisper model to use")
    subtitle_parser.add_argument("--output_dir", "-o", type=str,
                        default=".", help="directory to save the outputs")
    subtitle_parser.add_argument("--output_srt", type=str2bool, default=False,
                        help="whether to output the .srt file along with the video files")
    subtitle_parser.add_argument("--srt_only", type=str2bool, default=False,
                        help="only generate the .srt file and not create overlayed video")
    subtitle_parser.add_argument("--verbose", type=str2bool, default=False,
                        help="whether to print out the progress and debug messages")
    subtitle_parser.add_argument("--task", type=str, default="transcribe", choices=[
                        "transcribe", "translate"], help="whether to perform X->X speech recognition ('transcribe') or X->English translation ('translate')")
    subtitle_parser.add_argument("--language", type=str, default="auto", choices=["auto","af","am","ar","as","az","ba","be","bg","bn","bo","br","bs","ca","cs","cy","da","de","el","en","es","et","eu","fa","fi","fo","fr","gl","gu","ha","haw","he","hi","hr","ht","hu","hy","id","is","it","ja","jw","ka","kk","km","kn","ko","la","lb","ln","lo","lt","lv","mg","mi","mk","ml","mn","mr","ms","mt","my","ne","nl","nn","no","oc","pa","pl","ps","pt","ro","ru","sa","sd","si","sk","sl","sn","so","sq","sr","su","sv","sw","ta","te","tg","th","tk","tl","tr","tt","uk","ur","uz","vi","yi","yo","zh"], 
    help="What is the origin language of the video? If unset, it is detected automatically.")
    
    # Record command (new functionality)
    record_parser = subparsers.add_parser("record", help="Record audio/video and generate subtitles")
    record_parser.add_argument("--type", choices=["audio", "video", "both"], default="both",
                        help="Type of recording to make")
    record_parser.add_argument("--output_dir", "-o", type=str,
                        default=".", help="directory to save the outputs")
    record_parser.add_argument("--model", default="small",
                        choices=whisper.available_models(), help="name of the Whisper model to use")
    record_parser.add_argument("--resolution", type=str, default="1280x720",
                        help="Video resolution (for video recording)")
    record_parser.add_argument("--fps", type=int, default=30,
                        help="Frames per second (for video recording)")
    record_parser.add_argument("--list_devices", type=str2bool, default=False,
                        help="List available recording devices and exit")
    record_parser.add_argument("--video_device", type=int, default=0,
                        help="Video device index to use")
    record_parser.add_argument("--audio_device", type=int, default=None,
                        help="Audio device index to use (default: system default device)")
    
    # Summarize command (new functionality)
    summarize_parser = subparsers.add_parser("summarize", help="Summarize subtitles into meeting minutes")
    summarize_parser.add_argument("srt_file", type=str, help="Path to SRT file to summarize")
    summarize_parser.add_argument("--output_file", "-o", type=str, default=None,
                        help="Path to save the summary")
    summarize_parser.add_argument("--format", choices=["text", "markdown"], default="markdown",
                        help="Output format for the summary")
    summarize_parser.add_argument("--model", type=str, default="gpt-3.5-turbo",
                        help="OpenAI model to use for summarization")
    summarize_parser.add_argument("--api_key", type=str, default=None,
                        help="OpenAI API key (if not set in OPENAI_API_KEY environment variable)")
    
    # For backward compatibility, treat `auto_subtitle video.mp4 ...` as the
    # subtitle command. Argparse rejects unknown positionals before we could
    # patch the namespace, so the command has to be inserted into argv here.
    argv = sys.argv[1:]
    if argv and argv[0] not in ("subtitle", "record", "summarize", "-h", "--help"):
        argv = ["subtitle"] + argv

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return

    # Execute the appropriate command
    if args.command == "subtitle":
        subtitle_command(args)
    elif args.command == "record":
        record_command(args)
    elif args.command == "summarize":
        summarize_command(args)


def subtitle_command(args):
    """Handle the subtitle command (original functionality)"""
    model_name = args.model
    output_dir = args.output_dir
    output_srt = args.output_srt
    srt_only = args.srt_only
    language = args.language
    
    os.makedirs(output_dir, exist_ok=True)

    if model_name.endswith(".en"):
        warnings.warn(
            f"{model_name} is an English-only model, forcing English detection.")
        args.language = "en"
    # if translate task used and language argument is set, then use it
    elif language != "auto":
        args.language = language
    
    # Convert args to dict and remove unnecessary keys
    args_dict = vars(args).copy()
    for key in ['command', 'model', 'output_dir', 'output_srt', 'srt_only', 'video']:
        if key in args_dict:
            args_dict.pop(key)

    # Whisper expects language=None for auto-detection, not the string "auto"
    if args_dict.get("language") == "auto":
        args_dict["language"] = None


    model = whisper.load_model(model_name)
    audios = get_audio(args.video)
    subtitles = get_subtitles(
        audios, output_srt or srt_only, output_dir, lambda audio_path: model.transcribe(audio_path, **args_dict)
    )

    if srt_only:
        return

    for path, srt_path in subtitles.items():
        out_path = os.path.join(output_dir, f"{filename(path)}.mp4")

        print(f"Adding subtitles to {filename(path)}...")

        video = ffmpeg.input(path)
        audio = video.audio

        ffmpeg.concat(
            video.filter('subtitles', srt_path, force_style="OutlineColour=&H40000000,BorderStyle=3"), audio, v=1, a=1
        ).output(out_path).run(quiet=True, overwrite_output=True)

        print(f"Saved subtitled video to {os.path.abspath(out_path)}.")


def record_command(args):
    """Handle the record command (new functionality)"""
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    # List devices if requested
    if args.list_devices:
        recorder = AudioVideoRecorder(output_dir)
        recorder.list_devices()
        return
    
    # Create the appropriate recorder and start it (all recorders are non-blocking)
    if args.type == "audio":
        recorder = AudioRecorder(output_dir)
        recorder.start_recording(device_index=args.audio_device)
    elif args.type == "video":
        recorder = VideoRecorder(output_dir, fps=args.fps, resolution=args.resolution)
        recorder.start_recording(device_index=args.video_device)
    else:  # both
        recorder = AudioVideoRecorder(output_dir, fps=args.fps, resolution=args.resolution)
        recorder.start_recording(video_device_index=args.video_device,
                                 audio_device_index=args.audio_device)

    try:
        print("Recording... Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping recording...")

    output_file = recorder.stop_recording()

    if not output_file:
        print("Recording failed or was not started.")
        return
    
    # Ask if user wants to generate subtitles
    generate_subtitles = input("Do you want to generate subtitles for this recording? (y/n): ").lower() == 'y'
    
    if generate_subtitles:
        # Create args for subtitle command
        subtitle_args = argparse.Namespace(
            command="subtitle",
            video=[output_file],
            model=args.model,
            output_dir=output_dir,
            output_srt=True,
            srt_only=False,
            verbose=False,
            task="transcribe",
            language="auto"
        )
        
        # Generate subtitles
        subtitle_command(subtitle_args)
        
        # Get the SRT file path
        srt_file = os.path.join(output_dir, f"{filename(output_file)}.srt")
        
        # Ask if user wants to generate meeting minutes
        generate_minutes = input("Do you want to generate meeting minutes from the subtitles? (y/n): ").lower() == 'y'
        
        if generate_minutes:
            # Create args for summarize command
            summarize_args = argparse.Namespace(
                command="summarize",
                srt_file=srt_file,
                output_file=os.path.join(output_dir, f"{filename(output_file)}_minutes.md"),
                format="markdown",
                model="gpt-3.5-turbo",
                api_key=None
            )
            
            # Generate meeting minutes
            summarize_command(summarize_args)


def summarize_command(args):
    """Handle the summarize command (new functionality)"""
    # Check if the SRT file exists
    if not os.path.exists(args.srt_file):
        print(f"Error: SRT file '{args.srt_file}' not found.")
        return
    
    # Create the summarizer
    summarizer = SubtitleSummarizer(api_key=args.api_key, model=args.model)
    
    # Generate the output file path if not provided
    if not args.output_file:
        base_name = filename(args.srt_file)
        if args.format == "markdown":
            args.output_file = f"{base_name}_minutes.md"
        else:
            args.output_file = f"{base_name}_minutes.txt"
    
    # Generate the summary
    try:
        if args.format == "markdown":
            summarizer.summarize_to_markdown(args.srt_file, args.output_file)
        else:
            summarizer.summarize(args.srt_file, args.output_file)
        
        print(f"Meeting minutes generated and saved to {os.path.abspath(args.output_file)}")
    except Exception as e:
        print(f"Error generating summary: {str(e)}")


def get_audio(paths):
    temp_dir = tempfile.gettempdir()

    audio_paths = {}

    for path in paths:
        print(f"Extracting audio from {filename(path)}...")
        output_path = os.path.join(temp_dir, f"{filename(path)}.wav")

        ffmpeg.input(path).output(
            output_path,
            acodec="pcm_s16le", ac=1, ar="16k"
        ).run(quiet=True, overwrite_output=True)

        audio_paths[path] = output_path

    return audio_paths


def get_subtitles(audio_paths: dict, output_srt: bool, output_dir: str, transcribe: callable):
    subtitles_path = {}

    for path, audio_path in audio_paths.items():
        srt_path = output_dir if output_srt else tempfile.gettempdir()
        srt_path = os.path.join(srt_path, f"{filename(path)}.srt")
        
        print(
            f"Generating subtitles for {filename(path)}... This might take a while."
        )

        warnings.filterwarnings("ignore")
        result = transcribe(audio_path)
        warnings.filterwarnings("default")

        with open(srt_path, "w", encoding="utf-8") as srt:
            write_srt(result["segments"], file=srt)

        subtitles_path[path] = srt_path

    return subtitles_path


if __name__ == '__main__':
    main()
