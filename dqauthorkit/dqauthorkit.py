__version__ = "0.1.0"

import sys
import argparse
import os
import getpass
import requests
import json
import re
import shutil
import time
import sys

TOKEN_FILE_PATH = os.path.join(os.path.expanduser("~"), ".dataquest")
DATAQUEST_BASE_URL = "https://www.dataquest.io/api/v1/"
DATAQUEST_TOKEN_URL = "{0}{1}".format(DATAQUEST_BASE_URL, "accounts/get_auth_token/")
DATAQUEST_MISSION_SOURCE_URL = "{0}{1}".format(DATAQUEST_BASE_URL, "missions/mission_sources/")
DATAQUEST_TASK_STATUS_URL = "{0}{1}".format(DATAQUEST_BASE_URL, "missions/task_status/")

class NoAuthenticationError(Exception):
    pass

class InvalidPythonError(Exception):
    pass

class InvalidFormatError(Exception):
    pass

class UserQuitException(Exception):
    pass

class ServerFailureException(Exception):
    pass

def get_input():
    return getattr(__builtins__, 'raw_input', input)

class BaseCommand(object):
    argument_list = [
        {
            'dest': 'command',
            'type': str,
            'help': 'The command to run.'
        }
    ]

    def __init__(self):
        self.parser = argparse.ArgumentParser(description='Run helper commands for dataquest.')
        for arg in self.argument_list:
            self.parser.add_argument(**arg)
        self.args = self.parser.parse_args()

class HelpCommand(BaseCommand):
    command_name = "help"

    def run(self):
        print("Potential commands are:")
        for command in get_command_classes():
            print(command)

class AuthenticateCommand(BaseCommand):
    command_name = "authenticate"

    def run(self):
        email = get_input()("Enter your email for dataquest.io: ").strip()
        password = getpass.getpass("Enter your password: ").strip()
        resp = requests.post(DATAQUEST_TOKEN_URL, data={"email": email, "password": password})
        if resp.status_code == 200:
            data = json.loads(resp.content.decode("utf-8"))
            write_data = {
                "token": data["token"],
                "email": email
            }
            with open(TOKEN_FILE_PATH, "w+") as tokenfile:
                json.dump(write_data, tokenfile)
            print("Authentication info written to {0}.  You can now upload and test your missions.".format(TOKEN_FILE_PATH))
        else:
            print("Invalid email or password.  Please try again.")

