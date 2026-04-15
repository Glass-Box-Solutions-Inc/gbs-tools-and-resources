from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-meruscase",
    version="1.0.0",
    description="Agent-native CLI for MerusCase — California Workers' Compensation case management",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
        "httpx>=0.27.0",
        # playwright is used for case creation via Browserless (cloud browser).
        # No local `playwright install chromium` is needed — Browserless provides
        # the browser remotely. The playwright Python package is still required
        # for the async_playwright + connect_over_cdp API.
        "playwright>=1.40.0",
        "google-cloud-secret-manager>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-meruscase=cli_anything.meruscase.meruscase_cli:main",
        ],
    },
    python_requires=">=3.10",
)
