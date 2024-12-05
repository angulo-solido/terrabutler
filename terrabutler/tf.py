import signal
import subprocess
from colorama import Fore
from sys import exit
from terrabutler.settings import get_settings
from terrabutler.utils import paths

# Values from Config
org = get_settings()["general"]["organization"]


def terraform_args_print(command, site):
    """
    Print Args
    """

    if command == "init":
        needed_options = "backend"
    elif command == "plan" or command == "apply":
        needed_options = "var"

    options = terraform_needed_options_builder(needed_options, site)
    return " ".join(options)


def terraform_needed_options_builder(needed_options, site):
    """
    Create array of needed options for backend or var files
    """
    from terrabutler.env import get_current_env
    env = get_current_env()
    default_env = get_settings()["environments"]["default"]["name"]

    if needed_options == "backend":
        backend_dir = paths["backends"]

        if site == "inception":  # Init inception with default ENV
            return ["-backend-config",
                    f"{backend_dir}/{org}-{default_env}-inception.tfvars"]
        else:
            return ["-backend-config",
                    f"{backend_dir}/{org}-{env}-{site}.tfvars"]

    elif needed_options == "var":
        variables_dir = paths["variables"]

        return ["-var-file", f"{variables_dir}/global.tfvars",
                "-var-file", f"{variables_dir}/{org}-{env}.tfvars",
                "-var-file", f"{variables_dir}/{org}-{env}-{site}.tfvars"
                ]

    else:  # If needed_options is empty, return empty array
        return []


def terraform_command_builder(command, site, args=[], options=[],
                              needed_options=""):
    """
    Create the command to run terraform
    """
    aux = ["terraform", command]  # Start base command

    if needed_options == "backend" or needed_options == "var":
        aux += terraform_needed_options_builder(needed_options, site)

    aux += options  # Add options passed by user
    aux += args  # Add args passed by user

    return aux


def terraform_command_runner(command, site, args=[], options=[],
                             needed_options=""):
    """
    Run tfenv and run the terraform command
    """
    from terrabutler.env import get_current_env
    site_dir = f"{paths['root']}/site_{site}"
    env = get_current_env()

    command = terraform_command_builder(command, site, args=args,
                                        options=options,
                                        needed_options=needed_options)

    prev_sigint_handler = signal.getsignal(signal.SIGINT)
    try:
        p = subprocess.Popen(args=command, cwd=site_dir)
        signal.signal(signal.SIGINT, signal.SIG_IGN)  # ignore on python thread
        p.wait()

        if p.returncode != 0:
            print(Fore.RED + "There was an error while running the terraform"
                  " command.")
            exit(1)
    except subprocess.CalledProcessError:
        print(Fore.RED + f"There was an error while doing the {command}"
              f" command inside the '{site}' site in '{env}' environment.")
        exit(1)
    finally:
        signal.signal(signal.SIGINT, prev_sigint_handler)


def terraform_destroy_all_sites():
    """
    Destroy all sites by looping through all sites in reverse order
    """
    sites = list(reversed(get_settings()["sites"]["ordered"]))
    for site in sites:
        terraform_command_runner("destroy", site, options=["-auto-approve"],
                                 needed_options="var")


def terraform_apply_all_sites():
    """
    Destroy all sites by looping through all sites
    """
    sites = list(get_settings()["sites"]["ordered"])
    for site in sites:
        if site != "inception":
            terraform_command_runner("init", site, options=["-reconfigure"],
                                     needed_options="backend")
        terraform_command_runner("apply", site, options=["-auto-approve"],
                                 needed_options="var")


def terraform_init_all_sites():
    """
    Init all sites by looping through all sites (inception doesn't need a init)
    """
    sites = list(get_settings()["sites"]["ordered"])
    if "inception" in sites:
        sites.remove("inception")
    for site in sites:
        print(Fore.YELLOW + f"Initializing {site} site")
        terraform_command_runner("init", site, options=["-reconfigure"],
                                 needed_options="backend")
