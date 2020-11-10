import os
from setuptools import setup


def get_requires(filename):
    requirements = []
    with open(filename, "rt") as req_file:
        for line in req_file.read().splitlines():
            if not line.strip().startswith("#"):
                requirements.append(line)
    return requirements


setup(
    name="conan-center-bot",
    version=os.environ.get("CCB_VERSION", "0.0.0"),
    license="GPLv3",
    packages=["ccb"],
    entry_points={
        "console_scripts": [
            "conan-center-bot=ccb.__main__:main",
        ],
    },
    include_package_data=True,
    install_requires=get_requires("requirements.txt"),
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
