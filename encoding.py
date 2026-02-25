# embed_image.py
from PIL import Image

def str_to_bits(s):
    b = []
    for ch in s:
        byte = ord(ch)
        for i in range(8):
            b.append((byte >> (7-i)) & 1)
    return b

def embed(input_image, output_image, message):
    im = Image.open(input_image)
    if im.mode != 'RGB':
        im = im.convert('RGB')
    w, h = im.size
    pixels = im.load()
    bits = str_to_bits(message)
    length = len(bits)
    # store length first as 32-bit integer
    length_bits = [(length >> (31-i)) & 1 for i in range(32)]
    all_bits = length_bits + bits
    max_capacity = w * h
    if len(all_bits) > max_capacity:
        raise Exception("Message too long for image.")
    idx = 0
    for y in range(h):
        for x in range(w):
            if idx >= len(all_bits):
                break
            r, g, b = pixels[x, y]
            r = (r & 0xFE) | all_bits[idx]  # replace LSB of red channel
            pixels[x, y] = (r, g, b)
            idx += 1
        if idx >= len(all_bits):
            break
    im.save(output_image, 'PNG')
    print(f"Embedded {len(bits)} message bits into {output_image}")

if __name__ == "__main__":
    # ------------------------------
    # <- Paste your input image path, output image name, and message here ->
    input_image = "input_image.jpg"   # <-- Replace with your image file name
    output_image = "outputimage.png" # <-- Replace with desired output image name
    message = "This is nature"  # <-- Replace with your message
    # ------------------------------
    embed(input_image, output_image, message)
