import anthropic
from agent.llm_utils import pil_to_b64
from utils.VNCClient import VNCClient_SSH
from utils.log import print_message
from utils.timeout import timeout
import time
import os
import json
from typing import cast
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessage,
    BetaTextBlock,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)

CLAUDE_CUA_SYSTEM_PROMPT = """
Additional Notes:
* Available xdotool keys: ctrl, command, option, backspace, tab, enter, esc, del, left, up, right, down, and single ASCII characters.
* When you think the task can not be done, say ```FAIL```, don't easily say ```FAIL```, try your best to do the task. When you think the task is completed, say ```DONE```. Include the three backticks. If the task is not completed, don't raise any of these two flags.
* At the end of each step (except for the last step), always take a screenshot. In the next round, carefully evaluate if you have achieved the right outcome. Explicitly show your thinking: "I have evaluated step X..." If not correct, try again. Only when you confirm a step was executed correctly should you move on to the next one.
* You may need my username and password. My username is `ec2-user` and password is `000000`.
"""

class ClaudeComputerUseAgent:
    def __init__(
        self,
        model: str,
        betas: list,
        max_tokens: int,
        display_width: int,
        display_height: int,
        only_n_most_recent_images: int,
        system_prompt: str,
        remote_client: VNCClient_SSH,
    ):
        self.model = model
        self.betas = betas
        self.max_tokens = max_tokens
        self.display_width = display_width
        self.display_height = display_height
        self.only_n_most_recent_images = only_n_most_recent_images
        self.system_prompt = system_prompt

        self.messages = []
        self.token_usage = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        self.client = anthropic.Anthropic()
        self.tools = [
            {
                "type": "computer_20250124",
                "name": "computer",
                "display_width_px": self.display_width,
                "display_height_px": self.display_height,
                "display_number": 1,
            }
        ]

        self.remote_client = remote_client

    def call_agent(self, step_index: int):
        if self.system_prompt is None:
            response = self.client.beta.messages.create(
                model = self.model,
                max_tokens = self.max_tokens,
                tools = self.tools,
                messages = self.messages,
                betas = self.betas
            )
        else:
            response = self.client.beta.messages.create(
                model = self.model,
                max_tokens = self.max_tokens,
                tools = self.tools,
                messages = self.messages,
                system = self.system_prompt,
                betas = self.betas
            )

        # Count token usage
        self.token_usage.append(
            {
                "step": step_index,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }
        )
        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.input_tokens
        return response
    
    def execute_action(self, action_dict: dict):
        """
        Execute an action based on the input dictionary.
        
        Expected dictionary keys:
        - "action": string specifying the action.
        - "coordinate": [x, y] pixel coordinates (for mouse_move, left_click_drag, etc.)
        - "duration": integer (for hold_key and wait actions)
        - "scroll_amount": integer (for scroll action)
        - "scroll_direction": one of ["up", "down", "left", "right"] (for scroll action)
        - "start_coordinate": [x, y] for left_click_drag action
        - "text": string for key press or type actions (or key combination to hold during a click)
        
        Returns:
            A tuple of three parameters: (
                True/False indicating status of action,
                List of dicts containing tool result content; could be None,
                (Optional) PIL.Image screenshot
            )
        """
        action = action_dict.get("action")
        
        if action == "key":
            # Send a key press using xdotool syntax
            text = action_dict.get("text", "")
            self.remote_client.key_press(text)
            return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "hold_key":
            # Hold down a key or multiple keys for a specified duration (in seconds).
            duration_seconds = int(action_dict.get("duration"))
            text = action_dict.get("text", "")
            self.remote_client.key_press_and_hold(text, duration_seconds)
            return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "type":
            # Type a string of text.
            text = action_dict.get("text", "")
            self.remote_client.type_text(text)
            return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "cursor_position":
            # Use osascript to get the current cursor position.
            # The command returns a string like "1234.56, 789.01"
            command = """osascript -l JavaScript -e 'ObjC.import("CoreGraphics"); var loc = $.CGEventGetLocation($.CGEventCreate(null)); loc.x + ", " + loc.y'"""
            success, output = self.remote_client.run_ssh_command(command)
            if success:
                try:
                    parts = output.split(",")
                    x = float(parts[0].strip())
                    y = float(parts[1].strip())
                    return True, {"type": "text", "text": f"Tool executed successfully. Cursor position: {output}"}
                except Exception as e:
                    print(f"Error performing action dict `{action_dict}`: Failed to parse cursor position output: {e}")
                    return False, None, None
            else:
                print(f"Error performing action dict `{action_dict}`: Failed to retrieve cursor position via SSH command.")
                return False, None, None
        
        elif action == "mouse_move":
            # Move the mouse to a given pixel coordinate.
            coordinate = action_dict.get("coordinate")
            if coordinate and len(coordinate) == 2:
                x, y = coordinate
                self.remote_client.move_to_pixel(x, y)
                return True, [{"type": "text", "text": "Tool executed successfully"}], None
            else:
                print(f"Error parsing action dict `{action_dict}`: 'coordinate' parameter is required for mouse_move.")
                return False, None, None
        
        elif action == "left_mouse_down":
            self.remote_client.mouse_down("left")
            return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "left_mouse_up":
            self.remote_client.mouse_up("left")
            return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "left_click":
            # Optionally move to a coordinate if provided.
            coordinate = action_dict.get("coordinate")

            # Key down
            if "text" in action_dict:
                key = action_dict.get("text", "")
                key = self.remote_client._filter_key(key)
                self.remote_client.client.keyDown(key)

            # Move cursor
            if coordinate and len(coordinate) == 2:
                x, y = coordinate
                self.remote_client.move_to_pixel(x, y)

            # Click
            self.remote_client.left_click()

            # Key up
            if "text" in action_dict:
                self.remote_client.client.keyUp(key)
            return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "left_click_drag":
            # Drag from start_coordinate to coordinate.
            start_coordinate = action_dict.get("start_coordinate")
            coordinate = action_dict.get("coordinate")
            if (start_coordinate and len(start_coordinate) == 2 and
                coordinate and len(coordinate) == 2):
                # Move to the starting coordinate.
                x0, y0 = start_coordinate
                self.remote_client.move_to_pixel(x0, y0)
                # Press and hold the left mouse button.
                self.remote_client.mouse_down("left")
                # Move to the destination coordinate.
                x1, y1 = coordinate
                self.remote_client.move_to_pixel(x1, y1)
                # Release the mouse button.
                self.remote_client.mouse_up("left")
                return True, [{"type": "text", "text": "Tool executed successfully"}], None
            else:
                print(f"Error parsing action dict `{action_dict}`: 'start_coordinate' and 'coordinate' parameters are required for left_click_drag.")
                return False, None, None
        
        elif action == "right_click":
            coordinate = action_dict.get("coordinate")
            if coordinate and len(coordinate) == 2:
                x, y = coordinate
                self.remote_client.move_to_pixel(x, y)
            self.remote_client.right_click()
            return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "middle_click":
            coordinate = action_dict.get("coordinate")
            if coordinate and len(coordinate) == 2:
                x, y = coordinate
                self.remote_client.move_to_pixel(x, y)
            self.remote_client.middle_click()
            return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "double_click":
            coordinate = action_dict.get("coordinate")
            if coordinate and len(coordinate) == 2:
                x, y = coordinate
                self.remote_client.move_to_pixel(x, y)
            self.remote_client.double_click()
            return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "triple_click":
            # Triple-click is simulated by three consecutive left clicks.
            coordinate = action_dict.get("coordinate")
            if coordinate and len(coordinate) == 2:
                x, y = coordinate
                self.remote_client.move_to_pixel(x, y)
            self.remote_client.triple_click()
            return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "scroll":
            # Scroll using the scroll wheel. Optionally move to a coordinate first.
            scroll_amount = action_dict.get("scroll_amount") * 100 # Factor to amplify scrolling
            scroll_direction = action_dict.get("scroll_direction")
            if scroll_amount is None or scroll_direction is None:
                print(f"Error parsing action dict `{action_dict}`: 'scroll_amount' and 'scroll_direction' are required for scroll.")
                return False, None, None
            else:
                coordinate = action_dict.get("coordinate")
                if coordinate and len(coordinate) == 2:
                    x, y = coordinate
                    self.remote_client.move_to_pixel(x, y)
                if scroll_direction == "up":
                    self.remote_client.scroll_up(scroll_amount, by_pixel=True)
                    return True, [{"type": "text", "text": "Tool executed successfully"}], None
                elif scroll_direction == "down":
                    self.remote_client.scroll_down(scroll_amount, by_pixel=True)
                    return True, [{"type": "text", "text": "Tool executed successfully"}], None
                elif scroll_direction == "left":
                    self.remote_client.scroll_left(scroll_amount, by_pixel=True)
                    return True, [{"type": "text", "text": "Tool executed successfully"}], None
                elif scroll_direction == "right":
                    self.remote_client.scroll_right(scroll_amount, by_pixel=True)
                    return True, [{"type": "text", "text": "Tool executed successfully"}], None
                else:
                    print(f"Error parsing action dict `{action_dict}`: Invalid scroll_direction '{scroll_direction}'.")
                    return False, None, None
        
        elif action == "wait":
            duration = action_dict.get("duration")
            if duration is None:
                print(f"Error parsing action dict `{action_dict}`: 'duration' is required for wait.")
                return False, None, None
            else:
                time.sleep(duration)
                return True, [{"type": "text", "text": "Tool executed successfully"}], None
        
        elif action == "screenshot":
            image = self.remote_client.capture_screenshot()
            if image is None:
                return False, None, None
            else:
                return True, [
                    {"type": "text", "text": "Tool executed successfully"},{
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": pil_to_b64(image, add_prefix=False)
                        }
                    }
                ], image
        
        else:
            print(f"Error parsing action dict `{action_dict}`: Unknown action '{action}'.")
            return False, None, None

    def _response_to_params(
        self,
        response: BetaMessage,
    ) -> list[BetaContentBlockParam]:
        res: list[BetaContentBlockParam] = []
        for block in response.content:
            if isinstance(block, BetaTextBlock):
                if block.text:
                    res.append(BetaTextBlockParam(type="text", text=block.text))
                elif getattr(block, "type", None) == "thinking":
                    # Handle thinking blocks - include signature field
                    thinking_block = {
                        "type": "thinking",
                        "thinking": getattr(block, "thinking", None),
                    }
                    if hasattr(block, "signature"):
                        thinking_block["signature"] = getattr(block, "signature", None)
                    res.append(cast(BetaContentBlockParam, thinking_block))
            else:
                # Handle tool use blocks normally
                res.append(cast(BetaToolUseBlockParam, block.model_dump()))
        return res

    def tool_result_to_params(self, tool_use_id: str, status: bool, tool_result_content: list):
        if tool_result_content is None:
            tool_result_content = []
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "content": tool_result_content,
                    "tool_use_id": tool_use_id,
                    "is_error": status == False,
                }
            ]
        }
    
    def filter_to_n_most_recent_images(self, n: int):
        # The function would only consider images within tool_result blocks
        for message_index in range(len(self.messages) - 1, -1, -1):
            if self.messages[message_index]['role'] == 'user':
                for message_content_index in range(len(self.messages[message_index]['content']) - 1, -1, -1):
                    if isinstance(self.messages[message_index]['content'], list):
                        if self.messages[message_index]['content'][message_content_index]['type'] == 'tool_result':
                            for message_content_content_index in range(len(self.messages[message_index]['content'][message_content_index]['content']) - 1, -1, -1):
                                if self.messages[message_index]['content'][message_content_index]['content'][message_content_content_index]['type'] == 'image':
                                    if n > 0:
                                        n -= 1
                                    else:
                                        # Remove item `messages[message_index]['content'][message_content_index]['content'][message_content_content_index]` from the list `messages[message_index]['content'][message_content_index]['content']` 
                                        del self.messages[message_index]['content'][message_content_index]['content'][message_content_content_index]

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

        # with timeout(task_step_timeout):
        
        # [Step 1] Message preparation
        if len(self.messages) == 0:
            # Append task at the beginning of the conversation
            task_block = {
                "role": "user",
                "content": task,
            }
            self.messages.append(task_block)

        if self.only_n_most_recent_images > 0:
            self.filter_to_n_most_recent_images(self.only_n_most_recent_images)

        # [Step 2] Agent prediction
        print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = 'Calling GUI agent...')

        response = self.call_agent(current_step)
        agent_response_block = {
            "role": "assistant",
            "content": self._response_to_params(response)
        }
        self.messages.append(agent_response_block)

        # [Step 3] Acutation

        print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = 'Actuating...')

        response_content = response.content

        for block in response_content:
            if block.type == "tool_use":
                # Perform actions
                status, tool_result_content, current_screenshot = self.execute_action(block.input)
                tool_result_message_block = self.tool_result_to_params(
                    tool_use_id = block.id,
                    status = status,
                    tool_result_content = tool_result_content
                )
                self.messages.append(tool_result_message_block)

                # Save screenshot
                if current_screenshot is not None:
                    current_screenshot.save(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}.png'))

            elif block.type == 'text':
                if "```DONE```" in block.text:
                    step_status = "done"
                elif "```FAIL```" in block.text:
                    step_status = "fail"
        
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