import subprocess
import wave
import os
from pathlib import Path

def convert_to_wav(input_file, temp_wav="temp.wav"):
    """Convert any audio format to WAV using FFmpeg"""
    subprocess.run([
        "ffmpeg", "-y", "-i", input_file,
        "-ar", "44100", "-ac", "2", "-sample_fmt", "s16", temp_wav
    ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return temp_wav

def encode_audio(input_file, secret_msg):
    input_path = Path(input_file)
    temp_wav = "temp.wav"

    # Convert to WAV
    convert_to_wav(input_file, temp_wav)

    # Read WAV
    audio = wave.open(temp_wav, 'rb')
    frame_bytes = bytearray(list(audio.readframes(audio.getnframes())))
    params = audio.getparams()
    audio.close()

    # Add delimiter
    secret_msg += '###'
    bits = ''.join([format(ord(c), '08b') for c in secret_msg])

    if len(bits) > len(frame_bytes):
        raise ValueError("Message too long for this audio!")

    # LSB encoding
    for i, bit in enumerate(bits):
        frame_bytes[i] = (frame_bytes[i] & 254) | int(bit)

    # Save stego WAV
    stego_file = input_path.stem + "_stego.wav"
    stego = wave.open(stego_file, 'wb')
    stego.setparams(params)
    stego.writeframes(frame_bytes)
    stego.close()

    # Optional: convert back to original format for listening
    output_file = input_path.stem + "_stego" + input_path.suffix
    subprocess.run([
        "ffmpeg", "-y", "-i", stego_file, output_file
    ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    print(f"[+] Message encoded in '{stego_file}' (WAV) and '{output_file}' for listening")
    os.remove(temp_wav)

if __name__ == "__main__":
    input_audio = input("Enter audio file path (any format): ").strip()
    secret_msg = input("Enter secret message: ").strip()
    encode_audio(input_audio, secret_msg)