class GenerateMissions(BaseCommand):
    command_name = "generate"
    argument_list = BaseCommand.argument_list + [
        {
            'dest': 'path',
            'type': str,
            'help': 'The path to your mission folder.'
        }
    ]

    def parse_mission_metadata(self, data):
        data = re.split("-{1,}>", data)
        metadata = self.parse_metadata_string(data[0])
        lines = "".join(data[1:])
        lines = [l.strip() for l in re.split("#{1,}", lines)]
        lines = [l for l in lines if len(l) > 0]
        if len(lines) != 3:
            print("Invalid mission name, description, and author fields.")
            raise InvalidFormatError()

        metadata["name"] = lines[0]
        metadata["description"] = lines[1]
        metadata["author"] = lines[2]
        return metadata

    def parse_screen_metadata(self, data):
        data = re.split("-{1,}>", data)
        metadata = self.parse_metadata_string(data[0])
        lines = "".join(data[1:])

        lines = [l.strip() for l in re.split("#{1,}", lines.strip())]
        lines = [l for l in lines if len(l) > 0]
        metadata["name"] = lines[0]
        return metadata

    def parse_metadata_string(self, data):
        if "<!-" not in data:
            print("Missing metadata string.")
            raise InvalidFormatError()

        data = re.sub("<!-{1,}", "", data)
        data = re.split("-{1,}>", data)[0]
        data = data.split("=")
        values = {}
        key = None
        for i, item in enumerate(data):
            item = item.strip()
            if key is None:
                key = item
            else:
                vals = item.rsplit(' ', 1)
                if len(vals) == 2:
                    item, next_key = vals
                else:
                    item = vals[0]
                if key != "file_list":
                    item = item.replace("\"", "").replace("'", "")
                values[key] = item
                if len(vals) == 2:
                    key = next_key
                else:
                    key = None
        return values

    def update_screen_info(self, data, info, data_key, info_key):
        if data.lower().startswith(data_key.lower()):
            info[info_key] = data[len(data_key):].strip()
        return info

    def check_start_string(self, data, keys):
        for k in keys:
            if data.lower().startswith(k.lower()):
                return True
        return False

    def check_for_no_answer(self, screen_info):
        if "answer" not in screen_info or ("check_vars" not in screen_info and "check_val" not in screen_info and "check_code_run" not in screen_info) or "instructions" not in screen_info:
            return True
        return False

    def parse_notebook(self, data):
        cells = data["cells"]
        metadata = data["metadata"]
        if metadata["kernelspec"]["name"] != "python3":
            print("Dataquest requires the use of python3.  Please change your kernel and test your code.")
            raise InvalidPythonError()
        mission_data = cells[0]
        screen_data = cells[1:]
        if mission_data["cell_type"] != "markdown":
            print("No metadata for the mission found.  Add this in before generating yaml files.")
            raise InvalidFormatError()
        mission_info = "".join(mission_data["source"])
        mission_metadata = self.parse_mission_metadata(mission_info)
        screens = []
        screen_info = {}
        for i, s in enumerate(screen_data):
            screen_data = "".join(s["source"])
            if "<!-" in screen_data:
                if len(screen_info) > 0:
                    if self.check_for_no_answer(screen_info):
                        screen_info["no_answer_needed"] = "True"
                    screens.append(screen_info)
                screen_info = self.parse_screen_metadata(screen_data)
                screen_names = screen_data.split("##")
                intro = screen_names[1]
                if len(screen_names) > 2:
                    instructions = screen_names[2]
                else:
                    instructions = ""
                instructions = instructions.replace("Instructions", "", 1).strip()
                intro = intro.replace("Intro", "", 1).strip()
                if len(instructions) > 0:
                    screen_info["instructions"] = instructions
                screen_info["left_text"] = intro
            elif s["cell_type"] == "code":
                screen_datas = [s.strip() for s in re.split("#{1,}", screen_data)]
                screen_datas = [s for s in screen_datas if len(s) > 0]
                for data in screen_datas:
                    screen_info = self.update_screen_info(data, screen_info, "initial", "initial_vars")
                    screen_info = self.update_screen_info(data, screen_info, "display", "initial_display")
                    screen_info = self.update_screen_info(data, screen_info, "answer", "answer")
                    screen_info = self.update_screen_info(data, screen_info, "check vars", "check_vars")
                    screen_info = self.update_screen_info(data, screen_info, "check val", "check_val")
                    screen_info = self.update_screen_info(data, screen_info, "check code run", "check_code_run")
                if len(screen_datas) == 1 and not self.check_start_string(data, ["initial", "display", "answer", "check vars", "check val", "check code run"]):
                    screen_info["initial_display"] = screen_datas[0]

            elif "## hint" in screen_data.lower():
                hint = screen_data.strip()[len("## hint"):].strip()
                screen_info["hint"] = hint
        if len(screen_info) > 0:
            if self.check_for_no_answer(screen_info):
                screen_info["no_answer_needed"] = "True"
            screens.append(screen_info)

        print("Mission data:")
        print(mission_metadata)
        print("Screen data:")
        print(screens)

        return mission_metadata, screens

    def generate_yaml(self, mission_metadata, screens):
        separator = "--------"
        yaml_data = [separator, ""]
        initial_vars = []
        for s in screens:
            if "initial_vars" in s:
                initial_vars.append(s["initial_vars"])
        for k in mission_metadata:
            yaml_data.append("{0}: {1}".format(k, mission_metadata[k]))
        if len(initial_vars) > 0:
            yaml_data.append("vars:")
            for i, v in enumerate(initial_vars):
                yaml_data.append("  {0}: |".format(i+1))
                for l in v.split("\n"):
                    yaml_data.append("    {0}".format(l))
        yaml_data += ["", separator]

        for s in screens:
            yaml_data += [""]
            for k in ["name", "type", "check_vars", "no_answer_needed"]:
                if k in s:
                    yaml_data.append("{0}: {1}".format(k, s[k]))
            for k in ["left_text", "initial_display", "answer", "hint", "check_val", "check_code_run"]:
                if k in s:
                    yaml_data.append("{0}: |".format(k))
                    lines = s[k].split("\n")
                    for l in lines:
                        yaml_data.append("  {0}".format(l))
            if "initial_vars" in s:
                yaml_data.append("initial_vars: {0}".format(initial_vars.index(s["initial_vars"]) + 1))
            yaml_data += ["", separator]
        full_data = "\n".join(yaml_data)
        return full_data


    def run(self):
        path = os.path.abspath(os.path.expanduser(self.args.path))
        files = [os.path.join(path, f) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        nb_files = [f for f in files if f.endswith(".ipynb")]
        yaml_path = os.path.join(path, "missions")
        if not os.path.exists(yaml_path):
            os.makedirs(yaml_path)

        for nb_path in nb_files:
            print("Processing file at {0}".format(nb_path))
            with open(nb_path, "r") as nbfile:
                data = json.load(nbfile)
            mission_metadata, screens = self.parse_notebook(data)
            yaml_data = self.generate_yaml(mission_metadata, screens)
            mission_path = os.path.join(yaml_path, mission_metadata["mission_number"])
            if not os.path.exists(mission_path):
                os.makedirs(mission_path)
            mission_file = os.path.join(mission_path, "{0}.yaml".format(mission_metadata["mission_number"]))
            with open(mission_file, "w+") as mfile:
                mfile.write(yaml_data)
            for f in json.loads(mission_metadata["file_list"]):
                f_path = os.path.join(path, f)
                dest_path = os.path.join(mission_path, f)
                if not os.path.exists(dest_path):
                    shutil.copy2(f_path, dest_path)
        print("Finished writing yaml data to {0}".format(yaml_path))

def get_sources():
    auth_header = get_auth_header()
    resp = requests.get(DATAQUEST_MISSION_SOURCE_URL, headers=auth_header)
    data = json.loads(resp.content.decode("utf-8"))
    return data

def get_source_selection():
    sources = get_sources()
    print("Your mission sources:")
    for i, source in enumerate(sources):
        print("{0}: {1}".format(i+1, source["path"]))
    selection = get_input()("Enter your selection (or enter -1 to quit): ").strip()
    selection = int(selection) - 1
    if selection == -2:
        raise UserQuitException()
    source = sources[selection]
    return source

def poll_api_endpoint(url):
    auth_header = get_auth_header()
    resp = requests.post(url, headers=auth_header)
    data = json.loads(resp.content.decode("utf-8"))
    params = {
        "task_type": data["task_type"],
        "task_id": data["task_id"]
    }
    i = 0
    status = {"state": "PENDING"}
    while i < 500 and status["state"] == "PENDING":
        i += 1
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(10)
        resp = requests.get(DATAQUEST_TASK_STATUS_URL, params=params, headers=auth_header)
        status = json.loads(resp.content.decode("utf-8"))
    if status["state"] == "FAILURE":
        print("Error executing your command.")
        print(status["result"])
        raise ServerFailureException()
    elif status["state"] == "SUCCESS":
        print("..Done.")
    return status["result"]

class TestMissionCommand(BaseCommand):
    command_name = "test"

    def run(self):
        source = get_source_selection()
        url = "{0}{1}/test/".format(DATAQUEST_MISSION_SOURCE_URL, source["id"])
        sys.stdout.write("Testing...")
        result = poll_api_endpoint(url)
        print("Here's the output.  Make sure to look over this for errors:")
        print(result["output"])

class SyncMissionCommand(BaseCommand):
    command_name = "sync"

    def run(self):
        source = get_source_selection()
        url = "{0}{1}/sync/".format(DATAQUEST_MISSION_SOURCE_URL, source["id"])
        sys.stdout.write("Syncing...")
        result = poll_api_endpoint(url)
        print("Here's the output.  Make sure to look over this for errors:")
        print(result["output"])

def get_command_classes():
    return {cls.command_name: cls for cls in BaseCommand.__subclasses__()}

def get_auth_header():
    if not os.path.exists(TOKEN_FILE_PATH):
        print("Please use the authenticate command to sign in first.")
        raise NoAuthenticationError
    with open(TOKEN_FILE_PATH, "r") as tokenfile:
        data = json.load(tokenfile)
    return {"Authorization": "Token {0}".format(data["token"])}

def main():
    parser = argparse.ArgumentParser(description='Run helper commands for dataquest.')
    parser.add_argument(dest='command', type=str, help='The command to run.')
    parser.add_argument(dest='options', help='Additional options.', nargs="*")

    args = parser.parse_args()
    command = args.command
    commands = get_command_classes()
    cls = commands[command]
    inst = cls()
    inst.run()