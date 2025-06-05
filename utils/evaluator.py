import subprocess
import sys

class Evaluator:
    def __init__(self, ssh_host: str, ssh_username: str, ssh_pkey: str):
        self.ssh_host = ssh_host
        self.ssh_username = ssh_username
        self.ssh_pkey = ssh_pkey

    def run_command(self, command: str) -> str:
        command = command.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$')
        ssh_command = f'ssh -o StrictHostKeyChecking=no -i "{self.ssh_pkey}" {self.ssh_username}@{self.ssh_host} "{command}"'
        try:
            output = subprocess.check_output(ssh_command, shell=True, stderr=subprocess.STDOUT).decode().strip()
            return True, output
        except Exception as e: # subprocess.CalledProcessError
            return False, e

    def __call__(self, eval_configs: list, binary_grading: bool = True) -> int:
        filtered_eval_configs = [item for item in eval_configs if item[1] == 100] if binary_grading else eval_configs
        for eval_config in filtered_eval_configs:
            command, return_value = eval_config
            success, output = self.run_command(command)
            if success and isinstance(output, str):
                if "true" in output.lower():
                    return return_value
                else: # false --> continue to the next valid grading point
                    continue
            else:
                return [command, return_value, output]
        return 0
