# `VNCClient_SSH` Documentation

## Overview

The `VNCClient_SSH` class provides a Python interface for connecting to and controlling remote systems via VNC over SSH tunnels. It supports both standard VNC connections and VMware-specific screenshot capture methods.

## Class Definition

```python
VNCClient_SSH(guest_username, guest_password, ssh_host, ssh_pkey, 
              retry_attempts=3, retry_delay=5, action_interval_seconds=1, 
              vmx_path=None, vnc_connection_timeout=600)
```

### Parameters

- **guest_username** (str): Username for SSH and VNC authentication
- **guest_password** (str): Password for SSH and VNC authentication  
- **ssh_host** (str): SSH server hostname or IP address
- **ssh_pkey** (str): Path to SSH private key file
- **retry_attempts** (int, optional): Number of connection retry attempts (default: 3)
- **retry_delay** (int, optional): Delay between retry attempts in seconds (default: 5)
- **action_interval_seconds** (int, optional): Interval between actions in seconds (default: 1)
- **vmx_path** (str, optional): Path to VMware .vmx file for VMware-specific operations (default: None)
- **vnc_connection_timeout** (int, optional): VNC connection timeout in seconds (default: 600)

## Methods

### Connection Management

#### `connect()`
Establishes SSH tunnel and VNC connection with automatic retry logic.

**Raises:**
- `ConnectionError`: If connection fails after all retry attempts

#### `disconnect()`
Closes VNC connection and SSH tunnel.

#### `check_ssh_connectivity()`
Tests SSH connectivity without establishing a persistent connection.

**Returns:**
- `bool`: True if SSH connection successful, False otherwise

#### `run_ssh_command(command: str) -> tuple`
Executes a command on the remote system via SSH.

**Parameters:**
- **command** (str): Command to execute

**Returns:**
- `tuple`: (success: bool, output/error: str)

### Screen Capture

#### `capture_screenshot()`
Captures a screenshot of the remote desktop.

**Returns:**
- `PIL.Image`: Screenshot as PIL Image object

**Notes:**
- Uses VNC capture by default
- Uses VMware tools capture if `vmx_path` is provided (faster for VMware VMs)

### Mouse Operations

#### `move_to(x, y)`
Moves mouse cursor to normalized coordinates.

**Parameters:**
- **x** (float): X coordinate (0.0 to 1.0)
- **y** (float): Y coordinate (0.0 to 1.0)

#### `move_to_pixel(x, y)`
Moves mouse cursor to exact pixel coordinates.

**Parameters:**
- **x** (int): X pixel coordinate
- **y** (int): Y pixel coordinate

#### `left_click()`
Performs a single left mouse click.

#### `right_click()`
Performs a single right mouse click.

#### `middle_click()`
Performs a single middle mouse click.

#### `double_click()`
Performs a double left mouse click.

#### `triple_click()`
Performs a triple left mouse click.

#### `mouse_down(button)`
Presses and holds a mouse button.

**Parameters:**
- **button** (str): Button name ("left", "middle", "right")

#### `mouse_up(button)`
Releases a mouse button.

**Parameters:**
- **button** (str): Button name ("left", "middle", "right")

#### `drag_to(x, y)`
Performs drag operation from current position to target coordinates.

**Parameters:**
- **x** (float): Target X coordinate (0.0 to 1.0)
- **y** (float): Target Y coordinate (0.0 to 1.0)

### Scrolling Operations

#### `scroll_down(amount, by_pixel=False)`
Scrolls down by specified amount.

**Parameters:**
- **amount** (float/int): Scroll amount (0.0-1.0 if proportional, pixel count if by_pixel=True)
- **by_pixel** (bool): If True, amount is in pixels; if False, amount is proportional

#### `scroll_up(amount, by_pixel=False)`
Scrolls up by specified amount.

**Parameters:**
- **amount** (float/int): Scroll amount (0.0-1.0 if proportional, pixel count if by_pixel=True)
- **by_pixel** (bool): If True, amount is in pixels; if False, amount is proportional

#### `scroll_left(amount, by_pixel=False)`
Scrolls left by specified amount.

**Parameters:**
- **amount** (float/int): Scroll amount (0.0-1.0 if proportional, pixel count if by_pixel=True)
- **by_pixel** (bool): If True, amount is in pixels; if False, amount is proportional

#### `scroll_right(amount, by_pixel=False)`
Scrolls right by specified amount.

**Parameters:**
- **amount** (float/int): Scroll amount (0.0-1.0 if proportional, pixel count if by_pixel=True)
- **by_pixel** (bool): If True, amount is in pixels; if False, amount is proportional

### Keyboard Operations

#### `key_press(key)`
Presses and releases a key.

**Parameters:**
- **key** (str): Key to press (see supported keys below)

#### `key_press_and_hold(key, duration_seconds: int)`
Presses a key and holds it for specified duration.

**Parameters:**
- **key** (str): Key to press
- **duration_seconds** (int): Duration to hold key in seconds

#### `type_text(text)`
Types a string of ASCII characters.

**Parameters:**
- **text** (str): Text to type (ASCII characters only)

**Notes:**
- Includes 0.1 second delay between characters
- Non-ASCII characters are filtered out

### Supported Keys

The following keys are supported for keyboard operations:

- **Single ASCII characters**: a-z, A-Z, 0-9, symbols
- **Special keys**: ctrl, command, option, backspace, tab, enter, esc, del
- **Arrow keys**: left, up, right, down
- **Key combinations**: Use hyphen to combine (e.g., "ctrl-c", "command-v")

**Key Mapping Notes:**
- `option` maps to `meta`
- `command` and `cmd` map to `alt`
- `backspace` maps to `bsp`

## Usage Example

```python
# Initialize client
client = VNCClient_SSH(
    guest_username="ec2-user",
    guest_password="000000",
    ssh_host="13.250.104.211",
    ssh_pkey="./credential.pem",
    retry_attempts=5
)

try:
    # Connect to remote system
    client.connect()
    
    # Capture screenshot
    screenshot = client.capture_screenshot()
    screenshot.save("screenshot.png")
    
    # Perform mouse operations
    client.move_to(0.5, 0.5)  # Move to center
    client.left_click()
    
    # Type text
    client.type_text("Hello World!")
    
    # Press keys
    client.key_press("enter")
    client.key_press("ctrl-c")
    
    # Scroll operations
    client.scroll_down(0.1)  # Scroll down 10% of screen
    
finally:
    # Always disconnect
    client.disconnect()
```

## Dependencies

- `sshtunnel` (SSHTunnelForwarder)
- `PIL` (Image processing)
- `subprocess` (Command execution)
- Custom modules: `VMwareTools`, `print_message`, `api`, `KEYMAP`

## Error Handling

- Connection failures trigger automatic retry with exponential backoff
- SSH connectivity is validated before attempting VNC connection
- Screenshot capture includes fallback mechanisms for VMware environments
- Input validation filters non-ASCII characters from text input

## Notes

- Uses SSH tunnel on port 5900 (standard VNC port)
- Supports both standard VNC and VMware-optimized screenshot capture
- Coordinate system uses normalized values (0.0-1.0) for screen-independent positioning
- Automatic connection management ensures operations work even if connection is lost