import os
import json
import shutil
import argparse

from utils.log import print_message
from utils.languages import parse_language_list
from utils.run_task import run_task
from utils.timeout import TimeoutException
from constants import env_init_command, eval_init_command, language_lookup_table


# Parse args
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

arguments = parser.parse_args()


if arguments.instance_id is None and arguments.vmx_path is None:
    raise ValueError(f'Either `instance_id` or `vmx_path` must be provided')








# Prepare tasks
tasks = []
for path in arguments.paths_to_eval_tasks:
    category_name = os.path.basename(os.path.normpath(path))
    tasks += [(category_name, os.path.join(path, file)) for file in os.listdir(path) if file.lower().endswith('json')]

language_combinations = parse_language_list(arguments.languages)




incomplete_task_list = []

for task_language, env_language in language_combinations:
    if task_language in language_lookup_table:
        task_language = language_lookup_table[task_language]
    if env_language in language_lookup_table:
        env_language = language_lookup_table[env_language]
    

    for task_index, (task_category, json_path) in enumerate(tasks):

        # Load task json file
        with open(json_path, 'r') as f:
            task_dict = json.load(f)
        task_uuid = task_dict['id']
        task_id = f'({task_index + 1}/{len(tasks)})'

        # Check if there is strict env requirement
        # if arguments.instance_id is None and arguments.vmx_path is not None:
        #     if 'force_ec2' in task_dict:
        #         if task_dict['force_ec2']:
        #             print_message(f"Task should be evaluated in AWS EC2. Skipping task {task_uuid}.", title = f'Task {task_id}')

        # Check if the task/env is provided in the language requested
        if task_language not in task_dict["task"]:
            print_message(f"Task not provided in language {task_language}. Skipping task {task_uuid}.", title = f'Task {task_id}, task language {task_language}, env language {env_language}')
            continue
        elif env_language not in task_dict["snapshot"]:
            print_message(f"Environment not provided in language {env_language}. Skipping task {task_uuid}.", title = f'Task {task_id}, task language {task_language}, env language {env_language}')
            continue

        # Retrieve snapshot name
        snapshot_name = task_dict["snapshot"][env_language]

        # Check if base_save_dir is a path, and if not, create it
        if not os.path.exists(arguments.base_save_dir):
            os.makedirs(arguments.base_save_dir)
        save_dir = os.path.join(arguments.base_save_dir, task_category, f"{task_dict['id']}_{task_language}_{env_language}")

        # Check if save_dir exists, and if so, skip or raise an error
        if os.path.exists(save_dir):
            ## Previous evaluation record exists
            if os.path.exists(os.path.join(save_dir, 'eval_result.txt')):
                ### Task is already evaluated
                print_message(f"'eval_result.txt' found in {save_dir}. Skipping task.", title = f'Task {task_id}, task language {task_language}, env language {env_language}')
                continue
            elif os.path.exists(os.path.join(save_dir, 'fail.flag')):
                ### Previous evals failed
                shutil.rmtree(save_dir)
                os.makedirs(os.path.join(save_dir, 'context'))
            else:
                ### Unexpected situation
                raise OSError(f"Directory {save_dir} already exists. Consider cleaning up the save path using scripts/cleanup_result_directory.ipynb")
        else:
            ## No previous evaluation record, create the save dir
            os.makedirs(os.path.join(save_dir, 'context'))


        task_complete_flag = False
        for task_attempt in range(1, arguments.task_max_attempts + 1):
            if arguments.task_max_attempts > 1:
                print_message(f'{task_uuid}, Task language {task_language}, Env language {env_language}, Attempt {task_attempt}', title = f'Task {task_id}')
            try:
                run_task(
                    task_id = task_id,
                    task_dict = task_dict,
                    task_language = task_language,
                    env_language = env_language,
                    save_dir = save_dir,

                    snapshot_name = snapshot_name,
                    instance_id = arguments.instance_id,
                    snapshot_recovery_timeout_seconds = arguments.snapshot_recovery_timeout_seconds,
                    override_env_reset = arguments.override_env_reset,
                    vmx_path = arguments.vmx_path,

                    guest_username = arguments.guest_username,
                    guest_password = arguments.guest_password,
                    ssh_host = arguments.ssh_host,
                    ssh_pkey = arguments.ssh_pkey,

                    gui_agent_name = arguments.gui_agent_name,
                    max_steps = arguments.max_steps,
                    task_step_timeout = arguments.task_step_timeout,
                    pre_command_max_trials = arguments.pre_command_max_trials,
                    env_init_command = env_init_command,
                    eval_init_command = eval_init_command
                )
                task_complete_flag = True
                break
            except TimeoutException as e:
                print_message(e, title = f'Task {task_id} Error')
            except Exception as e:
                print_message(e, title = f'Task {task_id} Error')

        if not task_complete_flag:
            print_message(f'Task failed after max attempts: {task_uuid}', title = f'Task {task_id} Error')
            incomplete_task_list.append((task_uuid, f'{task_uuid} {task_id}, env language {env_language}, task language {task_language}'))

            # Make a fail flag under the directory
            fail_flag_path = os.path.join(save_dir, 'fail.flag')
            with open(fail_flag_path, 'w'):
                pass