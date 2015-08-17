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
import ast
import subprocess
from IPython import nbformat
import re
from IPython.nbformat import current as nbf

TOKEN_FILE_PATH = os.path.join(os.path.expanduser("~"), ".dataquest")
DATAQUEST_BASE_URL = "https://www.dataquest.io/api/v1/"
DATAQUEST_TOKEN_URL = "{0}{1}".format(DATAQUEST_BASE_URL, "accounts/get_auth_token/")
DATAQUEST_MISSION_SOURCE_URL = "{0}{1}".format(DATAQUEST_BASE_URL, "missions/mission_sources/")
DATAQUEST_TASK_STATUS_URL = "{0}{1}".format(DATAQUEST_BASE_URL, "missions/task_status/")
BASE_PATH = os.path.dirname(__file__)
ROOT_PATH = os.path.dirname(BASE_PATH)

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

def mission_loader(mission_filename):
    import yaml
    with open(mission_filename, 'rb') as mission_file:
        mission_data = mission_file.read()

    mission_data = mission_data.decode("utf-8")
    mission_data = re.split("-{4,}", mission_data)
    mission_data = [yaml.safe_load(i) for i in mission_data]
    meta = mission_data[1]
    screens = [i for i in mission_data[2:] if i is not None]
    first_screen = False
    for i, s in enumerate(screens):
        if s["type"] == "code" and not first_screen:
            if "imports" in meta:
                screens[i]["initial"] = meta["imports"] + "\n\n"
                first_screen = True
        if "initial_vars" in s:
            initial = meta["vars"][int(s["initial_vars"])]
            if "initial" not in screens[i]:
                screens[i]["initial"] = initial
            else:
                screens[i]["initial"] += initial


    return meta, screens

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

class StripOutputCommand(BaseCommand):
    command_name = "strip_output"
    argument_list = BaseCommand.argument_list + [
        {
            'dest': 'file',
            'type': str,
            'help': 'The name of the file you want to strip images from.'
        }
    ]

    def _cells(self, nb):
        """Yield all cells in an nbformat-insensitive manner"""
        if nb.nbformat < 4:
            for ws in nb.worksheets:
                for cell in ws.cells:
                    yield cell
        else:
            for cell in nb.cells:
                yield cell


    def strip_output(self, nb):
        """strip the outputs from a notebook object"""
        nb.metadata.pop('signature', None)
        for cell in self._cells(nb):
            if 'outputs' in cell:
                cell['outputs'] = []
            if 'prompt_number' in cell:
                cell['prompt_number'] = None
        return nb

    def run(self):
        path = os.path.abspath(os.path.expanduser(self.args.file))
        if not path.endswith(".ipynb"):
            raise ValueError

        with open(path, 'r') as f:
            nb = nbformat.read(f, as_version=nbformat.NO_CONVERT)
        self.strip_output(nb)
        with open(path, 'w+') as f:
            nbformat.write(nb, f)

class BlogPostCommand(BaseCommand):
    command_name = "blog_post"
    argument_list = BaseCommand.argument_list + [
        {
            'dest': 'path',
            'type': str,
            'help': 'The path to the mission you want to convert.'
        }
    ]

    def run(self):
        path = os.path.abspath(os.path.expanduser(self.args.path))
        if not path.endswith(".ipynb"):
            raise ValueError
        filename = os.path.basename(path)
        filename = filename.replace(".ipynb", ".md")
        new_path = os.path.join(os.path.dirname(path), filename)
        template_path = os.path.join(BASE_PATH, "nbconvert_html")
        config_path = os.path.join(template_path , "html.py")
        subprocess.call("cd {0} && ipython nbconvert {1} --to markdown --config {2} --output {3}".format(template_path, path, config_path, new_path), shell=True)


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

