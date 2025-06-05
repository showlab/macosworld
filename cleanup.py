import os
import shutil
import argparse

def clean_directories(base_save_dir):
    # Check if the directory exists
    if not os.path.isdir(base_save_dir):
        raise ValueError(f'Directory does not exist: {base_save_dir}')
    # Iterate through each item in the base directory
    for category_dir in os.listdir(base_save_dir):
        if os.path.isdir(os.path.join(base_save_dir, category_dir)):
            # Iterate through each item in the category directory
            for subdirectory in os.listdir(os.path.join(base_save_dir, category_dir)):
                subdirectory_path = os.path.join(base_save_dir, category_dir, subdirectory)
                
                # Check if the item is a directory
                if os.path.isdir(subdirectory_path):
                    # List all files in the subdirectory
                    files = os.listdir(subdirectory_path)
                    
                    # Check if there is at least one .txt file in the subdirectory
                    if not any(file.endswith('.txt') for file in files):
                        # If no .txt files are found, delete the subdirectory
                        print(f"Deleting: {subdirectory_path}")
                        shutil.rmtree(subdirectory_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base_save_dir", type=str, required=True)
    args = parser.parse_args()

    clean_directories(args.base_save_dir)
