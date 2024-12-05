from terrabutler.settings import get_settings
from terrabutler.tf import terraform_init_all_sites
from terrabutler.utils import paths
from click import confirm
from colorama import Fore
from sys import exit
import boto3
import os
import subprocess

# Values from Settings
org = get_settings()["general"]["organization"]
default_env_name = get_settings()["environments"]["default"]["name"]


def create_env(env, confirmation, temporary, apply, s3):
    from terrabutler.settings import write_settings
    from terrabutler.tf import terraform_apply_all_sites
    from terrabutler.variables import generate_var_files
    available_envs = get_available_envs(s3)

    if env in available_envs:
        print(Fore.YELLOW + "The environment you are trying to create already"
              " exists.\n\nNo changes were made.")
        exit(1)
    elif confirmation or confirm(f"Do you really want to create '{env}'" +
                                 " environment?", default=False):
        try:
            subprocess.run(args=['terraform', 'workspace', 'new', env],
                           cwd=paths["inception"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        except subprocess.CalledProcessError:
            print(Fore.RED + "There was an error while creating the new"
                  " environment.")
            exit(1)
        if temporary:  # Generate only for temporary environments
            generate_var_files(env)
        else:  # When permanent environment add to the list
            config_file = get_settings()  # Original config file
            envs = config_file["environments"]["permanent"]
            envs.append(env)
            write_settings(config_file)
        if apply and temporary:
            terraform_apply_all_sites()
        reload_direnv()
        print(Fore.GREEN + f"Created and switched to the environment '{env}'!")
    else:
        print(Fore.RED + "Creation cancelled.")
        exit(1)


def delete_env(env, confirmation, destroy, s3):
    from terrabutler.tf import terraform_destroy_all_sites
    available_envs = get_available_envs(s3)
    current_env = get_current_env()
    permanent_environments = get_settings()["environments"]["permanent"]

    if env not in available_envs:
        print(Fore.RED + "The environment you are trying to delete does not"
              " exist.\n\nNo changes were made.")
        exit(1)
    elif env == current_env:
        print(Fore.RED + "The environment you are trying to delete is your"
              " active environment.\n\nPlease switch to another workspace "
              "and try again.")
        exit(1)
    elif env in permanent_environments:
        print(Fore.RED + "The environment you are trying to delete is a" +
              " permanent environment and can not be deleted.\n\nNo changes" +
              " were made.")
        exit(1)
    elif confirmation or confirm(f"Do you really want to delete '{env}'" +
                                 " environment?", default=False):
        if destroy and not is_protected_env(env):
            terraform_destroy_all_sites()  # Destroy all sites
        for file in os.listdir(paths["variables"]):
            if file.startswith(f"{org}-{env}"):
                os.remove(os.path.join(paths["variables"], file))
        try:
            subprocess.run(args=['terraform', 'workspace', 'delete', env],
                           cwd=paths["inception"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        except subprocess.CalledProcessError:
            print(Fore.RED + f"There was an error while deleting the '{env}'"
                  "environment.")
            exit(1)
        print(Fore.GREEN + f"The environment '{env}' was deleted!")
    else:
        print(Fore.RED + "Deletion cancelled.")
        exit(1)


def get_current_env():
    with open(paths["environment"], 'r') as f:
        return f.read()


def set_current_env(env, s3, init=False):
    current_env = get_current_env()
    available_envs = get_available_envs(s3)

    if env == current_env:
        print(Fore.YELLOW + "The environment you selected is the current one."
              "\n\nNo changes were made.")
        exit(0)
    elif env not in available_envs:
        print(Fore.RED + f"The environment '{env}' does not exist.\n\nYou can"
              " create this environment with the 'new' command.")
        exit(1)
    else:
        try:
            with open(paths["environment"], "w") as f:
                f.write(env)
        except FileNotFoundError:
            print(Fore.RED + "The file that manages the environments could not"
                  " be found.")
            exit(1)

        reload_direnv()
        if init:
            terraform_init_all_sites()
        print("\n\n" + Fore.GREEN + f"Switched to environment '{env}'.")


def get_available_envs(s3):

    envs = []

    # Get Environments by accessing S3
    if s3:
        dev_env = boto3.session.Session(profile_name=f"{org}"
                                        f"-{default_env_name}")
        s3 = dev_env.resource("s3")
        bucket = s3.Bucket(f"{org}-{default_env_name}-site-inception")

        envs = []

        for folder in bucket.objects.filter(Prefix="env:/", Delimiter=""):
            folder_name = folder.key.split('/')[1].strip()
            envs.append(folder_name)

        return envs

    # Get Environments by accessing the .terraform/environment file
    directory = paths["inception"]
    subprocess.run(args=["terraform", "init", "-reconfigure",
                         "-backend-config",
                         f"{paths['backends']}/{org}-{default_env_name}-"
                         "inception.tfvars"],
                   cwd=directory,
                   stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    process = subprocess.run(args=['terraform', 'workspace', 'list'],
                             cwd=directory,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL,
                             universal_newlines=False)
    workspaces = process.stdout.splitlines()
    if len(workspaces) > 1:  # Only run if we have already done a init
        workspaces.pop()  # Remove null entry
        workspaces.pop(0)  # Pop default workspace
    for workspace in workspaces:
        envs.append(workspace.decode(
            "utf-8").replace(" ", "").replace("*", ""))
    return envs


def reload_direnv():
    try:
        subprocess.run(args=['direnv', 'reload'])
    except subprocess.CalledProcessError as e:
        print(e.output)


def is_protected_env(env):
    protected_envs = get_settings()["environments"]["permanent"]
    if env in protected_envs:
        return True
    return False