class YAMLToIPythonCommand(BaseCommand):
    command_name = "convert_yaml"
    argument_list = BaseCommand.argument_list + [
        {
            'dest': 'path',
            'type': str,
            'help': 'The path to the mission you want to convert.'
        },
        {
            'dest': 'final_dir',
            'type': str,
            'help': 'The directory you want to move things to.'
        }
    ]

    def assemble_mission_meta(self, mission_data):
        text = "<!-- "
        for k in mission_data:
            if k in ["vars", "author", "name", "description", "imports"]:
                continue
            text += k
            text += "="
            if isinstance(mission_data[k], str):
                text += '"'
            text += str(mission_data[k])
            if isinstance(mission_data[k], str):
                text += '"'
            text += " "

        text += "-->"
        return text

    def assemble_mission_cell(self, mission_data):
        text = self.assemble_mission_meta(mission_data)
        text += "\n\n"
        text += "# " + mission_data["name"] + "\n"
        text += "## " + mission_data["description"] + "\n"
        text += "## " + mission_data["author"]
        return text

    def assemble_screen_meta(self, screen):
        text = "<!-- "
        for k in screen:
            if k in ["name", "left_text", "initial_display", "answer", "hint", "check_val", "check_code_run", "check_vars", "instructions", "initial_vars", "video", "no_answer_needed", "initial"]:
                continue
            text += k
            text += "="
            if isinstance(screen[k], str):
                text += '"'
            text += str(screen[k])
            if isinstance(screen[k], str):
                text += '"'
            text += " "

        text += "-->"
        return text

    def run(self):
        path = os.path.abspath(os.path.expanduser(self.args.path))
        final_dir = os.path.abspath(os.path.expanduser(self.args.final_dir))
        if not path.endswith(".yaml") and not path.endswith(".yml"):
            raise ValueError
        filename = os.path.basename(path)
        new_filename = "Mission" + filename.replace(".yml", ".ipynb").replace(".yaml", ".ipynb")
        final_dest = os.path.join(final_dir, new_filename)
        mission, screens = mission_loader(path)

        nb = nbf.new_notebook()

        mission_cell = nbf.new_text_cell('markdown', self.assemble_mission_cell(mission).strip())
        cells = [mission_cell]

        for screen in screens:
            text = self.assemble_screen_meta(screen)
            text += "\n\n"
            if screen["type"] == "code":
                text += "# " + screen["name"]
                text += "\n\n"
                text += screen["left_text"]
                if "instructions" in screen:
                    text += "\n\n"
                    text += "## Instructions\n\n"
                    text += screen["instructions"]
                if "hint" in screen:
                    text += "\n\n"
                    text += "## Hint\n\n"
                    text += screen["hint"]
            elif screen["type"] == "video":
                text += "# " + screen["name"]
                text += "\n\n"
                text += screen["video"]
            elif screen["type"] == "text":
                text += "# " + screen["name"]
                text += "\n\n"
                text += screen["text"]
            cell = nbf.new_text_cell('markdown', text.strip())
            cells.append(cell)

            if screen["type"] == "code":
                text = ""
                if "initial" not in screen and "answer" not in screen:
                    text += screen["initial_display"]
                else:
                    items = [
                        {"key": "initial", "name": "## Initial"},
                        {"key": "initial_display", "name": "## Display"},
                        {"key": "answer", "name": "## Answer"},
                        {"key": "check_val", "name": "## Check val"},
                        {"key": "check_vars", "name": "## Check vars"},
                        {"key": "check_code_run", "name": "## Check code run"}
                    ]

                    for item in items:
                        if item["key"] in screen and len(str(screen[item["key"]]).strip()) > 0:
                            if item["key"] == "check_vars" and len(screen[item["key"]]) == 0:
                                continue
                            text += item["name"] + "\n\n"
                            if item["key"] == "check_val":
                                text += '"' + str(screen[item["key"]]).strip().replace("\n", "\\n") + '"'
                            else:
                                text += str(screen[item["key"]]).strip()
                            text += "\n\n"
                cell = nbf.new_code_cell(input=text.strip())
                cells.append(cell)

        nb['worksheets'].append(nbf.new_worksheet(cells=cells))

        with open(final_dest, 'w+') as f:
            nbf.write(nb, f, 'ipynb')

        # Copy any associated files over
        original_dir = os.path.dirname(path)
        for f in os.listdir(original_dir):
            full_path = os.path.join(original_dir, f)
            if os.path.isfile(full_path):
                if not f.endswith(".yaml") and not f.endswith(".yml") and not f.endswith(".ipynb"):
                    shutil.copy2(full_path, os.path.join(final_dir, f))


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
        data = data.split("\n")
        metadata = self.parse_metadata_string(data[0])
        counter = 0
        for l in data[1:]:
            if l.startswith("#"):
                name = re.sub("#{1,}", "", l).strip()
                if counter == 0:
                    metadata["name"] = name
                elif counter == 1:
                    metadata["description"] = name
                elif counter == 2:
                    metadata["author"] = name
                counter += 1
        return metadata

    def parse_screen_metadata(self, data):
        data = data.split("\n")
        metadata = self.parse_metadata_string(data[0])
        counter = 0
        for l in data[1:]:
            if l.startswith("#"):
                name = re.sub("#{1,}", "", l).strip()
                if counter == 0:
                    metadata["name"] = name
                counter += 1
        return metadata

    def parse_metadata_string(self, data):
        if "<!-" not in data:
            print("Missing metadata string at top of mission/screen.")
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

    def check_for_no_answer(self, screen_info):
        if "answer" not in screen_info or ("check_vars" not in screen_info and "check_val" not in screen_info and "check_code_run" not in screen_info) or "instructions" not in screen_info:
            return True
        return False

    def parse_section(self, data, current_item):
        lines = data.split("\n")
        items = {current_item: []}
        for data in lines:
            if data.startswith("##"):
                current_item = re.sub("#{1,}", "", data.strip().lower()).strip()
                if current_item not in items:
                    items[current_item] = []
            else:
                if current_item is not None:
                    items[current_item] += [data]
        for k in items:
            items[k] = "\n".join(items[k]).strip()
        return items

    def update_screen_info(self, items, screen_info, key_mappings):
        for k in key_mappings:
            if key_mappings[k] in items:
                screen_info[k] = items[key_mappings[k]]
        return screen_info

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
            sd = "".join(s["source"])
            if "<!-" in sd:
                if len(screen_info) > 0:
                    if self.check_for_no_answer(screen_info):
                        screen_info["no_answer_needed"] = "True"
                    screens.append(screen_info)
                screen_info = self.parse_screen_metadata(sd)
                screen_names = sd.split("#", 1)[1]
                screen_names = screen_names.replace(screen_info["name"], "", 1).strip()
                current_item = "left_text"
                if screen_info["type"] == "video":
                    current_item = "video"
                elif screen_info["type"] == "text":
                    current_item = "text"
                items = self.parse_section(screen_names, current_item)
                screen_info = self.update_screen_info(items, screen_info, {
                    "left_text": "left_text",
                    "video": "video",
                    "instructions": "instructions",
                    "hint": "hint",
                    "text": "text"
                })
            elif s["cell_type"] == "code":
                if screen_info.get("initial_display") is not None:
                    continue
                # Remove any ipython line magics from the code.
                code_data = "\n".join([l for l in sd.split("\n") if not l.startswith("%")])
                items = self.parse_section(code_data, "display")
                try:
                    items["check val"] = ast.literal_eval(items["check val"])
                    if not isinstance(items["check val"], str):
                        items["check val"] = str(items["check val"])
                except Exception:
                    pass
                screen_info = self.update_screen_info(items, screen_info, {
                    "initial_vars": "initial",
                    "initial_display": "display",
                    "answer": "answer",
                    "check_vars": "check vars",
                    "check_val": "check val",
                    "check_code_run": "check code run"
                })

        if len(screen_info) > 0:
            if self.check_for_no_answer(screen_info):
                screen_info["no_answer_needed"] = "True"
            screens.append(screen_info)

        return mission_metadata, screens

    def generate_yaml(self, mission_metadata, screens):
        separator = "--------"
        yaml_data = [separator, ""]
        initial_vars = []
        code = []
        for s in screens:
            if s["type"] != "code":
                continue
            if "initial_vars" in s:
                vars = code + [s["initial_vars"]]
            else:
                vars = code
            ivars = "\n".join(vars)
            initial_vars.append(ivars)
            s["full_initial_vars"] = ivars
            if "initial_vars" in s:
                code.append(s["initial_vars"])

        for k in ["name", "description", "author", "prerequisites", "language", "premium", "under_construction", "file_list", "mission_number", "mode", "persist_container"]:
            if k in mission_metadata:
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
            for k in ["name", "type", "check_vars", "no_answer_needed", "video", "error_okay"]:
                if k in s:
                    yaml_data.append("{0}: {1}".format(k, s[k]))
            for k in ["left_text", "initial_display", "answer", "hint", "check_val", "check_code_run", "instructions", "text"]:
                if k in s:
                    yaml_data.append("{0}: |".format(k))
                    lines = s[k].split("\n")
                    for l in lines:
                        yaml_data.append("  {0}".format(l))
            if s["type"] == "code":
                yaml_data.append("initial_vars: {0}".format(initial_vars.index(s["full_initial_vars"]) + 1))
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
            try:
                file_list = json.loads(mission_metadata["file_list"])
            except Exception:
                file_list = ast.literal_eval(mission_metadata["file_list"])

            for f in file_list:
                f_path = os.path.join(path, f)
                dest_path = os.path.join(mission_path, f)
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
        print("Please sign in first.")
        auth = AuthenticateCommand()
        auth.run()
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