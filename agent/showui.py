import os
from utils.VNCClient import VNCClient_SSH
from utils.log import print_message
from agent.llm_utils import pil_to_b64
from PIL import Image
import json
from utils.timeout import timeout
import time
import torch
import ast
from qwen_vl_utils import process_vision_info
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

_NAV_SYSTEM = """
You are an assistant trained to navigate the macOS screen. 
Given a task instruction, a screen observation, and an action history sequence, 
output the next action and wait for the next observation. 
Here is the action space:
1. CLICK: Click on an element, value is not applicable and the position [x,y] is required. 
2. INPUT: Type a string into an element, value is a string to type and the position [x,y] is required. 
3. HOVER: Hover on an element, value is not applicable and the position [x,y] is required.
4. ENTER: Enter operation, value and position are not applicable.
5. SCROLL: Scroll the screen, value is the direction to scroll and the position is not applicable.
6. ESC: ESCAPE operation, value and position are not applicable.
7. PRESS: Long click on an element, value is not applicable and the position [x,y] is required. 
"""

_NAV_FORMAT = """
Format the action as a dictionary with the following keys:
{'action': 'ACTION_TYPE', 'value': 'element', 'position': [x,y]}

If value or position is not applicable, set it as None.
Position might be [[x1,y1], [x2,y2]] if the action requires a start and end position.
Position represents the relative coordinates on the screenshot and should be scaled to a range of 0-1.
"""

class ShowUI_Agent:
    def __init__(
        self,
        model_name: str,
        system_prompt: str,
        remote_client: VNCClient_SSH,
        min_pixels: int,
        max_pixels: int,
    ):
        
        # Perform device count check
        if torch.cuda.device_count() != 1:
            raise NotImplementedError(f'ShowUI only verified for running on one card. Comment out this line if you know what you are doing.')
        
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto"
        )
        self.processor = AutoProcessor.from_pretrained(model_name, min_pixels=min_pixels, max_pixels=max_pixels)

        self.system_prompt = system_prompt
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
        self.action_history = ''

        self.remote_client = remote_client

    def call_agent(self, task: str, screenshot: Image.Image):

        # Construct messages
        if len(self.action_history) == 0:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.system_prompt},
                        {"type": "text", "text": f'Task: {task}'},
                        # {"type": "text", "text": PAST_ACTION},
                        {"type": "image", "image": pil_to_b64(screenshot), "min_pixels": self.min_pixels, "max_pixels": self.max_pixels},
                    ],
                }
            ]
        else:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.system_prompt},
                        {"type": "text", "text": f'Task: {task}'},
                        {"type": "text", "text": self.action_history},
                        {"type": "image", "image": pil_to_b64(screenshot), "min_pixels": self.min_pixels, "max_pixels": self.max_pixels},
                    ],
                }
            ]

        # Prepare for generation
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.model.device)

        # Generate
        generated_ids = self.model.generate(**inputs, max_new_tokens=128)
        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]

        return output_text
    
    def parse_agent_output(self, output_text):
        # https://github.com/showlab/computer_use_ootb/blob/58ff12c63d4bcc4d1d0ed841644da12d80d8ebfc/computer_use_demo/gui_agent/actor/showui_agent.py#L151

        try:
            # Ensure the output is stripped of any extra spaces
            output_text = output_text.strip()

            # Wrap the input in brackets if it looks like a single dictionary
            if output_text.startswith("{") and output_text.endswith("}"):
                output_text = f"[{output_text}]"

            # Validate if the output resembles a list of dictionaries
            if not (output_text.startswith("[") and output_text.endswith("]")):
                raise ValueError("Output does not look like a valid list or dictionary.")

            # Parse the output using ast.literal_eval
            parsed_output = ast.literal_eval(output_text)

            # Ensure the result is a list
            if isinstance(parsed_output, dict):
                parsed_output = [parsed_output]
            elif not isinstance(parsed_output, list):
                raise ValueError("Parsed output is neither a dictionary nor a list.")

            # Ensure all elements in the list are dictionaries
            if not all(isinstance(item, dict) for item in parsed_output):
                raise ValueError("Not all items in the parsed output are dictionaries.")

            return parsed_output
        
        except Exception as e:
            return []

    def execute_actions(self, parsed_actions: list):
        status = "unfinished"
        for action in parsed_actions:
            if 'value' not in action:
                action['value'] = None
            if 'position' not in action:
                action['position'] = None

            act = action['action'].lower()
            value = action['value']
            position = action['position']

            try:
                if act == 'click':
                    self.remote_client.move_to(position[0], position[1])
                    self.remote_client.left_click()
                elif act == 'input':
                    self.remote_client.type_text(value)
                elif act == 'hover':
                    self.remote_client.move_to(position[0], position[1])
                elif act == 'enter':
                    self.remote_client.key_press('enter')
                elif act == 'scroll':
                    # Scroll for 50% of screen width/height
                    if value == 'up':
                        self.remote_client.scroll_up(0.5)
                    elif value == 'down':
                        self.remote_client.scroll_down(0.5)
                    elif value == 'left':
                        self.remote_client.scroll_left(0.5)
                    elif value == 'right':
                        self.remote_client.scroll_right(0.5)
                    else:
                        raise ValueError(f'Scrolling direction should be up/down/left/right; got {value}')
                elif action == 'esc':
                    self.remote_client.key_press('esc')
                elif action == 'press':
                    self.remote_client.move_to(position[0], position[1])
                    self.remote_client.client.mouseDown(1)
                    time.sleep(3) # Hold for 3 seconds
                    self.remote_client.client.mouseUp(1)
            except Exception as e:
                print(f'Failed to parse action {action}')

            time.sleep(self.remote_client.action_interval_seconds)

        return status
            
    
    def step(
        self,

        task_id: int,
        current_step: int,
        max_steps: int,
        env_language: str,
        task_language: str,

        task: str,
        task_step_timeout: int,
        save_dir: str,
    ):
        # with timeout(task_step_timeout):
        # Capture screenshot
        print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = 'Capturing screenshot...')
        current_screenshot = self.remote_client.capture_screenshot()

        # Prediction
        print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = 'Calling GUI agent...')
        raw_response = self.call_agent(task = task, screenshot = current_screenshot)

        # Action
        print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = 'Actuating...')
        parsed_actions = self.parse_agent_output(raw_response)
        status = self.execute_actions(parsed_actions)
            
        # Update action history
        if parsed_actions is not None:
            # Organise action history as in https://github.com/showlab/ShowUI/issues/5
            # Other implementations, such as computer use ootb, does not append action history to messages during each round of inference
            self.action_history = f'{parsed_actions}\n'

        # Save current_screenshot
        current_screenshot.save(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}.png'))

        # Save raw_response
        with open(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}_raw_response.txt'), 'w') as f:
            f.write(raw_response)

        # Dump parsed_actions
        if parsed_actions is not None:
            with open(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}_parsed_actions.json'), 'w') as f:
                json.dump(parsed_actions, f, indent=4)

        return status

    def save_conversation_history(self, save_dir: str):
        pass

    