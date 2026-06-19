#!/usr/bin/env python3
"""
setup.py for cli-anything-adjudica-staging
"""

from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-adjudica-staging",
    version="1.0.0",
    author="cli-anything contributors",
    author_email="",
    description="CLI harness for Adjudica - Staging E2E Automation via Playwright",
    long_description="CLI harness for Adjudica staging E2E automation and test commands.",
    long_description_content_type="text/markdown",
    url="https://github.com/HKUDS/CLI-Anything",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-adjudica-staging=cli_anything.adjudica_staging.adjudica_cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
