import time
from typing import Any

from PIL import Image
from io import BytesIO
import os
import json

from google.api_core.exceptions import InvalidArgument
from vertexai.preview.generative_models import Image as VertexImage

from vertexai.preview.generative_models import (
    GenerativeModel,
    HarmBlockThreshold,
    HarmCategory,
    Content,
    Part
)

from utils.VNCClient import VNCClient_SSH
from utils.log import print_message
from utils.timeout import timeout



GEMINI_SYSTEM_PROMPT = """
You are an agent that performs Mac desktop computer tasks by controlling mouse and keyboard through VNC. For each step, you will receive a screenshot observation of the computer screen and should predict the next action.

Your output must be raw text commands with the following structure:
```
<action_name> <parameter_1> <parameter_2>
<action_name> <parameter_1> <parameter_2>
...
```

For example:
```
move_to 0.25 0.5
key_press command-c
left_click
```

Available actions and their parameters:

1. Mouse Actions:
- "move_to": Move cursor to normalized coordinates
  Required params: {"x": float 0-1, "y": float 0-1}
  
- "left_click": Perform left mouse click
  No params required
  
- "middle_click": Perform middle mouse click
  No params required
  
- "right_click": Perform right mouse click
  No params required
  
- "double_click": Perform double left click
  No params required

- "triple_click": Perform triple left click
  No params required

- "drag_to": Drag with the left mouse button to a specified coordinate.
  Required params: {"x": float 0-1, "y": float 0-1}

- "mouse_down": Press and hold a mouse button.
  Required params: {"button": string ("left", "middle", "right")}

- "mouse_up": Release a mouse button.
  Required params: {"button": string ("left", "middle", "right")}

- "scroll_down": Scroll down by proportion of screen height
  Required params: {"amount": float 0-1}
  
- "scroll_up": Scroll up by proportion of screen height
  Required params: {"amount": float 0-1}

- "scroll_left": Scroll up by proportion of screen width
  Required params: {"amount": float 0-1}

- "scroll_right": Scroll up by proportion of screen width
  Required params: {"amount": float 0-1}

2. Keyboard Actions:
- "type_text": Type ASCII text
  Required params: {"text": string}
  Everything after `type_text ` will be parsed as parameter 1, including spaces. No need to escape any characters.
  
- "key_press": Press a key or key combination.
  Required params: {"key": string}
  Available keys: ctrl, command, option, backspace, tab, enter, esc, del, left, up, right, down, or single ASCII characters
  When pressing a combination of keys simultaneously, connect the keys using `-`, for example, `command-c` or `ctrl-alt-del`

3. Control Actions:
- "wait": Wait for specified seconds
  Required params: {"seconds": float}
  
- "fail": Indicate task cannot be completed
  No params required
  
- "done": Indicate task is already finished
  No params required

Important Notes:
- Your username is "ec2-user" and password is "000000"
- All coordinates (x,y) should be normalized between 0 and 1
- All scroll amounts should be normalized between 0 and 1
- Only ASCII characters are allowed for text input
- The control commands (wait, fail, done) must be the only command issued in a round. If one of these commands is used, no other actions should be provided alongside it.
- Return only the actions in a backtick-wrapped plaintext code block, one line per action, no other text
"""

GEMINI_SAFETY_CONFIG = {
    HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
}

def pil_to_vertex(img: Image.Image) -> str:
    with BytesIO() as image_buffer:
        img.save(image_buffer, format="PNG")
        byte_data = image_buffer.getvalue()
        img_vertex = VertexImage.from_bytes(byte_data)
    return img_vertex

