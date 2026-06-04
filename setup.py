#!/usr/bin/env python
"""Setup script for ai-signal backend."""

from setuptools import setup, find_packages

setup(
    name="ai-signal",
    version="0.1.0",
    description="AI Signal backend service",
    author="AI Signal Team",
    packages=find_packages(include=["pipeline", "pipeline.*"]),
    python_requires=">=3.10",
    install_requires=[
        "flask>=2.3.0",
        "pydantic>=2.8.0",
        "gunicorn>=20.1.0",
    ],
    include_package_data=True,
    zip_safe=False,
)
