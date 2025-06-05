from utils.VNCClient import VNCClient_SSH

class CustomGUIAgent:
    def __init__(self, remote_client: VNCClient_SSH, **kwargs):
        ...

    def step(
        self,
        task_id: str,           # ID/UUID of the current task
        current_step: int,      # 1, 2, 3, ...
        max_steps: int,         # e.g. 15
        env_language: str,      # en/zh/ar/ja/ru
        task_language: str,     # en/zh/ar/ja/ru
        task: str,              # e.g. "Set volume to 25%."
        task_step_timeout: int, # e.g. 120
        save_dir: str,          # Where you can save anything related to this task
    ) -> str:
        
        """
        Example workflow:
        1. Capture screenshot
        2. Send task and screenshot to the GUI agent
        3. Parse agent response string into actions
        4. Call `remote_client` to execute those actions in the environment, for example:
            ```
            self.remote_client.key_press('command-c')
            ```
            Please refer to `instructions/VNCCLient_SSH_documentation.md` or existing agent implementations.
        5. Return if the status is "unfinished" or something else
        """

        status = "unfinished"
        # Not completed: `status` MUST BE `unfinished`
        # No further steps: `status` could be `DONE`, `done`, `completed`, or whatever string
        return status
