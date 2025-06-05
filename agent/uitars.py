from openai import OpenAI
import os
from utils.VNCClient import VNCClient_SSH
from utils.log import print_message
from agent.llm_utils import pil_to_b64
from PIL import Image
import json
from utils.timeout import timeout
import time
import re


# https://github.com/bytedance/UI-TARS
UITARS_COMPUTER_SYSTEM_PROMPT = r"""You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. 

## Output Format
```\nThought: ...
Action: ...\n```

## Action Space

click(start_box='<|box_start|>(x1,y1)<|box_end|>')
left_double(start_box='<|box_start|>(x1,y1)<|box_end|>')
right_single(start_box='<|box_start|>(x1,y1)<|box_end|>')
drag(start_box='<|box_start|>(x1,y1)<|box_end|>', end_box='<|box_start|>(x3,y3)<|box_end|>')
hotkey(key='')
type(content='') #If you want to submit your input, use \"\
\" at the end of `content`.
scroll(start_box='<|box_start|>(x1,y1)<|box_end|>', direction='down or up or right or left')
wait() #Sleep for 5s and take a screenshot to check for any changes.
finished()
call_user() # Submit the task and call the user when the task is unsolvable, or when you need the user's help.


## Note
- Use Chinese in `Thought` part.
- Summarize your next action (with its target element) in one sentence in `Thought` part.
- Available hotkeys: ctrl, command, option, backspace, tab, enter, esc, del, left, up, right, down, and all standalone ASCII characters

## User Instruction
"""

