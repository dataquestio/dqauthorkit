import argparse

parser = argparse.ArgumentParser(description='Run helper commands for dataquest.')
parser.add_argument(dest='command', type=str, help='The command to run.')
parser.add_argument(dest='options', help='Additional options.', nargs="*")

args = parser.parse_args()

from .dqauthorkit import main
main(args.command)