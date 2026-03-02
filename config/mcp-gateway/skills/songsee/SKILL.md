---
name: songsee
description: "Generate audio spectrograms and waveform visualizations"
command: "${command}"
args:
  - name: command
    description: "ffmpeg/sox command for audio visualization"
    required: true
tags: [audio, visualization, spectrogram, media]
timeout: 60
---

# Song See Skill

Generate audio spectrograms and waveform visualizations using ffmpeg and sox. Create visual representations of audio files for analysis and presentation.

## Spectrogram with ffmpeg

```bash
# Generate a spectrogram image from an audio file
ffmpeg -i input.mp3 -lavfi showspectrumpic=s=1024x512 spectrogram.png -y

# Generate with custom size and color
ffmpeg -i input.mp3 -lavfi showspectrumpic=s=1920x1080:color=intensity spectrogram.png -y

# Generate spectrogram with legend
ffmpeg -i input.mp3 -lavfi showspectrumpic=s=1024x512:legend=1 spectrogram.png -y

# Spectrogram of specific time range (30s starting at 1:00)
ffmpeg -ss 60 -t 30 -i input.mp3 -lavfi showspectrumpic=s=1024x512 spectrogram_clip.png -y

# Log-scale frequency spectrogram
ffmpeg -i input.mp3 -lavfi showspectrumpic=s=1024x512:fscale=log spectrogram_log.png -y
```

## Waveform with ffmpeg

```bash
# Generate a waveform image
ffmpeg -i input.mp3 -lavfi showwavespic=s=1024x256 waveform.png -y

# Waveform with custom colors
ffmpeg -i input.mp3 -lavfi "showwavespic=s=1024x256:colors=0x00FF00" waveform.png -y

# Split channels waveform
ffmpeg -i input.mp3 -lavfi showwavespic=s=1024x256:split_channels=1 waveform_stereo.png -y

# Waveform of specific segment
ffmpeg -ss 0 -t 60 -i input.mp3 -lavfi showwavespic=s=1920x256 waveform_first_minute.png -y
```

## Spectrogram with sox

```bash
# Generate spectrogram with sox
sox input.mp3 -n spectrogram -o spectrogram.png

# Spectrogram with custom dimensions
sox input.mp3 -n spectrogram -x 1024 -y 512 -o spectrogram.png

# Spectrogram with title
sox input.mp3 -n spectrogram -t "My Song" -o spectrogram.png

# High-resolution spectrogram
sox input.mp3 -n spectrogram -x 1920 -Y 1080 -o spectrogram_hires.png

# Spectrogram of a specific channel (left)
sox input.mp3 -n remix 1 spectrogram -o spectrogram_left.png
```

## Audio Info

```bash
# Get audio file details with ffprobe
ffprobe -v quiet -print_format json -show_format -show_streams input.mp3

# Get duration
ffprobe -v quiet -show_entries format=duration -of csv=p=0 input.mp3

# Get sample rate and channels
ffprobe -v quiet -show_entries stream=sample_rate,channels -of csv=p=0 input.mp3

# Get audio stats with sox
sox input.mp3 -n stat 2>&1
```

## Combined Visualizations

```bash
# Generate both spectrogram and waveform
ffmpeg -i input.mp3 -lavfi showspectrumpic=s=1024x512 spectrogram.png -y && \
ffmpeg -i input.mp3 -lavfi showwavespic=s=1024x256 waveform.png -y

# Vertical stack spectrogram and waveform using ffmpeg
ffmpeg -i input.mp3 -lavfi "showspectrumpic=s=1024x384" spectrogram.png -y && \
ffmpeg -i input.mp3 -lavfi "showwavespic=s=1024x192" waveform.png -y
```

## Examples

**Generate a spectrogram from an MP3:**
```
command: "ffmpeg -i /tmp/song.mp3 -lavfi showspectrumpic=s=1024x512:legend=1 /tmp/spectrogram.png -y"
```

**Generate a waveform visualization:**
```
command: "ffmpeg -i /tmp/song.mp3 -lavfi showwavespic=s=1024x256:split_channels=1 /tmp/waveform.png -y"
```

**Get audio file info:**
```
command: "ffprobe -v quiet -print_format json -show_format -show_streams /tmp/song.mp3"
```

**Generate spectrogram of first 30 seconds:**
```
command: "ffmpeg -t 30 -i /tmp/song.mp3 -lavfi showspectrumpic=s=1024x512 /tmp/spectrogram_30s.png -y"
```
