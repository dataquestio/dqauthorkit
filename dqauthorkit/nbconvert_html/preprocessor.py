from IPython.nbconvert.preprocessors import *
from collections import namedtuple
import re

class HTMLPreprocessor(Preprocessor):

    def preprocess_cell(self, cell, resources, index):
        """
        Adds bold 'cheese' to the start of every markdown cell.
        """
        cell.source = re.sub("<!-.+->", "", cell.source)
        cell.source = cell.source.strip()
        if 'source' in cell:
            if index == 0:
                lines = cell.source.split("\n")
                cell.source = lines[0]
                print("Lesson Name: {0}".format(lines[0]))
            else:
                if cell.cell_type == "markdown":
                    cell.source = cell.source.split("## Instructions")[0]
                    if cell.source.startswith("#"):
                        cell.source = "#" + cell.source
                else:
                    data = cell.source.split("## Display")
                    if len(data) == 1:
                        cell.source = data[0]
                    else:
                        data = data[1]
                        data = data.replace("## Answer", "")
                        for item in ["## Check vars", "## Check val", "## Check code run"]:
                            regex = re.compile(re.escape(item), re.IGNORECASE)
                            data = regex.split(data)[0]
                        cell.source = data
            cell.source = cell.source.strip()
        return cell, resources