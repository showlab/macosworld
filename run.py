import argparse
import sys
import subprocess
import socket

from utils.log import print_message
from utils.completion_checker import all_tasks_completed

parser = argparse.ArgumentParser()

parser.add_argument('--guest_username', type=str, default='ec2-user')
parser.add_argument('--guest_password', type=str, default='000000')
parser.add_argument('--ssh_host', type=str, default=None)
parser.add_argument('--ssh_pkey', type=str, default='credential.pem')
parser.add_argument('--instance_id', type=str)
parser.add_argument('--vmx_path', type=str, default=None)

parser.add_argument('--snapshot_recovery_timeout_seconds', type=int, default=120)
parser.add_argument('--override_env_reset', action='store_true')

parser.add_argument('--pre_command_max_trials', type=int, default=3)
parser.add_argument('--task_max_attempts', type=int, default=2)
parser.add_argument('--task_step_timeout', type=int, default=120)

parser.add_argument('--gui_agent_name', type=str, required=True)
parser.add_argument('--max-steps', type=int, default=15)
parser.add_argument('--base_save_dir', type=str, default='./results')
parser.add_argument('--paths_to_eval_tasks', nargs='+', required=True)
parser.add_argument('--languages', nargs='+', required=True)

args = parser.parse_args()


# The testbench restarts every 12 hours.
# Interrupted tasks are automatically cleaned up and re-benchmarked.
# This is intended to prevent subprocess stucks within the testbench.
# If you remove the timeout, it is recommended that you monitor the testbench every few hours to ensure that the program has not stalled.
TESTBENCH_TIMEOUT_SECONDS = 12 * 3600


# Loop until the benchmark is completed
while True:

    # Step 1 - Run `clean_up.py` to cleanup the base_save_dir
    print_message(f'Running cleanup on {args.base_save_dir}', title = 'run.py')
    subprocess.run([sys.executable, "cleanup.py", "--base_save_dir", args.base_save_dir])



    # Step 2 - Check if all benchmark tasks have been completed by scanning base_save_dir
    finished = all_tasks_completed(args.base_save_dir, args.paths_to_eval_tasks, args.languages)
    # print("all_tasks_completed ->", finished)
    if finished:
        print('\n' * 5)
        print_message(f'All tasks completed. You can now shut down the AWS instance or virtual machine', title = 'run.py')
        break



    # Step 3 - Run `testbench.py`
    cmd = [sys.executable, "testbench.py"]

    # pass simple scalar arguments when present
    if args.vmx_path:
        cmd += ["--vmx_path", args.vmx_path]
    if args.ssh_host:
        cmd += ["--ssh_host", args.ssh_host]
    if args.ssh_pkey:
        cmd += ["--ssh_pkey", args.ssh_pkey]
    if args.instance_id:
        cmd += ["--instance_id", args.instance_id]

    cmd += ["--snapshot_recovery_timeout_seconds", str(args.snapshot_recovery_timeout_seconds)]
    if args.override_env_reset:
        cmd += ["--override_env_reset"]

    cmd += ["--pre_command_max_trials", str(args.pre_command_max_trials)]
    cmd += ["--task_max_attempts", str(args.task_max_attempts)]
    cmd += ["--task_step_timeout", str(args.task_step_timeout)]

    cmd += ["--guest_username", args.guest_username]
    cmd += ["--guest_password", args.guest_password]

    cmd += ["--gui_agent_name", args.gui_agent_name]
    cmd += ["--max-steps", str(args.max_steps)]
    cmd += ["--base_save_dir", args.base_save_dir]

    # multi-value args: pass them as a single flag followed by their items
    cmd += ["--paths_to_eval_tasks"] + list(args.paths_to_eval_tasks)
    cmd += ["--languages"] + list(args.languages)

    # subprocess.run(cmd)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    host, port = srv.getsockname()
    print_message(f'Running testbench: {" ".join(cmd)}', title = 'run.py')
    print_message(f'Communicating with testbench on {host}:{port}', title = 'run.py')
    cmd += ["--port", str(port)]
    p = subprocess.Popen(cmd)
    srv.settimeout(TESTBENCH_TIMEOUT_SECONDS)
    try:
        conn, _ = srv.accept()
        msg = conn.recv(1024)
        conn.close()
    except socket.timeout:
        p.kill()  # or p.terminate()
        print_message(f'Testbench terminated after timeout {TESTBENCH_TIMEOUT_SECONDS}s. Interrupted task will be cleaned up and re-benchmarked.', title = 'run.py')
    finally:
        srv.close()

