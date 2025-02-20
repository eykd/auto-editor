'''scripts/fastVideo.py'''

"""
This method is used for mp4 files that only need frame margin and silent_threshold
specified.

It's about 4x faster than the safe method. 1 Minute of video may take about 12 seconds.
"""

# External libraries
import cv2  # pip3 install opencv-python
import numpy as np
from scipy.io import wavfile

# Included functions
from scripts.usefulFunctions import getAudioChunks, progressBar, vidTracks

# Internal libraries
import os
import sys
import subprocess
from shutil import rmtree
from time import time

def fastVideo(videoFile, outFile, silentThreshold, frameMargin, SAMPLE_RATE,
    AUD_BITRATE, VERBOSE, cutByThisTrack, keepTracksSep):

    print('Running from fastVideo.py')

    if(not os.path.isfile(videoFile)):
        print('Could not find file:', videoFile)
        sys.exit()

    TEMP = '.TEMP'

    cap = cv2.VideoCapture(videoFile)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = round(cap.get(cv2.CAP_PROP_FPS))

    try:
        os.mkdir(TEMP)
    except OSError:
        rmtree(TEMP)
        os.mkdir(TEMP)

    tracks = vidTracks(videoFile)

    if(cutByThisTrack >= tracks):
        print("Error: You choose a track that doesn't exist.")
        print(f'There are only {tracks-1} tracks. (starting from 0)')
        sys.exit()
    for trackNumber in range(tracks):
        cmd = ['ffmpeg', '-i', videoFile, '-ab', AUD_BITRATE, '-ac', '2', '-ar',
        str(SAMPLE_RATE),'-map', f'0:a:{trackNumber}', f'{TEMP}/{trackNumber}.wav']
        if(not VERBOSE):
            cmd.extend(['-nostats', '-loglevel', '0'])
        else:
            cmd.extend(['-hide_banner'])
        subprocess.call(cmd)

    sampleRate, audioData = wavfile.read(f'{TEMP}/{cutByThisTrack}.wav')
    chunks = getAudioChunks(audioData, sampleRate, fps, silentThreshold, 2, frameMargin)

    oldAudios = []
    newAudios = []
    for i in range(tracks):
        __, audioData = wavfile.read(f'{TEMP}/{i}.wav')
        oldAudios.append(audioData)
        newAudios.append(np.zeros_like(audioData, dtype=np.int16))

    yPointer = 0

    out = cv2.VideoWriter(f'{TEMP}/spedup.mp4', fourcc, fps, (width, height))

    totalFrames = chunks[len(chunks) - 1][1]
    beginTime = time()

    while cap.isOpened():
        ret, frame = cap.read()
        if(not ret):
            break

        cframe = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) # current frame

        currentTime = cframe / fps

        state = None
        for chunk in chunks:
            if(cframe >= chunk[0] and cframe <= chunk[1]):
                state = chunk[2]
                break

        if(state == 1):
            out.write(frame)

            audioSampleStart = int(currentTime * sampleRate)
            audioSampleEnd = audioSampleStart + (sampleRate // fps)

            # handle audio tracks
            for i, oneAudioData in enumerate(oldAudios):
                audioChunk = oneAudioData[audioSampleStart:audioSampleEnd]

                yPointerEnd = yPointer + audioChunk.shape[0]

                newAudios[i][yPointer:yPointerEnd] = audioChunk
            yPointer = yPointerEnd

        progressBar(cframe, totalFrames, beginTime)

    # finish audio
    for i, newData in enumerate(newAudios):
        newData = newData[:yPointer]
        wavfile.write(f'{TEMP}/new{i}.wav', sampleRate, newData)

        if(not os.path.isfile(f'{TEMP}/new{i}.wav')):
            raise IOError('audio file not created.')

    cap.release()
    out.release()
    cv2.destroyAllWindows()

    first = videoFile[:videoFile.rfind('.')]
    extension = videoFile[videoFile.rfind('.'):]

    if(outFile == ''):
        outFile = f'{first}_ALTERED{extension}'

    # Now mix new audio(s) and the new video.

    if(keepTracksSep):
        cmd = ['ffmpeg', '-y']
        for i in range(tracks):
            cmd.extend(['-i', f'{TEMP}/new{i}.wav'])
        cmd.extend(['-i', f'{TEMP}/spedup.mp4']) # add input video
        for i in range(tracks):
            cmd.extend(['-map', f'{i}:a:0'])
        cmd.extend(['-map', f'{tracks}:v:0','-c:v', 'copy', '-movflags', '+faststart',
            outFile])
        if(not VERBOSE):
            cmd.extend(['-nostats', '-loglevel', '0'])
    else:
        if(tracks > 1):
            cmd = ['ffmpeg']
            for i in range(tracks):
                cmd.extend(['-i', f'{TEMP}/new{i}.wav'])
            cmd.extend(['-filter_complex', f'amerge=inputs={tracks}', '-ac', '2',
                f'{TEMP}/newAudioFile.wav'])
            if(not VERBOSE):
                cmd.extend(['-nostats', '-loglevel', '0'])
            subprocess.call(cmd)
        else:
            os.rename(f'{TEMP}/new0.wav', f'{TEMP}/newAudioFile.wav')

        cmd = ['ffmpeg', '-y', '-i', f'{TEMP}/newAudioFile.wav', '-i',
            f'{TEMP}/spedup.mp4', '-c:v', 'copy', '-movflags', '+faststart',
            outFile]
        if(not VERBOSE):
            cmd.extend(['-nostats', '-loglevel', '0'])
        subprocess.call(cmd)

    return outFile
