import os
from setuptools import setup, find_packages


def get_version():
    THIS_DIR = os.path.dirname(os.path.realpath(__file__))
    main_ns = {}
    with open(os.path.join(THIS_DIR, "ccb/_version.py")) as ver_file:
        exec(ver_file.read(), main_ns)
    return main_ns["__version__"]


setup(
    name="conan-center-bot",
    version=get_version(),
    license="GPLv3",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "conan-center-bot=ccb.__main__:main",
        ],
    },
    include_package_data=True,
    install_requires=[
        "terminaltables<4",
        "ruamel.yaml<0.17",
        "aiohttp<4",
        "colored<2",
        "conan<2",
    ],
    author="Quentin Chateau",
    author_email="quentin.chateau@gmail.com",
    description="A bot to automatically update conan-center-index",
    long_description=open("README.md", "r").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/qchateau/conan-center-bot",
    classifiers=[
        "Development Status :: 1 - Planning",
        "Programming Language :: Python :: 3",
        "Programming Language :: C",
        "Programming Language :: C++",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
