# extract_image.py
from PIL import Image

def bits_to_str(bits):
    chars = []
    for b in range(0, len(bits), 8):
        byte = 0
        for i in range(8):
            byte = (byte << 1) | bits[b + i]
        chars.append(chr(byte))
    return ''.join(chars)

def extract(input_image):
    im = Image.open(input_image)
    if im.mode != 'RGB':
        im = im.convert('RGB')
    w, h = im.size
    pixels = im.load()
    
    # Step 1: extract first 32 bits to get message length
    length_bits = []
    idx = 0
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            length_bits.append(r & 1)
            idx += 1
            if idx >= 32:
                break
        if idx >= 32:
            break
    
    length = 0
    for bit in length_bits:
        length = (length << 1) | bit
    
    # Step 2: extract message bits
    message_bits = []
    count = 0
    for y in range(h):
        for x in range(w):
            if count < 32:
                count += 1  # skip first 32 bits
                continue
            if len(message_bits) >= length:
                break
            r, g, b = pixels[x, y]
            message_bits.append(r & 1)
        if len(message_bits) >= length:
            break
    
    message = bits_to_str(message_bits)
    print("Hidden message:", message)
    return message

if __name__ == "__main__":
    # ------------------------------
    # <- Paste your received image name here ->
    input_image = "outputimage.png"  # <-- Replace with your received image
    # ------------------------------
    extract(input_image)
