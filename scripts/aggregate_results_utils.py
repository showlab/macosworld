import os
import pandas as pd

def aggregate_results(root_dir):
    records = []
    # iterate over first‐level subfolders
    for category in os.listdir(root_dir):
        cat_path = os.path.join(root_dir, category)
        if not os.path.isdir(cat_path):
            continue

        # iterate over second‐level subfolders
        for sub in os.listdir(cat_path):
            sub_path = os.path.join(cat_path, sub)
            if not os.path.isdir(sub_path):
                continue

            parts = sub.split('_')
            if len(parts) != 3:
                # skip any folder not matching uuid_task_env pattern
                continue
            uuid, task_lang, env_lang = parts

            eval_file = os.path.join(sub_path, 'eval_result.txt')
            if not os.path.isfile(eval_file):
                continue

            # read the single integer score
            try:
                with open(eval_file, 'r') as f:
                    line = f.readline().strip()
                score = int(line)
            except Exception as e:
                print(f"Warning: could not parse score in {eval_file}: {e}")
                continue

            records.append({
                'category':      category,
                'uuid':          uuid,
                'task_language': task_lang,
                'env_language':  env_lang,
                'score':         score
            })

    # build DataFrame
    df = pd.DataFrame(records, columns=[
        'category', 'uuid', 'task_language', 'env_language', 'score'
    ])

    # save to CSV
    out_csv = os.path.join(root_dir, 'aggregated.csv')
    df.to_csv(out_csv, index=False)
    print(f"Saved aggregated results to {out_csv}")

    # print distributions per (task_language, env_language)
    grouped = df.groupby(['task_language', 'env_language'])
    for (task, env), group in grouped:
        counts = group['score'].value_counts().sort_index()
        dist_str = ', '.join(f"{sc}: {cnt}" for sc, cnt in counts.items())
        mean_score = group['score'].mean()
        print(f"\n[task_language {task}, env_language {env}]")
        print(dist_str)
        print(f"Mean score: {mean_score:.2f}")


def collect_distraction_results(path, filter_words=None):
    """
    Walks through `path`, finds all 'distraction_result.txt' files,
    optionally filters them by substrings in the directory name,
    reads the first line of each as a string, and returns a list of these strings.
    
    :param path:      Root directory to start the search.
    :param filter_words:  List of substrings to filter on (all must be present
                          in the directory name). If None, no filtering is done.
    :return:          List of strings, each the first line of a found file.
    """
    results = []
    for root, _, files in os.walk(path):
        for file in files:
            if file == "distraction_result.txt":
                file_path = os.path.join(root, file)

                # Get the name of the immediate parent directory
                dir_name = os.path.basename(os.path.dirname(file_path))

                # If filter_words is given, check that each appears in '_<dir_name>_'
                if filter_words is None or all(word in f'_{dir_name}_' for word in filter_words):
                    try:
                        with open(file_path, "r") as f:
                            line = f.readline().rstrip("\n")
                            results.append(line)
                        print(f"File processed: {file_path}")
                    except Exception as e:
                        print(f"Warning: Could not read from {file_path}: {e}")
    return results

def aggregate_distraction_results(path, filter_words = None):
    distraction_results = collect_distraction_results(path, filter_words)

    count_distracted = distraction_results.count('distracted')
    count_gold = distraction_results.count('gold')
    count_not_handled = distraction_results.count('not_handled')

    print(f'# Distracted: {count_distracted}')
    print(f'# Gold: {count_gold}')
    print(f'# Not handled: {count_not_handled}')

def calculate_overall_score(
    score_sys_and_interface,
    score_sys_apps,
    score_file_management,
    score_productivity,
    score_media,
    score_multitasking,
):
    """
    Computes and prints the weighted average across seven categories.
    Each argument corresponds to the numeric value for that category.

    Args:
        system_interface   (int or float): Value for "System & Interface"
        system_apps        (int or float): Value for "System Apps"
        file_management    (int or float): Value for "File Management"
        productivity       (int or float): Value for "Productivity"
        media              (int or float): Value for "Media"
        multitasking       (int or float): Value for "Multitasking"
    """
    # 1) Define the (fixed) weights for each category:
    weights = {
        "System & Interface": 29,
        "System Apps":        38,
        "File Management":    29,
        "Productivity":       35,
        "Media":              12,
        "Multitasking":       28,
    }

    # 2) Collect the passed‐in values into a dict matching weight keys:
    all_values = {
        "System & Interface": score_sys_and_interface,
        "System Apps":        score_sys_apps,
        "File Management":    score_file_management,
        "Productivity":       score_productivity,
        "Media":              score_media,
        "Multitasking":       score_multitasking,
    }

    # 3) Sanity check: make sure none of the inputs are None
    for category, val in all_values.items():
        if val is None:
            raise ValueError(f"'{category}' is set to None. Please pass in a numeric value.")

    # 4) Compute weighted sum and total weight
    total_weight = sum(weights.values())
    weighted_sum  = 0.0

    for category, weight in weights.items():
        category_value = all_values[category]
        weighted_sum += weight * category_value

    weighted_average = weighted_sum / total_weight

    # 5) Print the result
    print(f"Overall score = {weighted_average}")