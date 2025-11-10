"""Setup configuration for TraceLab CLI."""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="tracelab-cli",
    version="1.0.0",
    author="TraceLab Team",
    description="Agent-first CLI for TraceLab research repository",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/tracelab/tracelab",
    packages=find_packages(include=["cli", "cli.*"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    install_requires=[
        "click>=8.1.0",
        "httpx>=0.25.0",
        "rich>=13.0.0",
    ],
    entry_points={
        "console_scripts": [
            "tracelab=cli.main:main",
        ],
    },
)

