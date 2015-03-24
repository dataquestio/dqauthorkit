__version__ = "0.1.0"

import sys
import argparse
import os
import getpass
import requests
import json

TOKEN_FILE_PATH = os.path.join(os.path.expanduser("~"), ".dataquest")
DATAQUEST_BASE_URL = "https://www.dataquest.io/api/v1/"
DATAQUEST_TOKEN_URL = "{0}{1}".format(DATAQUEST_BASE_URL, "accounts/get_auth_token/")

class NoAuthenticationError():
    pass

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
        get_input = getattr(__builtins__, 'raw_input', input)
        email = get_input("Enter your email for dataquest.io: ").strip()
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

    def run(self):
        path = os.path.abspath(os.path.expanduser(self.args.path))
        print(path)

def get_command_classes():
    return {cls.command_name: cls for cls in BaseCommand.__subclasses__()}

def get_auth_header():
    if not os.path.exists(TOKEN_FILE_PATH):
        print("Please use the authenticate command to sign in first.")
        raise NoAuthenticationError
    with open(TOKEN_FILE_PATH, "r") as tokenfile:
        data = json.load(tokenfile)
    return {"Authorization": "Token {0}".format(data["token"])}

def main(command):
    commands = get_command_classes()
    cls = commands[command]
    inst = cls()
    inst.run()