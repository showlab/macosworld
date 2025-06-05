import subprocess
import time
import os
from utils.log import print_message

class VMwareTools:

    def __init__(self, guest_username: str, guest_password: str, ssh_host: str, ssh_pkey: str, vmx_path: str):
        self.guest_username = guest_username
        self.guest_password = guest_password
        self.ssh_host = ssh_host
        self.ssh_pkey = ssh_pkey
        self.vmx_path = vmx_path

    def ping_vmware_tools(self) -> tuple:
        no_op_command = f'vmrun -T ws -gu {self.guest_username} -gp {self.guest_password} runScriptInGuest "{self.vmx_path}" /bin/zsh :'
        no_op_result = subprocess.run(no_op_command, shell=True, text=True, capture_output=True, encoding="utf-8", env=os.environ.copy())

        return (
            no_op_result.returncode == 0,   # Successful or not
            no_op_result                    # Raw return
        )

    def run_ssh_command(self, command: str) -> tuple:
        command = command.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$')
        ssh_command = f'ssh -o StrictHostKeyChecking=no -i "{self.ssh_pkey}" {self.guest_username}@{self.ssh_host} "{command}"'
        try:
            output = subprocess.check_output(ssh_command, shell=True, stderr=subprocess.STDOUT).decode().strip()
            return True, output
        except Exception as e: # subprocess.CalledProcessError
            return False, e

    def reload_vmware_tools(self, max_attempts: int = 5) -> bool:
        unload_vmware_tools_command = f'echo "{self.guest_password}" | sudo -S launchctl unload /Library/LaunchDaemons/com.vmware.launchd.tools.plist'
        load_vmware_tools_command = f'echo "{self.guest_password}" | sudo -S launchctl load /Library/LaunchDaemons/com.vmware.launchd.tools.plist'

        for attempt in range(max_attempts):
            self.run_ssh_command(unload_vmware_tools_command)
            self.run_ssh_command(load_vmware_tools_command)
            success_flag, raw_result = self.ping_vmware_tools()
            if success_flag:
                return True
        return False

    def revert_to_snapshot(self, vmware_snapshot_name: str, get_ip_address_timeout_seconds: int = 120):
        def shutdown():
            shutdown_command = f'vmrun -T ws stop "{self.vmx_path}" hard'
            shutdown_result = subprocess.run(shutdown_command, shell=True, text=True, capture_output=True, encoding="utf-8", env=os.environ.copy())

        def cleanup():
            cleanup_command = f'rm -rf "{self.vmx_path}f"; rm -rf "{self.vmx_path}.lck"'
            cleanup_result = subprocess.run(cleanup_command, shell=True, text=True, capture_output=True, encoding="utf-8", env=os.environ.copy())


        # Revert to snapshot
        print_message(f'Reverting guest machine "{self.vmx_path}" to snapshot "{vmware_snapshot_name}"')
        env_restore_command = f'vmrun -T ws revertToSnapshot "{self.vmx_path}" {vmware_snapshot_name}'
        env_restore_result = subprocess.run(env_restore_command, shell=True, text=True, capture_output=True, encoding="utf-8", env=os.environ.copy())

        if env_restore_result.returncode != 0:
            print_message(f'Error reverting to snapshot\nSTDOUT: {env_restore_result.stdout}\nSTDERR:{env_restore_result.stderr}', title = 'Error')
            if 'The file is already in use' in env_restore_result.stdout:
                shutdown()
                cleanup()
                return False, None
            else:
                raise RuntimeError(f'Error recovering snapshot {vmware_snapshot_name}')
        

        # Start guest machine
        print_message(f'Starting guest machine "{self.vmx_path}"', title = 'VMware')
        env_start_command = f'vmrun -T ws start "{self.vmx_path}" nogui'
        env_start_result = subprocess.run(env_start_command, shell=True, text=True, capture_output=True, encoding="utf-8", env=os.environ.copy())

        if env_start_result.returncode != 0:
            print_message(f'Error starting guest machine\nSTDOUT: {env_start_result.stdout}\nSTDERR:{env_start_result.stderr}', title = 'Error')
            if 'The file is already in use' in env_start_result.stdout:
                shutdown()
                cleanup()
                return False, None
            else:
                raise RuntimeError(f'Error recovering snapshot {vmware_snapshot_name}')
            
        # Activate VMware Tools
        print_message(f'Activating VMware Tools', title = 'VMware')
        no_op_command = f'vmrun -T ws -gu {self.guest_username} -gp {self.guest_password} runScriptInGuest "{self.vmx_path}" /bin/zsh :'
        no_op_result = subprocess.run(no_op_command, shell=True, text=True, capture_output=True, encoding="utf-8", env=os.environ.copy())
        
        if no_op_result.returncode != 0:
            print_message(f'Error activating VMware Tools\nSTDOUT: {no_op_result.stdout}\nSTDERR:{no_op_result.stderr}', title='Error')
            return False, None

        # Get IP address
        print_message(f'Retrieving IP address of guest machine "{self.vmx_path}"', title = 'VMware')
        get_ip_command = f'vmrun -T ws getGuestIPAddress "{self.vmx_path}"'
        start_time = time.time()
        while True:
            get_ip_result = subprocess.run(get_ip_command, shell=True, text=True, capture_output=True, encoding="utf-8", env=os.environ.copy())
            
            if get_ip_result.returncode == 0:
                guest_ip = get_ip_result.stdout.strip()
                print_message(f'IP address of guest machine: {guest_ip}', title = 'VMware')
                if guest_ip is not None:
                    return True, guest_ip
            if time.time() - start_time > get_ip_address_timeout_seconds:
                print_message(f'Timeout obtaining guest machine IP address; last error:\nSTDOUT: {get_ip_result.stdout}\nSTDERR:{get_ip_result.stderr}', title = 'Error')
                return False, None

            subprocess.run(no_op_command, shell=True, text=True, capture_output=True, encoding="utf-8", env=os.environ.copy())
