"""
Setup script for MerusCase Matter Automation Framework
"""

from setuptools import setup, find_packages

setup(
    name="merus-expert",
    version="1.0.0-alpha",
    description="SOC2-compliant automation framework for MerusCase matter creation",
    author="GlassBoxSolutions",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "playwright==1.48.0",
        "pydantic==2.10.0",
        "pydantic-settings==2.7.0",
        "python-dotenv==1.0.1",
        "cryptography==44.0.0",
        "click==8.1.8",
        "Pillow==11.1.0",
    ],
    entry_points={
        'console_scripts': [
            'merus-expert=main:main',
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Legal Industry",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
