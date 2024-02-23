from setuptools import find_packages  # type: ignore
from setuptools import setup

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="css_inliner",
    packages=find_packages(),
    entry_points={"console_scripts": ["css_inliner=css_inliner:main"]},
    install_requires=requirements,
)
