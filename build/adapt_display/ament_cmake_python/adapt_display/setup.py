from setuptools import find_packages
from setuptools import setup

setup(
    name='adapt_display',
    version='0.0.0',
    packages=find_packages(
        include=('adapt_display', 'adapt_display.*')),
)
