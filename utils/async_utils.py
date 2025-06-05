import os
import subprocess
import signal

class AsyncSSHCommandHandler:
    def __init__(self, ssh_host: str, ssh_username: str, ssh_pkey: str, current_timestep: int = 0):
        self.ssh_host = ssh_host
        self.ssh_username = ssh_username
        self.ssh_pkey = ssh_pkey
        self.current_timestep = current_timestep
        self.process = None  # Holds the subprocess.Popen process

    def run_command(self, command: str) -> subprocess.Popen:
        # Format the command with the ssh options and execute it asynchronously.
        command = command.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$')
        ssh_command = f'ssh -tt -i "{self.ssh_pkey}" {self.ssh_username}@{self.ssh_host} "{command}"'
        self.process = subprocess.Popen(
            ssh_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid
        )
        return self.process

    def end_command(self):
        """
        Return args:
        1. Process return code
        2. Process stdout
        3. Process stderr
        4. Whether the process was killed/ended itself
        """
        if self.process:
            if self.process.poll() is None:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                # print("In-process event is killed.")
                end_type = 'killed'
            else:
                # print("In-process event has been handled.")
                end_type = 'handled'
            stdout, stderr = self.process.communicate()
            return self.process.returncode, stdout, stderr, end_type
        else:
            print("No process is currently running.")
            return None, "", "No process is currently running.", None