class UITARS_GUI_AGENT:
    def __init__(
        self,
        model: str,
        vllm_base_url: str,
        system_prompt: str,
        remote_client: VNCClient_SSH,
        only_n_most_recent_images: int,
        max_tokens: int,
        top_p: float,
        temperature: float,
    ):
        self.prompt_client = OpenAI(
            base_url=vllm_base_url,
            api_key="empty",
        )
        self.model = model
        self.system_prompt = system_prompt
        self.remote_client = remote_client
        self.only_n_most_recent_images = only_n_most_recent_images
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.temperature = temperature

        self.screenshots = []
        self.messages = []

        self.token_usage = []
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def format_messages(self, task: str, screenshot: str):
        if len(self.messages) == 0:
            self.messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": self.system_prompt + task},
                ]
            })
        self.messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": pil_to_b64(screenshot)}
                }
            ]
        })

    def filter_to_n_most_recent_images(self, n: int):
        for message_index in range(len(self.messages) - 1, -1, -1):
            if self.messages[message_index]['role'] == 'user':
                if isinstance(self.messages[message_index]['content'], list):
                    for message_content_index in range(len(self.messages[message_index]['content']) - 1, -1, -1):
                        if self.messages[message_index]['content'][message_content_index]['type'] == 'image_url':
                            if n > 0:
                                n -= 1
                            else:
                                del self.messages[message_index]['content'][message_content_index]
                    if len(self.messages[message_index]['content']) == 0:
                        del self.messages[message_index]

    def call_agent(self, task: str, screenshot: Image.Image) -> str:
        self.format_messages(task = task, screenshot = screenshot)

        self.filter_to_n_most_recent_images(self.only_n_most_recent_images)

        # Agent inference
        response = self.prompt_client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            frequency_penalty=1,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            temperature=self.temperature,
        )
        response_content = response.choices[0].message.content

        # Append response_content to messages
        self.messages.append({
            "role": "assistant",
            "content": [
                {"type": "text", "text": response_content}
            ]
        })

        # Count tokens
        self.token_usage.append(
            {
                "step": "step_index",
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens
            }
        )
        self.total_prompt_tokens += response.usage.prompt_tokens
        self.total_completion_tokens += response.usage.completion_tokens

        return response_content

    def parse_coordinate(self, coord_str):
        """
        Parse a coordinate string of the form '(x,y)' and return a tuple (x, y) as integers.
        """
        try:
            # Remove outer parentheses and possible spaces
            if coord_str.startswith('(') and coord_str.endswith(')'):
                inner = coord_str[1:-1]
                parts = inner.split(',')
                if len(parts) != 2:
                    raise ValueError("Coordinate does not contain exactly two values.")
                x = int(parts[0].strip())
                y = int(parts[1].strip())
                return (x, y)
            else:
                raise ValueError("Coordinate does not start with '(' and end with ')'.")
        except Exception as e:
            raise ValueError(f"Invalid coordinate format '{coord_str}': {e}")

    def convert_hotkey(self, key_str):
        """
        Convert a space-separated key string to a dash-separated key string.
        For example: 'ctrl alt t' -> 'ctrl-alt-t'
        """
        # Remove extra spaces and join with dash
        keys = key_str.strip().split()
        return '-'.join(keys)

    def parse_kwargs(self, params_str):
        """
        Parse a parameter string of the format key='value', key2='value2' etc.
        Return a dictionary of the parameters.
        
        The parser assumes:
        - The key is a valid identifier.
        - The value is enclosed in single quotes.
        - Only the escape sequences \t, \n, and \' are valid inside the value.
        """
        kwargs = {}
        i = 0
        n = len(params_str)
        while i < n:
            # Skip whitespace and commas
            while i < n and params_str[i] in " \t\n\r,":
                i += 1
            if i >= n:
                break
            
            # Parse key (match word characters)
            key_match = re.match(r'(\w+)', params_str[i:])
            if not key_match:
                raise ValueError(f"Expected a key at: {params_str[i:]}")
            key = key_match.group(1)
            i += key_match.end()
            
            # Skip whitespace
            while i < n and params_str[i] in " \t":
                i += 1
            
            # Expect '='
            if i >= n or params_str[i] != '=':
                raise ValueError(f"Expected '=' after key '{key}'. Found: {params_str[i:]}")
            i += 1  # skip '='
            
            # Skip whitespace
            while i < n and params_str[i] in " \t":
                i += 1
            
            # Expect opening single quote
            if i >= n or params_str[i] != "'":
                raise ValueError(f"Expected opening quote for value of key '{key}' at: {params_str[i:]}")
            i += 1  # skip the opening quote
            
            # Parse the value until an unescaped single quote is encountered.
            value_chars = []
            while i < n:
                ch = params_str[i]
                if ch == '\\':
                    # If next character is part of valid escape sequence, process it.
                    if i + 1 < n and params_str[i+1] in ["'", "n", "t"]:
                        next_ch = params_str[i+1]
                        if next_ch == 'n':
                            value_chars.append("\n")
                        elif next_ch == 't':
                            value_chars.append("\t")
                        elif next_ch == "'":
                            value_chars.append("'")
                        i += 2
                        continue
                    else:
                        # If not a valid escape, treat backslash as a literal.
                        value_chars.append(ch)
                        i += 1
                        continue
                elif ch == "'":
                    i += 1  # Skip the closing quote
                    break
                else:
                    value_chars.append(ch)
                    i += 1
            else:
                raise ValueError(f"Unterminated string for key '{key}'.")
            
            value = ''.join(value_chars)
            kwargs[key] = value
        return kwargs

    def find_actions(self, action_string):
        """
        Walk through the string to find function calls that match the expected names and
        return a list of tuples (func_name, params_string). Handles nested parentheses in a simple way,
        taking into account quoted strings.
        """
        actions_list = []
        # List of valid function names
        valid_funcs = ["click", "left_double", "right_single", "drag", "hotkey", "type", "scroll", "wait", "finished", "call_user"]
        # Build a regex that matches any of these names followed immediately by an open paren.
        pattern = re.compile(r'\b(' + '|'.join(valid_funcs) + r')\s*\(', re.IGNORECASE)
        
        pos = 0
        while pos < len(action_string):
            match = pattern.search(action_string, pos)
            if not match:
                break
            func_name = match.group(1)
            # find the starting index of parameters (after the '(')
            start_index = match.end()  # points right after '('
            
            # now parse until the matching closing parenthesis, considering nested things and quotes.
            paren_count = 1
            i = start_index
            in_quote = False
            quote_char = ''
            while i < len(action_string) and paren_count > 0:
                char = action_string[i]
                if in_quote:
                    if char == quote_char:
                        in_quote = False
                    elif char == '\\' and i+1 < len(action_string):
                        # Skip the escape sequence.
                        i += 1
                    # else remain in quote
                else:
                    if char in ("'", '"'):
                        in_quote = True
                        quote_char = char
                    elif char == '(':
                        paren_count += 1
                    elif char == ')':
                        paren_count -= 1
                        if paren_count == 0:
                            break
                i += 1
            
            if paren_count != 0:
                print(f"Error parsing: Unable to find matching closing parenthesis for function '{func_name}' starting at index {match.start()}")
                pos = match.end()
                continue

            params_str = action_string[start_index:i]
            actions_list.append((func_name, params_str))
            pos = i + 1  # continue after the closing ')'
        return actions_list

    def parse_agent_output(self, action_string: str):
        """
        Parse a string containing possible action calls into a list of dictionaries
        with keys 'func' and 'kwargs' representing executable actions.
        """
        parsed_actions = []
        # first, find all action call substrings
        action_calls = self.find_actions(action_string)
        for func_name, params_str in action_calls:
            try:
                # If parameters are provided, try parsing them
                kwargs = {}
                # Only try to parse if params_str is not empty (strip whitespace)
                if params_str.strip():
                    kwargs = self.parse_kwargs(params_str)
            except Exception as e:
                print(f"Error parsing parameters for '{func_name}({params_str})': {e}")
                continue
            
            # Now, process each action based on its function name.
            func_name_lower = func_name.lower()
            
            if func_name_lower == "click":
                try:
                    coord = self.parse_coordinate(kwargs['start_box'])
                    parsed_actions.append({'func': 'move_to_pixel', 'kwargs': {'x': coord[0], 'y': coord[1]}})
                except Exception as e:
                    pass
                # Map to left_click. Ignoring any provided parameters.
                parsed_actions.append({'func': 'left_click', 'kwargs': {}})
            elif func_name_lower == "left_double":
                try:
                    coord = self.parse_coordinate(kwargs['start_box'])
                    parsed_actions.append({'func': 'move_to_pixel', 'kwargs': {'x': coord[0], 'y': coord[1]}})
                except Exception as e:
                    pass
                parsed_actions.append({'func': 'double_click', 'kwargs': {}})
            elif func_name_lower == "right_single":
                try:
                    coord = self.parse_coordinate(kwargs['start_box'])
                    parsed_actions.append({'func': 'move_to_pixel', 'kwargs': {'x': coord[0], 'y': coord[1]}})
                except Exception as e:
                    pass
                parsed_actions.append({'func': 'right_click', 'kwargs': {}})
            elif func_name_lower == "drag":
                # Expecting two parameters: start_box and end_box.
                if 'start_box' not in kwargs or 'end_box' not in kwargs:
                    print(f"Error parsing '{func_name}({params_str})': Missing 'start_box' or 'end_box'.")
                    continue
                try:
                    start_coord = self.parse_coordinate(kwargs['start_box'])
                    end_coord = self.parse_coordinate(kwargs['end_box'])
                except Exception as e:
                    print(f"Error parsing coordinates in '{func_name}({params_str})': {e}")
                    continue
                # Create two actions: move_to_pixel to the start coord, then drag_to to the end coord.
                parsed_actions.append({'func': 'move_to_pixel', 'kwargs': {'x': start_coord[0], 'y': start_coord[1]}})
                parsed_actions.append({'func': 'drag_to', 'kwargs': {'x': end_coord[0], 'y': end_coord[1]}})
            elif func_name_lower == "hotkey":
                if 'key' not in kwargs:
                    print(f"Error parsing '{func_name}({params_str})': Missing 'key'.")
                    continue
                # Convert space separated keys into dash separated keys.
                converted_key = self.convert_hotkey(kwargs['key'])
                parsed_actions.append({'func': 'hotkey', 'kwargs': {'key': converted_key}})
            elif func_name_lower == "type":
                if 'content' not in kwargs:
                    print(f"Error parsing '{func_name}({params_str})': Missing 'content'.")
                    continue
                parsed_actions.append({'func': 'type_text', 'kwargs': {'text': kwargs['content']}})
            elif func_name_lower == "scroll":
                if 'direction' not in kwargs:
                    print(f"Error parsing '{func_name}({params_str})': Missing 'direction'.")
                    continue
                direction = kwargs['direction'].strip().lower()
                if direction not in ['down', 'up', 'left', 'right']:
                    print(f"Error parsing '{func_name}({params_str})': Invalid direction '{direction}'.")
                    continue
                # For scroll, we choose the appropriate function name.
                scroll_func = f"scroll_{direction}"
                # Optionally, if a start_box is provided, we can parse it; however, the scroll functions
                # defined above do not require a coordinate parameter. We include it if needed.
                if 'start_box' in kwargs:
                    try:
                        coord = self.parse_coordinate(kwargs['start_box'])
                    except Exception as e:
                        print(f"Error parsing scroll start_box in '{func_name}({params_str})': {e}")
                        continue
                parsed_actions.append({'func': 'move_to_pixel', 'kwargs': {'x': coord[0], 'y': coord[1]}})
                parsed_actions.append({'func': scroll_func, 'kwargs': {}})
            elif func_name_lower in ["wait", "finished", "call_user"]:
                parsed_actions.append({'func': func_name_lower, 'kwargs': {}})
            else:
                print(f"Error: Unrecognized function '{func_name}' in '{func_name}({params_str})'")
        return parsed_actions

    def execute_actions(self, actions: list):
        """
        Execute a list of parsed actions.

        For each action, the corresponding VNCClient_SSH method is called.
        If a 'fail' or 'done' command is encountered, execution stops and the function returns immediately.
        """
        status = 'unfinished'
        for action in actions:
            act, kwargs = action['func'], action['kwargs']
            try:
                if act == 'left_click':
                    self.remote_client.left_click()
                elif act == 'double_click':
                    self.remote_client.double_click()
                elif act == 'right_click':
                    self.remote_client.right_click()
                elif act == 'move_to_pixel':
                    self.remote_client.move_to_pixel(**kwargs)
                elif act == 'drag_to':
                    self.remote_client.drag_to(**kwargs)
                elif act == 'type_text':
                    self.remote_client.type_text(**kwargs)
                elif act == 'hotkey':
                    self.remote_client.key_press(**kwargs)
                elif act == 'scroll_up':
                    self.remote_client.scroll_up(0.5)
                elif act == 'scroll_down':
                    self.remote_client.scroll_down(0.5)
                elif act == 'scroll_left':
                    self.remote_client.scroll_left(0.5)
                elif act == 'scroll_right':
                    self.remote_client.scroll_right(0.5)
                elif act == 'wait':
                    time.sleep(5)
                elif act in ['finished', 'call_user']:
                    status = act
                time.sleep(self.remote_client.action_interval_seconds)
            except Exception as e:
                print(f'Error executing action {action}: {e}')
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

        # Save current_screenshot
        current_screenshot.save(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}.png'))

        # Save raw_response
        with open(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}_raw_response.txt'), 'w') as f:
            f.write(raw_response)

        # Dump parsed_actions
        with open(os.path.join(save_dir, 'context', f'step_{str(current_step).zfill(3)}_parsed_actions.json'), 'w') as f:
            json.dump(parsed_actions, f, indent=4)

        # print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = f'Status: {status}')

        return status

    def save_conversation_history(self, save_dir: str):
        # Remove all images before saving chat log
        self.filter_to_n_most_recent_images(0)

        file = os.path.join(save_dir, 'context', 'chat_log.json')
        with open(file, "w") as json_file:
            json.dump(self.messages, json_file)

        self.token_usage.append({
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens
        })
        file = os.path.join(save_dir, 'context', 'token_usage.json')
        with open(file, "w") as json_file:
            json.dump(self.token_usage, json_file)