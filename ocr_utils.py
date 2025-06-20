import cv2
import numpy as np
import pytesseract
import re
from logger import log_debug

def preprocess_for_ocr(img, mode='adaptive', block_size=41, c_value=-60): # Parameters are now configurable
    """
    Preprocesses an image for OCR.

    Args:
        img: The input image (NumPy array).
        mode: The type of preprocessing to apply.
              'adaptive': Applies adaptive thresholding (recommended for varying backgrounds).
              'binary': Applies fixed binary thresholding (inverted).
              'binary_inv': Applies fixed binary thresholding.
              'none': Returns the grayscale image without thresholding.
              Defaults to 'adaptive'.
        block_size: Size of the pixel neighborhood used for adaptive thresholding.
                   Must be an odd number. Only used for 'adaptive' mode.
        c_value: Constant subtracted from the mean for adaptive thresholding.
                Can be positive, negative, or zero. Only used for 'adaptive' mode.
    Returns:
        The processed image.
    """
    if img is None or img.size == 0:
        log_debug("Input image to preprocess_for_ocr is empty or None.")
        # Return a small black image or handle as an error appropriately
        return np.zeros((10, 10), dtype=np.uint8)

    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy() # Ensure it's a copy if already grayscale

    try:
        if mode == 'adaptive':
            # --- Adaptive Thresholding ---
            # Use the configurable parameters
            blockSize = block_size  # Size of the pixel neighborhood used to calculate the threshold.
                                    # Must be an odd number (e.g., 3, 5, 7, 11, 21).
                                    # Smaller for smaller text/details, larger for larger features.
            C = c_value             # A constant subtracted from the mean or weighted mean.
                                    # Normally, it is positive but may be zero or negative as well.
                                    # Helps fine-tune the threshold.

            # cv2.ADAPTIVE_THRESH_GAUSSIAN_C often gives better results than cv2.ADAPTIVE_THRESH_MEAN_C.
            # cv2.THRESH_BINARY_INV is used because Tesseract generally prefers black text on a white background.
            processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                              cv2.THRESH_BINARY_INV, blockSize, C)
            log_debug(f"Used adaptive thresholding (blockSize={blockSize}, C={C})")
            # --- End of Adaptive Thresholding ---

        elif mode == 'binary':
            # Original fixed thresholding (inverted: white text becomes black)
            _, processed = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            log_debug(f"Used fixed binary thresholding (INV)")
        elif mode == 'binary_inv':
            # Original fixed thresholding (white text stays white)
            _, processed = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            log_debug(f"Used fixed binary thresholding (standard)")
        elif mode == 'none': # Explicitly handle 'none'
            processed = gray
            log_debug(f"No thresholding applied, using grayscale. Mode: {mode}")
        else: # Fallback for unrecognized modes
            log_debug(f"Unrecognized mode: '{mode}'. Defaulting to grayscale.")
            processed = gray
            
        return processed

    except Exception as e:
        log_debug(f"Preprocessing error (mode: {mode}): {e}, returning grayscale image")
        # In case of any error during processing, return the grayscale image
        return gray

def scale_for_ocr(img):
    if img is None or img.size == 0:
        return img
    h, w = img.shape[:2]
    min_dim = 300
    if h < min_dim or w < min_dim:
        scale_factor = max(min_dim / h, min_dim / w)
        scaled = cv2.resize(img, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
        return scaled
    return img

def get_tesseract_model_params(mode='general'):
    if mode == 'subtitle':
        return f'--psm 7 --oem 3 -c preserve_interword_spaces=1'
    elif mode == 'gaming':
        return f'--psm 6 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?:;()[]-_\'"/\\$%&@ '
    elif mode == 'document':
        return f'--psm 3 --oem 3'
    else:
        return f'--psm 6 --oem 3'

def ocr_region_with_confidence(img, region, lang_code, custom_config, confidence_threshold):
    x, y, w, h = region
    if len(img.shape) == 3:
        roi = img[y:y+h, x:x+w]
    else:
        roi = img[y:y+h, x:x+w]
    
    scaled_roi = scale_for_ocr(roi)
    
    try:
        data = pytesseract.image_to_data(
            scaled_roi,
            lang=lang_code,
            config=custom_config,
            output_type=pytesseract.Output.DICT
        )
        filtered_text = []
        for i in range(len(data['text'])):
            if not data['text'][i].strip():
                continue
            if float(data['conf'][i]) >= confidence_threshold:
                filtered_text.append(data['text'][i])
            else:
                log_debug(f"Filtered low-confidence text: '{data['text'][i]}' ({data['conf'][i]}%)")
        return ' '.join(filtered_text)
    except Exception as e:
        log_debug(f"OCR error in region {region}: {e}")
        return ""

def post_process_ocr_text_general(text, lang='auto'):
    if not text: return text
    cleaned = text.strip()
    ocr_errors = {
        '\u201E': '"', '\u2019': "'", '\u2014': '-', '\u2013': '-',
    }
    if lang.startswith('fra') or lang.startswith('fr'):
        cleaned = cleaned.replace('||', 'Il')
    
    # English-specific OCR fixes
    if lang.startswith('eng') or lang.startswith('en'):
        # Special case for | character (commonly at start of sentences)
        cleaned = re.sub(r'^\|\s', 'I ', cleaned)  # | at start followed by space
        cleaned = re.sub(r'\s\|\s', ' I ', cleaned)  # | surrounded by spaces
        
        # Other fixes using word boundaries
        english_ocr_fixes = {
            '{': '(', '}': ')', '\\/': 'V',
        }
        for error, correction in english_ocr_fixes.items():
            cleaned = re.sub(r'\b' + re.escape(error) + r'\b', correction, cleaned)
    
    for error, correction in ocr_errors.items():
        cleaned = re.sub(r'\b' + re.escape(error) + r'\b', correction, cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned

def remove_text_after_last_punctuation_mark(text):
    if not text: return text
    pattern = r'[.!?]|\.{3}|…'
    matches = list(re.finditer(pattern, text))
    if not matches: return text
    last_match = matches[-1]
    end_pos = last_match.end()
    if last_match.group() == ".":
        if end_pos + 2 <= len(text) and text[end_pos:end_pos+2] == "..":
            end_pos += 2
    return text[:end_pos]

def post_process_ocr_for_game_subtitle(text):
    if not text: return text
    cleaned = text.strip()
    name_match = re.search(r'^([A-Za-z\s]+):', cleaned)
    if name_match:
        character_name = name_match.group(1).strip()
        character_name = ' '.join(word.capitalize() for word in character_name.split())
        cleaned = cleaned.replace(name_match.group(0), f"{character_name}:")
    substitutions = {
        # "l-": "I-", "ledi": "Jedi", "jedl": "Jedi",  # Commented out - too aggressive
        # "RepubIic": "Republic", "repubIic": "republic",  # Commented out - too aggressive
    }
    for error, correction in substitutions.items():
        cleaned = cleaned.replace(error, correction)
    cleaned = re.sub(r'(\w+:)(\w)', r'\1 \2', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'^[\|\[\]\{\}<>\s\.,;:_\-=+\'\"]{1,5}', '', cleaned)
    cleaned = re.sub(r'[\|\[\]\{\}<>\s\.,;:_\-=+\'\"]{1,5}$', '', cleaned)
    return cleaned