class Gemini_General_Agent:
    def __init__(
        self,
        model: str,
        system_prompt: str,
        remote_client: VNCClient_SSH,
        only_n_most_recent_images: int,
        max_tokens: int,
        top_p: float,
        temperature: float,
        safety_config: dict,
    ):
        self.prompt_client = GenerativeModel(model)
        self.safety_config = safety_config
        self.system_prompt = system_prompt
        self.remote_client = remote_client

        self.max_tokens = max_tokens
        self.only_n_most_recent_images = only_n_most_recent_images
        self.top_p = top_p
        self.temperature = temperature
        
        self.messages = None
        self.screenshots = []

        self.token_usage = []
        self.total_prompt_tokens = 0
        self.total_candidates_tokens = 0

    def construct_user_prompt(self, task: str, screenshots: list):
        if len(screenshots) == 0:
            raise ValueError(f'Empty list of screenshots.')
        if len(screenshots) == 1:
            return [
                self.system_prompt,
                f'Task: {task}\nScreenshot: ',
                screenshots[0]
            ]
        return [
            self.system_prompt,
            f'Task: {task}\nRolling window of historical screenshots in chronological order: ',
            *screenshots[:-1],
            '\nCurrent screenshot: ',
            screenshots[-1]
        ]
    
    def call_agent(self, task: str):
        prompt = self.construct_user_prompt(task = task, screenshots = self.screenshots)

        response = self.prompt_client.generate_content(
            prompt,
            generation_config=dict(
                candidate_count=1,
                max_output_tokens=self.max_tokens,
                top_p=self.top_p,
                temperature=self.temperature,
            ),
            safety_settings=self.safety_config,
        )

        # Count token usage
        self.token_usage.append(
            {
                "prompt_token_count": response.usage_metadata.prompt_token_count,
                "candidates_token_count": response.usage_metadata.candidates_token_count
            }
        )
        self.total_prompt_tokens += response.usage_metadata.prompt_token_count
        self.total_candidates_tokens += response.usage_metadata.candidates_token_count

        response_text = response.candidates[0].content.parts[0].text
        return response_text
    
    def parse_agent_output(self, agent_output):
        """
        Parse the raw output string from the GUI agent into a list of actions.
        Each action is a dict with an "action" key and any required parameters.
        
        This function is robust to:
        - Extra surrounding backticks or triple backticks
        - Extra spaces and non-action text lines
        - Parameters provided with "key=value" format
        - Incomplete or misformatted lines (which will print an error and skip that line)
        """
        valid_actions = {"move_to", "left_click", "middle_click", "right_click", "double_click",
                        "scroll_down", "scroll_up", "type_text", "key_press", "wait", "fail", "done"}
        actions = []
        
        # Remove any surrounding backticks or triple backticks
        agent_output = agent_output.strip()
        if agent_output.startswith("```") and agent_output.endswith("```"):
            agent_output = agent_output[3:-3].strip()
        # Also remove any extra single backticks
        agent_output = agent_output.strip("`").strip()
        
        # Split the output into lines
        lines = agent_output.splitlines()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                # Split the line into tokens by whitespace.
                # Note: for type_text the text may contain spaces.
                tokens = line.split()
                if not tokens:
                    continue
                # The first token should be a valid action command.
                action_cmd = tokens[0].strip().lower()
                if action_cmd not in valid_actions:
                    # If the line does not begin with a valid command, ignore it.
                    continue

                action_dict = {"action": action_cmd}
                
                # Parse parameters based on the action command.
                if action_cmd in ["move_to", "drag_to"]:
                    # Expecting two parameters: x and y.
                    if len(tokens) < 3:
                        print(f"Error parsing line (move_to requires 2 parameters): {line}")
                        continue
                    def parse_float(token):
                        if "=" in token:
                            token = token.split("=")[-1]
                        return float(token)
                    action_dict["x"] = parse_float(tokens[1])
                    action_dict["y"] = parse_float(tokens[2])
                elif action_cmd in ["mouse_down", "mouse_up"]:
                    if len(tokens) < 2:
                        print(f"Error parsing line ({action_cmd} requires a button parameter): {line}")
                        continue
                    button = tokens[1]
                    if "=" in button:
                        button = button.split("=")[-1]
                    action_dict["button"] = button.lower()
                elif action_cmd in ["scroll_down", "scroll_up"]:
                    # Expecting one parameter: amount.
                    if len(tokens) < 2:
                        print(f"Error parsing line ({action_cmd} requires 1 parameter): {line}")
                        continue
                    token = tokens[1]
                    if "=" in token:
                        token = token.split("=")[-1]
                    try:
                        action_dict["amount"] = float(token)
                    except Exception as e:
                        print(f"Error parsing parameter for {action_cmd}: {line} - {e}")
                        continue
                elif action_cmd == "wait":
                    # Expecting one parameter: seconds.
                    if len(tokens) < 2:
                        print(f"Error parsing line (wait requires 1 parameter): {line}")
                        continue
                    token = tokens[1]
                    if "=" in token:
                        token = token.split("=")[-1]
                    try:
                        action_dict["seconds"] = float(token)
                    except Exception as e:
                        print(f"Error parsing parameter for wait: {line} - {e}")
                        continue
                elif action_cmd == "type_text":
                    # Instead of stripping unconditionally, get the raw text after the command.
                    raw_text = line[len(tokens[0]):]
                    # If the text is entirely whitespace, preserve it.
                    if raw_text.strip() == "":
                        text = raw_text
                    else:
                        # Otherwise, remove leading/trailing spaces and normalize spaces in the middle.
                        text = ' '.join(raw_text.split())
                    action_dict["text"] = text
                elif action_cmd == "key_press":
                    # Expecting one parameter: key.
                    if len(tokens) < 2:
                        print(f"Error parsing line (key_press requires a key parameter): {line}")
                        continue
                    key = tokens[1]
                    if "=" in key:
                        key = key.split("=")[-1]
                    action_dict["key"] = key
                # For actions that require no parameters (left_click, middle_click, right_click, double_click, fail, done)
                # no extra parsing is needed.
                
                actions.append(action_dict)
            except Exception as e:
                print(f"Error parsing line: {line} - {e}")
                continue
                
        return actions
    
    def execute_actions(self, actions):
        """
        Execute a list of parsed actions.
        
        For each action, the corresponding VNCClient_SSH method is called.
        If a 'fail' or 'done' command is encountered, execution stops and the function returns immediately.
        
        Returns a tuple (status, actions_executed) where status is one of:
          - "done" if a 'done' command was executed,
          - "fail" if a 'fail' command was executed,
          - "unfinished" if neither was encountered.
        
        Note: This function does not use error handling; any errors during execution will propagate.
        """
        status = "unfinished"
        for action in actions:
            act = action.get("action")
            time.sleep(self.remote_client.action_interval_seconds)
            if act == "move_to":
                self.remote_client.move_to(action["x"], action["y"])
            elif act == "mouse_down":
                self.remote_client.mouse_down(action["button"])
            elif act == "mouse_up":
                self.remote_client.mouse_up(action["button"])
            elif act == "left_click":
                self.remote_client.left_click()
            elif act == "middle_click":
                self.remote_client.middle_click()
            elif act == "right_click":
                self.remote_client.right_click()
            elif act == "double_click":
                self.remote_client.double_click()
            elif act == "triple_click":
                self.remote_client.triple_click()
            elif act == "drag_to":
                self.remote_client.drag_to(action["x"], action["y"])
            elif act == "scroll_down":
                self.remote_client.scroll_down(action["amount"])
            elif act == "scroll_up":
                self.remote_client.scroll_up(action["amount"])
            elif act == "scroll_left":
                self.remote_client.scroll_left(action["amount"])
            elif act == "scroll_right":
                self.remote_client.scroll_right(action["amount"])
            elif act == "type_text":
                self.remote_client.type_text(action["text"])
            elif act == "key_press":
                self.remote_client.key_press(action["key"])
            elif act == "wait":
                time.sleep(action["seconds"])
            elif act == "fail":
                status = "fail"
                return status, actions
            elif act == "done":
                status = "done"
                return status, actions
        return status, actions

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
        self.screenshots.append(pil_to_vertex(current_screenshot))
        if self.only_n_most_recent_images > 0:
            self.screenshots = self.screenshots[-self.only_n_most_recent_images:]
        
        # Prediction
        print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = 'Calling GUI agent...')
        raw_response = self.call_agent(task = task)

        # Action
        print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = 'Actuating...')
        parsed_actions = self.parse_agent_output(raw_response)
        status, _ = self.execute_actions(parsed_actions)

        # Save current_screenshot
        current_screenshot.save(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}.png'))

        # Save raw_response
        with open(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}_raw_response.txt'), 'w') as f:
            f.write(raw_response)

        # Dump parsed_actions
        with open(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}_parsed_actions.json'), 'w') as f:
            json.dump(parsed_actions, f, indent=4)

        return status
    
    def save_conversation_history(self, save_dir: str):
        pass