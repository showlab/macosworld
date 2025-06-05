import os
import boto3
import time

from utils.VNCClient import VNCClient_SSH
from utils.evaluator import Evaluator
from utils.async_utils import AsyncSSHCommandHandler

from utils.log import print_message
from utils.vmware_utils import VMwareTools

from agent.get_gui_agent import get_gui_agent

from constants import ami_lookup_table


def inprocess_result_matching(inprocess_stdout: str, inprocess_gold_elements: list, inprocess_distracting_elements: list):
    # Match handled properly
    for element in inprocess_gold_elements:
        if element.lower() in inprocess_stdout.lower():
            inprocess_eval_result = 'gold'
            break
    # Match distracted
    for element in inprocess_distracting_elements:
        if element.lower() in inprocess_stdout.lower():
            inprocess_eval_result = 'distracted'
            break
    # No match
    if inprocess_eval_result is None:
        inprocess_eval_result = 'error_no_match'
    return inprocess_eval_result

def run_task(
    # Task-related params
    task_id: str,
    task_dict: dict,
    task_language: str,
    env_language: str,
    save_dir: str,

    # Env-related params
    snapshot_name: str,
    instance_id: str,
    snapshot_recovery_timeout_seconds: int,
    override_env_reset: bool,
    vmx_path: str,

    # Remote connection
    guest_username: str, 
    guest_password: str,
    ssh_host: str,
    ssh_pkey: str,

    # GUI agent
    gui_agent_name: str,

    # Runtime
    max_steps: int,
    task_step_timeout: int,
    pre_command_max_trials: int,
    env_init_command: str,
    eval_init_command: str,
):
    task_uuid = task_dict["id"]
    task_id = task_id

    # Check if env_language is in task_dict['snapshot']
    assert env_language in task_dict['snapshot'], f"Task {task_dict['id']} does not support snapshot language {env_language}"

    # Check if task_language is in task_dict['task']
    assert task_language in task_dict['task'], f"Task {task_dict['id']} does not include task language {task_language}"


    


    # Env reset
    cumulative_waiting_time = 0
    if override_env_reset:
        print('Please manually reset the environment. Press `c` to continue.')
        breakpoint()
    elif vmx_path is not None:
        # VMware env
        snapshot_revert_max_trials = 5
        vmware_tools = VMwareTools(
            guest_username = guest_username,
            guest_password = guest_password,
            ssh_host = None,
            ssh_pkey = ssh_pkey,
            vmx_path = vmx_path
        )
        for trial in range(1, snapshot_revert_max_trials + 1):
            if trial > 1:
                print_message(f'Retrying starting guest machine... ({trial}/{snapshot_revert_max_trials})')
            revert_success_flag, ssh_host = vmware_tools.revert_to_snapshot(snapshot_name)
            if revert_success_flag:
                break
        
        print_message(f'Guest machine started successfully at {ssh_host}', title = 'VMware')
        
    else:
        # AWS env
        snapshot_id = ami_lookup_table[snapshot_name]
        ec2_client = boto3.client('ec2')
        replace_root_volume_task_response = ec2_client.create_replace_root_volume_task(
            InstanceId=instance_id,       # Instance currently running
            # SnapshotId=snapshot_id,     # EBS snapshot
            ImageId=snapshot_id,
            DeleteReplacedRootVolume=True
        )
        print_message(f'Reinitiating instance "{instance_id}" from image "{snapshot_id}"', title = 'EC2')

        while True:
            describe_replace_root_volume_tasks_response = ec2_client.describe_replace_root_volume_tasks(
                ReplaceRootVolumeTaskIds=[replace_root_volume_task_response['ReplaceRootVolumeTask']['ReplaceRootVolumeTaskId']]
            )
            if describe_replace_root_volume_tasks_response['ReplaceRootVolumeTasks'][0]['TaskState'] == 'succeeded':
                print_message(f'Recovery complete. Duration {cumulative_waiting_time}s. ', title = 'EC2')
                break
            cumulative_waiting_time += 10
            if cumulative_waiting_time > snapshot_recovery_timeout_seconds:
                print_message(f'Timeout recovering instance "{instance_id}" from image "{snapshot_id}"', title = 'Error')
                raise TimeoutError
            time.sleep(10)


    # Establish remote connection

    remote_client = VNCClient_SSH(
        guest_username = guest_username, 
        guest_password = guest_password, 
        ssh_host = ssh_host,
        ssh_pkey = ssh_pkey,
        vmx_path = vmx_path
    )

    print_message(f'Checking ssh connectivity to {ssh_host}', title = 'VNC Client')
    while True:
        if remote_client.check_ssh_connectivity():
            break
        cumulative_waiting_time += 10
        if cumulative_waiting_time > snapshot_recovery_timeout_seconds:
            if vmx_path is None:
                # AWS
                raise TimeoutError(f'Timeout recovering instance "{instance_id}" from image "{snapshot_id}"')
            else:
                # VMware
                raise TimeoutError(f'Timeout establishing ssh connection to {ssh_host}')
        time.sleep(10)

    remote_client.connect()
    print_message(f'Connected to {ssh_host}', title = 'VNC Client')


    # Construct GUI Agent
    gui_agent = get_gui_agent(gui_agent_name, remote_client)

    # print('Manually reset the environment')
    # breakpoint()

    # Run prep command
    remote_client.run_ssh_command(env_init_command)
    if 'pre_command' in task_dict:
        pre_command = task_dict['pre_command']
        pre_command_complete_flag = False
        for trial in range(pre_command_max_trials):
            if isinstance(pre_command, str):
                # When the prep command is a string
                pre_command_complete_flag, pre_command_output = remote_client.run_ssh_command(pre_command)
            elif isinstance(pre_command, dict):
                # When the prep command is a dict of language-dependent string
                if env_language in pre_command:
                    pre_command_complete_flag, pre_command_output = remote_client.run_ssh_command(pre_command[env_language])
                else:
                    raise NotImplementedError(f'Task {task_id} has no preparation command for env language "{env_language}".')
            else:
                raise TypeError(f'Unknown prep command type ({type(pre_command)}) in task {task_id}.')
            if pre_command_complete_flag:
                # When the prep command finishes
                break
        if "force_error_free_prep" in task_dict:
            if task_dict["force_error_free_prep"] and not pre_command_complete_flag:
                # When the prep command repeatedly encounter errors until a max trial
                raise RuntimeError(f'Prep command not finished for task {task_id}.')
            
    inprocess_event_handler = None
    if 'in_process' in task_dict:
        inprocess_event_handler = AsyncSSHCommandHandler(ssh_host, guest_username, ssh_pkey)
        inprocess_command, inprocess_event_start_timestep, inprocess_gold_elements, inprocess_distracting_elements = task_dict['in_process']

    if 'before_action_delay_seconds' in task_dict:
        before_action_delay_seconds = task_dict['before_action_delay_seconds']
        print_message(f'Waiting for {before_action_delay_seconds}s before benchmarking', title = f'Task {task_id}/{env_language}/{task_language}')
        time.sleep(before_action_delay_seconds)


    # Start interactive loop

    task = task_dict['task'][task_language]

    for current_step in range(1, max_steps + 1):
        time.sleep(5)

        # Inject events
        if inprocess_event_handler is not None:
            if current_step == inprocess_event_start_timestep:
                inprocess_event_handler.run_command(inprocess_command)
                time.sleep(5)
                print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = 'Distraction event injected')

        # Call agent
        status = gui_agent.step(
            task_id = task_id,
            current_step = current_step,
            max_steps = max_steps,
            env_language = env_language,
            task_language = task_language,

            task = task,
            task_step_timeout = task_step_timeout,
            save_dir = save_dir
        )

        print_message(title = f'Task {task_id}/{env_language}/{task_language} Step {current_step}/{max_steps}', content = f'Status: {status}')
        
        if status != "unfinished":
            break

    gui_agent.save_conversation_history(save_dir)




    # In-process event grading
    if inprocess_event_handler is not None:
        # End event
        inprocess_return_code, inprocess_stdout, inprocess_stderr, inprocess_end_type = inprocess_event_handler.end_command()

        # Print result
        inprocess_log_message = f'Log as follows:\nReturn value {inprocess_return_code}\nSTDOUT: {inprocess_stdout}\nSTDERR: {inprocess_stderr}'


        # Evaluate distraction
        inprocess_eval_result = None
        if inprocess_end_type == 'killed':
            # Not handled
            inprocess_eval_result = 'not_handled'
        elif inprocess_return_code == 0 and isinstance(inprocess_stdout, str):
            # Result matching
            inprocess_eval_result = inprocess_result_matching(
                inprocess_stdout,
                inprocess_gold_elements,
                inprocess_distracting_elements
            ) 
        elif inprocess_return_code == 1 and isinstance(inprocess_stdout, str): # If the button name is "Cancel"
            if '-128' in inprocess_stdout: 
                # Result matching
                inprocess_eval_result = inprocess_result_matching(
                    inprocess_stdout,
                    inprocess_gold_elements,
                    inprocess_distracting_elements
                )
            else:
                # Other error
                inprocess_eval_result = 'error'
        else:
            # # User canceled error
            # if isinstance(inprocess_stdout, str):
            #     if 'User canceled. (-128)' in inprocess_stdout:
            #         raise RuntimeError(f'Inprocess event failed to initialise. STDOUT: {inprocess_stdout}')

            # Other error
            inprocess_eval_result = 'error'

        print_message(f'Event {inprocess_end_type} with status {inprocess_eval_result}. {inprocess_log_message}', title = 'Distraction Event')
                
        with open(os.path.join(save_dir, "distraction_result.txt"), "w") as file:
            file.write(f"{inprocess_eval_result}\n\n{inprocess_log_message}")



    # Task grading

    if "before_grading_delay_seconds" in task_dict:
        before_grading_delay_seconds = task_dict['before_grading_delay_seconds']
        if before_grading_delay_seconds > 0:
            print_message(f'Waiting for {before_grading_delay_seconds}s before grading', title = f'Task {task_id}/{env_language}/{task_language}')
            time.sleep(before_grading_delay_seconds)

    evaluator = Evaluator(ssh_host, guest_username, ssh_pkey)
    evaluator.run_command(eval_init_command)

    eval_result = evaluator(task_dict["grading_command"])
    print_message(title = 'Evaluation result', content = str(eval_result))

    if isinstance(eval_result, int):
        with open(os.path.join(save_dir, "eval_result.txt"), "w") as file:
            if eval_result < 0:
                file.write("eval_failed\n")
            file.write(str(eval_result))
    elif isinstance(eval_result, list):
        with open(os.path.join(save_dir, "eval_result.txt"), "w") as file:
            file.write("eval_failed\n")
            for line in eval_result:
                file.write(f"{line}\n")
    else:
        raise RuntimeError("Illegal return type from evaluator")
    

    try:
        remote_client.disconnect()
    except Exception as e:
        print_message(title = 'VNC Client', content = f'Error disconnecting: {e}')