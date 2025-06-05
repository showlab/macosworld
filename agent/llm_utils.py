from io import BytesIO
import base64
from PIL import Image

def pil_to_b64(img: Image.Image, add_prefix: bool = True) -> str:
    with BytesIO() as image_buffer:
        img.save(image_buffer, format="PNG")
        byte_data = image_buffer.getvalue()
        img_b64 = base64.b64encode(byte_data).decode("utf-8")
        if add_prefix:
            img_b64 = "data:image/png;base64," + img_b64
    return img_b64

def b64_to_pil(img_b64: str, remove_prefix: bool = True) -> Image.Image:
    if remove_prefix and img_b64.startswith("data:image/png;base64,"):
        img_b64 = img_b64[len("data:image/png;base64,"):]
    byte_data = base64.b64decode(img_b64)
    image = Image.open(BytesIO(byte_data))
    return image

def format_interleaved_message(elements, b64_image_add_prefix = True):
    formatted_list = []
    for element in elements:
        if isinstance(element, str):
            formatted_list.append({"type": "text", "text": element})
        elif isinstance(element, Image.Image):
            formatted_list.append({
                "type": "image_url",
                "image_url": {
                    "url": pil_to_b64(element, add_prefix = b64_image_add_prefix),
                    "detail": "high"
                }
            })
    return formatted_list

def construct_user_prompt(task: str, screenshots: list):
    if len(screenshots) == 0:
        raise ValueError(f'Empty list of screenshots.')
    if len(screenshots) == 1:
        return [
            f'Task: {task}\nScreenshot: ',
            screenshots[0]
        ]
    return [
        f'Task: {task}\nRolling window of historical screenshots in chronological order: ',
        *screenshots[:-1],
        screenshots[-1]
    ]