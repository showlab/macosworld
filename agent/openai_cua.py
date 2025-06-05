from agent.llm_utils import pil_to_b64
from PIL import Image
from utils.VNCClient import VNCClient_SSH
from utils.log import print_message
import os
import json
import requests
import time
from constants import SCREEN_WIDTH, SCREEN_HEIGHT

CUA_SYSTEM_PROMPT = """You are using a macOS computer to complete a user-given task. Additional Notes:
* Available xdotool keys: ctrl, command, option, backspace, tab, enter, esc, del, left, up, right, down, and single ASCII characters.
* When you think the task can not be done, say ```FAIL```, don't easily say ```FAIL```, try your best to do the task. When you think the task is completed, say ```DONE```. Include the three backticks. If the task is not completed, don't raise any of these two flags.
* You may need my username and password. My username is `ec2-user` and password is `000000`.
"""

class OpenAI_CUA:
    def __init__(
        self,
        model: str,
        system_prompt: str,
        remote_client: VNCClient_SSH,
        only_n_most_recent_images: int,
        top_p: float,
        temperature: float,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.remote_client = remote_client
        self.only_n_most_recent_images = only_n_most_recent_images
        self.top_p = top_p
        self.temperature = temperature

        self.tools = [
            {
                "type": "computer-preview",
                "display_width": SCREEN_WIDTH,
                "display_height": SCREEN_HEIGHT,
                "environment": "mac" # other possible values: "browser", "windows", "ubuntu"
            },
        ]

        self.messages = []
        self.token_usage = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def create_response(self, **kwargs):
        """
        https://github.com/openai/openai-cua-sample-app/blob/main/utils.py#L50

        Required kwargs: model, input, tools, truncation
        Example: {
            model: str,
            input = [{"role": "user", "content": "what is the weather in sf"}],
            tools = [
                {
                    "type": "computer-preview",
                    "display_width": 1024,
                    "display_height": 768,
                    "environment": "mac" # other possible values: "browser", "windows", "ubuntu"
                },
            ],
            truncation = "auto"
        }
        """
        

        url = "https://api.openai.com/v1/responses"
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }

        openai_org = os.getenv("OPENAI_ORG")
        if openai_org:
            headers["Openai-Organization"] = openai_org

        response = requests.post(url, headers=headers, json=kwargs)

        if response.status_code != 200:
            print(f"Error: {response.status_code} {response.text}")

        return response.json()
    
    def call_agent(self, task: str) -> list:

        # Include task in messages
        if len(self.messages) == 0:
            if self.system_prompt is not None:
                self.messages.append({"role": "system", "content": self.system_prompt})
            self.messages.append({"role": "user", "content": task})

        # Call API
        response = self.create_response(
            model = "computer-use-preview-2025-03-11",
            input = self.messages,
            tools = self.tools,
            truncation = "auto",
            temperature = self.temperature,
            top_p = self.top_p
        )

        # Check if call is successful
        if 'output' not in response:
            raise RuntimeError(f'Key "output" not in OpenAI CUA response dict. Current response dict:\n{response}')
        
        # Log token usage
        self.token_usage.append(response['usage'])
        self.total_input_tokens += response['usage']['input_tokens']
        self.total_output_tokens += response['usage']['output_tokens']

        return response['output']
    
    def filter_reasoning_messages(self):
        # The function would remove all reasoning items in self.messages
        raise DeprecationWarning('The method is deprecated.')
        for message_index in range(len(self.messages) - 1, -1, -1):
            if 'type' in self.messages[message_index]:
                if self.messages[message_index]['type'] == 'reasoning':
                    del self.messages[message_index]
    
    def filter_to_n_most_recent_images(self, n: int):
        # The function would only consider images within computer_call_output blocks
        call_id_to_remove = []
        for message_index in range(len(self.messages) - 1, -1, -1):
            if 'type' in self.messages[message_index] and 'output' in self.messages[message_index]:
                if self.messages[message_index]['type'] == 'computer_call_output' and isinstance(self.messages[message_index]['output'], dict):
                    if 'type' in self.messages[message_index]['output']:
                        if self.messages[message_index]['output']['type'] == 'input_image':
                            if n > 0:
                                n -= 1
                            else:
                                self.messages[message_index]['output']['image_url'] = pil_to_b64(Image.new('RGB', (7, 7), (0, 0, 0))) # Substitute with a 7x7 pure black image
                                # call_id_to_remove.append(self.messages[message_index]['call_id'])
                                # del self.messages[message_index]

        # for message_index in range(len(self.messages) - 1, -1, -1):
        #     if 'call_id' in self.messages[message_index]:
        #         if self.messages[message_index]['call_id'] in call_id_to_remove:
        #             del self.messages[message_index]

    def actuate(self, action: dict):
        """
        Execute an action.

        Input: a dictionary that represents an action. Example: {'type': 'click', 'button': 'left', 'x': 225, 'y': 250}

        Output: None

        Notes
            - Action space follows https://github.com/openai/openai-cua-sample-app/blob/main/computers/docker.py
            - Following https://github.com/openai/openai-cua-sample-app/blob/main/agent/agent.py#L94, screenshots would be provided after each action, so this actuation function would not separately handle screenshots
        """
        action_type = action["type"]
        # action_args = {k: v for k, v in action.items() if k != "type"}

        if action_type == "screenshot":
            pass
        elif action_type == "click":
            if 'x' in action and 'y' in action:
                self.remote_client.move_to_pixel(action['x'], action['y'])
            if "button" not in action:
                print(f'Error parsing action {action}: button to click not provided')
            elif action["button"] == 'left':
                self.remote_client.left_click()
            elif action["button"] == 'middle': 
                self.remote_client.middle_click()
            elif action["button"] == 'right':
                self.remote_client.right_click()
            else:
                print(f'Error parsing action {action}: invalid button to click')
        elif action_type == "double_click":
            if 'x' in action and 'y' in action:
                self.remote_client.move_to_pixel(action['x'], action['y'])
            self.remote_client.double_click()
        elif action_type == "scroll":
            if 'x' in action and 'y' in action:
                self.remote_client.move_to_pixel(action['x'], action['y'])
            if 'scroll_x' in action:
                if action['scroll_x'] < 0:
                    self.remote_client.scroll_up(-action['scroll_x'])
                if action['scroll_x'] > 0:
                    self.remote_client.scroll_down(action['scroll_x'])
            if 'scroll_y' in action:
                if action['scroll_y'] < 0:
                    self.remote_client.scroll_up(-action['scroll_y'])
                if action['scroll_y'] > 0:
                    self.remote_client.scroll_down(action['scroll_y'])
        elif action_type == "type":
            self.remote_client.type_text(action['text'])
        elif action_type == 'wait':
            if 'ms' in action:
                time.sleep(action['ms'] / 1000)
            else:
                wait_seconds = 1 # https://github.com/openai/openai-cua-sample-app/blob/main/computers/docker.py#L134
                time.sleep(wait_seconds)
        elif action_type == 'move':
            self.remote_client.move_to_pixel(action['x'], action['y'])
        elif action_type == 'keypress':
            key_combo = "-".join(action['keys'])
            self.remote_client.key_press(key_combo)
        elif action_type == 'drag':
            waypoints = action['path']
            self.remote_client.move_to_pixel(waypoints[0]['x'], waypoints[0]['y'])
            self.remote_client.client.mouseDown(1)
            for waypoint in waypoints[1:]:
                self.remote_client.move_to_pixel(waypoint['x'], waypoint['y'])
            self.remote_client.client.mouseUp(1)
            

    def handle_response_item(self, item: dict, save_dir: str, current_step: int, current_action: int):
        """
        Handle each response item; may cause a computer action + screenshot.
        
        Returns a tuple of 2 elements:
            1. A list containing items that represent computer-use results (e.g. containing a screenshot); should be added to the tail of self.messages
            2. A status str indicating whether the task is finished/unfinished or failed
        """
        if item["type"] == "message":
            # Check if the message contain status signals
            if "```DONE```" in item["content"][0]['text']:
                return [], "done"
            if "```FAIL```" in item["content"][0]['text']:
                return [], "fail"
            return [], None
        
        if item["type"] == "reasoning":
            return [], None
        
        if item["type"] == "function_call":
            raise NotImplementedError(f'Unexpected function call')

        if item["type"] == "computer_call":
            # Implement the action
            action = item["action"]
            try:
                self.actuate(action)
            except Exception as e:
                print(f'Error parsing action {action}: {e}')

            # Take a screenshot
            current_screenshot = self.remote_client.capture_screenshot()
            current_screenshot.save(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}_item_{str(current_action).zfill(3)}.png'))

            call_output = {
                # https://github.com/openai/openai-cua-sample-app/blob/main/agent/agent.py#L94
                "type": "computer_call_output",
                "call_id": item["call_id"],
                "acknowledged_safety_checks": item.get("pending_safety_checks", []), # Acknowledging all safety checks
                "output": {
                    "type": "input_image",
                    "image_url": pil_to_b64(current_screenshot),
                },
            }

            return [call_output], None
        
        return [], None

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
        
        step_status = "unfinished"

        # [Step 1] Message preparation
        if self.only_n_most_recent_images > 0:
            self.filter_to_n_most_recent_images(self.only_n_most_recent_images)

        # [Step 2] Agent prediction
        print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = 'Calling GUI agent...')

        raw_response: list = self.call_agent(task)
        self.messages += raw_response

        # [Step 3] Actuation
        print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = 'Actuating...')

        for idx, response_item in enumerate(raw_response):
            # Handle each item in the raw response; if it is a computer_use call, then its action would be actuated; if it is a message, then its content would be checked to determine whether the task is finished or not
            response_item_result, action_status = self.handle_response_item(response_item, save_dir, current_step, idx)

            # Add computer use results to the tail of messages
            self.messages += response_item_result

            # If there is a change in status, update that status and lock against future updates
            if step_status == "unfinished" and action_status is not None:
                step_status = action_status

        # Save raw_response
        with open(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}_raw_response.txt'), 'w') as f:
            json.dump(raw_response, f)

        return step_status

    def save_conversation_history(self, save_dir: str):
        # Remove all images before saving chat log
        self.filter_to_n_most_recent_images(0)
        
        file = os.path.join(save_dir, 'context', 'chat_log.json')
        with open(file, "w") as json_file:
            json.dump(self.messages, json_file)

        self.token_usage.append({
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens
        })
        file = os.path.join(save_dir, 'context', 'token_usage.json')
        with open(file, "w") as json_file:
            json.dump(self.token_usage, json_file)