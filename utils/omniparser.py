import sys
sys.path.append('./OmniParser')

from OmniParser.util.utils import get_som_labeled_img, check_ocr_box, get_caption_model_processor, get_yolo_model
from PIL import Image
import io
import base64

class DefaultOmniParser:
    def __init__(self, device: str):
        # All settings default (including path), following https://github.com/microsoft/OmniParser/blob/master/demo.ipynb

        self.BOX_TRESHOLD = 0.05

        # Model
        model_path='OmniParser/weights/icon_detect/model.pt'
        self.som_model = get_yolo_model(model_path)
        self.som_model.to(device)

        self.caption_model_processor = get_caption_model_processor(model_name="florence2", model_name_or_path="OmniParser/weights/icon_caption_florence", device=device)

    def __call__(self, screenshot: Image.Image):

        # Get configs
        box_overlay_ratio = max(screenshot.size) / 3200
        draw_bbox_config = {
            'text_scale': 0.8 * box_overlay_ratio,
            'text_thickness': max(int(2 * box_overlay_ratio), 1),
            'text_padding': max(int(3 * box_overlay_ratio), 1),
            'thickness': max(int(3 * box_overlay_ratio), 1),
        }

        # Inference
        ocr_bbox_rslt, is_goal_filtered = check_ocr_box(screenshot, display_img = False, output_bb_format='xyxy', goal_filtering=None, easyocr_args={'paragraph': False, 'text_threshold':0.9}, use_paddleocr=True)
        text, ocr_bbox = ocr_bbox_rslt

        # Annotate
        dino_labled_img, label_coordinates, parsed_content_list = get_som_labeled_img(screenshot, self.som_model, BOX_TRESHOLD = self.BOX_TRESHOLD, output_coord_in_ratio=True, ocr_bbox=ocr_bbox,draw_bbox_config=draw_bbox_config, caption_model_processor=self.caption_model_processor, ocr_text=text,use_local_semantics=True, iou_threshold=0.7, scale_img=False, batch_size=128)
        annotated_screenshot = Image.open(io.BytesIO(base64.b64decode(dino_labled_img)))

        # Calculate centre coordinate
        for parsed_content_index in range(len(parsed_content_list)):
            parsed_content_list[parsed_content_index]['centre_coord'] = f"{((parsed_content_list[parsed_content_index]['bbox'][0] + parsed_content_list[parsed_content_index]['bbox'][2]) / 2):.6f} {((parsed_content_list[parsed_content_index]['bbox'][1] + parsed_content_list[parsed_content_index]['bbox'][3]) / 2):.6f}"

        return annotated_screenshot, parsed_content_list
    