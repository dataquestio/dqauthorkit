import re
from setuptools import setup


version = re.search(
    '^__version__\s*=\s*"(.*)"',
    open('dqauthorkit/dqauthorkit.py').read(),
    re.M
).group(1)

with open("README.md", "rb") as f:
    long_descr = f.read().decode("utf-8")

setup(
    name="dqauthorkit",
    packages=["dqauthorkit"],
    entry_points={
        "console_scripts": ['dqauthor = dqauthorkit.dqauthorkit:main']
    },
    version=version,
    description="Python command line tool to make creating content for dataquest.io easier.",
    long_description=long_descr,
    author="Vik Paruchuri",
    author_email="vik@dataquest.io",
    url="https://github.com/dataquestio/dqauthorkit",
    license="MIT",
    install_requires=["requests"],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
         'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ]
)