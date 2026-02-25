import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, Response

# Import existing steganography helpers
import encoding as image_encoding
import decoding as image_decoding
from encode_audio import encode_audio as audio_encode, convert_to_wav
from decode_audio import decode_audio as audio_decode
from PIL import Image
import wave

BASE_DIR = Path(__file__).parent.resolve()
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"

UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg"}
ALLOWED_AUDIO_EXTS = {"wav", "mp3", "aac", "m4a", "flac", "ogg"}


def allowed_file(filename: str, kind: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    if kind == "image":
        return ext in ALLOWED_IMAGE_EXTS
    if kind == "audio":
        return ext in ALLOWED_AUDIO_EXTS
    return False


app = Flask(__name__)
app.secret_key = "replace-this-with-a-random-secret"


@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------
# File-payload helpers (do not affect existing text encode/decode)
# Header format:
#  MAGIC(4 bytes = b'STG1') | name_len(2 bytes BE) | name UTF-8 | payload_len(4 bytes BE) | payload
MAGIC = b"STG1"


def _bytes_to_bits(data: bytes):
    for byte in data:
        for i in range(8):
            yield (byte >> (7 - i)) & 1


def _bits_to_bytes(bits_iter, total_bits: int) -> bytes:
    out = bytearray()
    value = 0
    count = 0
    for b in bits_iter:
        value = (value << 1) | (b & 1)
        count += 1
        if count == 8:
            out.append(value)
            value = 0
            count = 0
        if len(out) * 8 >= total_bits:
            break
    return bytes(out)


def image_embed_file(input_image: str, output_image: str, payload_path: str, display_name: str):
    with open(payload_path, "rb") as f:
        payload = f.read()
    name_bytes = display_name.encode("utf-8")
    if len(name_bytes) > 65535:
        raise ValueError("Filename too long to embed")
    header = MAGIC + len(name_bytes).to_bytes(2, "big") + name_bytes + len(payload).to_bytes(4, "big")
    blob = header + payload

    im = Image.open(input_image)
    if im.mode != 'RGB':
        im = im.convert('RGB')
    w, h = im.size
    pixels = im.load()

    max_capacity_bits = w * h  # using 1 bit (R channel LSB) per pixel
    total_bits = len(blob) * 8
    if total_bits > max_capacity_bits:
        raise ValueError("Payload too large for this image")

    bit_iter = _bytes_to_bits(blob)
    written = 0
    for y in range(h):
        for x in range(w):
            if written >= total_bits:
                break
            r, g, b = pixels[x, y]
            bit = next(bit_iter)
            r = (r & 0xFE) | bit
            pixels[x, y] = (r, g, b)
            written += 1
        if written >= total_bits:
            break
    im.save(output_image, 'PNG')


def image_extract_file(input_image: str, output_dir: Path) -> Path:
    im = Image.open(input_image)
    if im.mode != 'RGB':
        im = im.convert('RGB')
    w, h = im.size
    pixels = im.load()

    # Build a generator of bits from R channel
    def bit_stream():
        for y in range(h):
            for x in range(w):
                r, g, b = pixels[x, y]
                yield r & 1

    bits = bit_stream()
    # Read first 4 bytes for magic (32 bits)
    magic = _bits_to_bytes(bits, 32)
    if magic != MAGIC:
        raise ValueError("File payload not found (magic mismatch). Try Text decode.")

    # name_len (16 bits)
    name_len = int.from_bytes(_bits_to_bytes(bits, 16), "big")
    name_bytes = _bits_to_bytes(bits, name_len * 8)
    filename = name_bytes.decode("utf-8", errors="replace")
    # payload_len (32 bits)
    payload_bits_len = int.from_bytes(_bits_to_bytes(bits, 32), "big") * 8
    data = _bits_to_bytes(bits, payload_bits_len)

    # Prevent directory traversal
    base_name = Path(filename).name
    out_path = output_dir / base_name
    # Ensure unique filename without overwriting existing files
    if out_path.exists():
        stem, suffix = Path(base_name).stem, Path(base_name).suffix
        counter = 1
        while True:
            candidate = output_dir / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                out_path = candidate
                break
            counter += 1
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


def audio_embed_file(input_file: str, payload_path: str, outputs_dir: Path):
    # Convert to temp WAV
    temp_wav = str(outputs_dir / "_temp_embed.wav")
    convert_to_wav(input_file, temp_wav)

    with open(payload_path, "rb") as f:
        payload = f.read()
    name = Path(payload_path).name
    name_bytes = name.encode("utf-8")
    if len(name_bytes) > 65535:
        raise ValueError("Filename too long to embed")
    header = MAGIC + len(name_bytes).to_bytes(2, "big") + name_bytes + len(payload).to_bytes(4, "big")
    blob = header + payload

    wav = wave.open(temp_wav, 'rb')
    frames = bytearray(list(wav.readframes(wav.getnframes())))
    params = wav.getparams()
    wav.close()

    total_bits = len(blob) * 8
    if total_bits > len(frames):
        raise ValueError("Payload too large for this audio")

    bit_iter = _bytes_to_bits(blob)
    for i in range(total_bits):
        frames[i] = (frames[i] & 254) | next(bit_iter)

    stem = Path(input_file).stem
    stego_wav = outputs_dir / f"{stem}_file_stego.wav"
    out = wave.open(str(stego_wav), 'wb')
    out.setparams(params)
    out.writeframes(frames)
    out.close()

    # Clean up
    try:
        os.remove(temp_wav)
    except OSError:
        pass

    return stego_wav


def audio_extract_file(stego_wav_path: str, outputs_dir: Path) -> Path:
    wav = wave.open(stego_wav_path, 'rb')
    frames = bytearray(list(wav.readframes(wav.getnframes())))
    wav.close()

    def bit_stream():
        for byte in frames:
            yield byte & 1

    bits = bit_stream()
    magic = _bits_to_bytes(bits, 32)
    if magic != MAGIC:
        raise ValueError("File payload not found (magic mismatch). Try Text decode.")
    name_len = int.from_bytes(_bits_to_bytes(bits, 16), "big")
    name_bytes = _bits_to_bytes(bits, name_len * 8)
    filename = name_bytes.decode("utf-8", errors="replace")
    payload_bits_len = int.from_bytes(_bits_to_bytes(bits, 32), "big") * 8
    data = _bits_to_bytes(bits, payload_bits_len)

    base_name = Path(filename).name
    out_path = outputs_dir / base_name
    if out_path.exists():
        stem, suffix = Path(base_name).stem, Path(base_name).suffix
        counter = 1
        while True:
            candidate = outputs_dir / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                out_path = candidate
                break
            counter += 1
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


@app.route("/process", methods=["POST"])
def process():
    medium = request.form.get("medium")  # image|audio
    action = request.form.get("action")  # encode|decode
    payload_type = request.form.get("payload_type", "text")  # text|file
    message = request.form.get("message", "")
    upload = request.files.get("file")
    payload_file = request.files.get("payload")  # file payload for encode

    if medium not in {"image", "audio"} or action not in {"encode", "decode"}:
        flash("Invalid selection.")
        return redirect(url_for("index"))

    if not upload or upload.filename == "":
        flash("Please choose a file to upload.")
        return redirect(url_for("index"))

    if not allowed_file(upload.filename, medium):
        flash("Unsupported file type for the selected medium.")
        return redirect(url_for("index"))

    # Save upload
    safe_name = Path(upload.filename).name
    upload_path = UPLOADS_DIR / safe_name
    upload.save(upload_path)

    result = {"medium": medium, "action": action, "payload_type": payload_type, "message": None, "downloads": []}

    try:
        if medium == "image":
            if action == "encode":
                output_name = f"{upload_path.stem}_stego.png"
                output_path = OUTPUTS_DIR / output_name
                if payload_type == "text":
                    if not message:
                        flash("Please enter a secret message to encode.")
                        return redirect(url_for("index"))
                    image_encoding.embed(str(upload_path), str(output_path), message)
                else:
                    if not payload_file or payload_file.filename == "":
                        flash("Please choose a payload file to embed.")
                        return redirect(url_for("index"))
                    payload_name = Path(payload_file.filename).name
                    payload_path = UPLOADS_DIR / ("payload_" + payload_name)
                    payload_file.save(payload_path)
                    image_embed_file(str(upload_path), str(output_path), str(payload_path), payload_name)
                result["downloads"].append({
                    "label": "Download stego image",
                    "href": url_for("download", filename=output_name)
                })
            else:  # decode (auto-detect file payload; fallback to text)
                try:
                    out_path = image_extract_file(str(upload_path), OUTPUTS_DIR)
                    result["downloads"].append({
                        "label": f"Download extracted file ({out_path.name})",
                        "href": url_for("download", filename=out_path.name, name=out_path.name)
                    })
                except Exception as e:
                    # If not file payload, fallback to text decode
                    extracted = image_decoding.extract(str(upload_path))
                    result["message"] = extracted

        else:  # audio
            if action == "encode":
                if payload_type == "text":
                    if not message:
                        flash("Please enter a secret message to encode.")
                        return redirect(url_for("index"))
                    # Call provided audio encoder; it writes outputs in CWD
                    cwd = os.getcwd()
                    try:
                        os.chdir(str(OUTPUTS_DIR))
                        audio_encode(str(upload_path), message)
                        stem = upload_path.stem
                        wav_out = f"{stem}_stego.wav"
                        orig_ext = upload_path.suffix
                        alt_out = f"{stem}_stego{orig_ext}"
                        if Path(wav_out).exists():
                            result["downloads"].append({
                                "label": "Download stego WAV",
                                "href": url_for("download", filename=wav_out)
                            })
                        if Path(alt_out).exists() and alt_out != wav_out:
                            result["downloads"].append({
                                "label": f"Download stego {orig_ext[1:].upper()}",
                                "href": url_for("download", filename=alt_out)
                            })
                    finally:
                        os.chdir(cwd)
                else:
                    if not payload_file or payload_file.filename == "":
                        flash("Please choose a payload file to embed.")
                        return redirect(url_for("index"))
                    payload_name = Path(payload_file.filename).name
                    payload_path = UPLOADS_DIR / ("payload_" + payload_name)
                    payload_file.save(payload_path)
                    stego_wav = audio_embed_file(str(upload_path), str(payload_path), OUTPUTS_DIR)
                    result["downloads"].append({
                        "label": "Download stego WAV",
                        "href": url_for("download", filename=stego_wav.name)
                    })
            else:  # decode (auto-detect file payload; fallback to text)
                if upload_path.suffix.lower() != ".wav":
                    flash("Please upload a stego WAV file for decoding.")
                    return redirect(url_for("index"))
                try:
                    out_path = audio_extract_file(str(upload_path), OUTPUTS_DIR)
                    result["downloads"].append({
                        "label": f"Download extracted file ({out_path.name})",
                        "href": url_for("download", filename=out_path.name, name=out_path.name)
                    })
                except Exception:
                    extracted = audio_decode(str(upload_path))
                    result["message"] = extracted

        return render_template("index.html", result=result)

    except Exception as exc:
        flash(f"Error: {exc}")
        return redirect(url_for("index"))


@app.route("/download/<path:filename>")
def download(filename: str):
    # Optional custom download name via query param (?name=...)
    download_name = request.args.get("name")
    try:
        return send_from_directory(
            str(OUTPUTS_DIR),
            filename,
            as_attachment=True,
            download_name=download_name if download_name else None,
        )
    except TypeError:
        # For older Flask versions without download_name, fallback
        return send_from_directory(
            str(OUTPUTS_DIR),
            filename,
            as_attachment=True,
        )


if __name__ == "__main__":
    # Run the server
    app.run(host="0.0.0.0", port=5000, debug=True)


