import wave

def decode_audio(stego_file):
    audio = wave.open(stego_file, 'rb')
    frame_bytes = bytearray(list(audio.readframes(audio.getnframes())))
    audio.close()

    # Extract LSBs
    bits = [str(byte & 1) for byte in frame_bytes]
    message = ""
    for i in range(0, len(bits), 8):
        byte = bits[i:i+8]
        if len(byte) < 8:
            break
        char = chr(int("".join(byte), 2))
        message += char
        if message.endswith("###"):
            break

    return message.replace("###", "")

if __name__ == "__main__":
    stego_audio = input("Enter stego WAV file path: ").strip()
    message = decode_audio(stego_audio)
    print(f"Hidden message: {message}")
