import pip

try:
    from setuptools import setup, find_packages
except ImportError:
    from distutils.core import setup, find_packages

with open('requirements.txt') as f:
    requires = f.read().splitlines()

setup(
    name="Dionysia-Tools",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=requires,
    # package_data={
    #     # If any package contains *.txt or *.rst files, include them:
    #     '': ['*.txt', '*.rst'],
    #     # And include any *.msg files found in the 'hello' package, too:
    #     'hello': ['*.msg'],
    # },

    # metadata to display on PyPI
    author="ewascome",
    description="Tools for Plex Server",
    keywords="radarr plex Trakt",
    url="https://github.com/ewascome/Dionysia-Tools",   # project home page, if any
    project_urls={
        "Bug Tracker": "https://github.com/ewascome/Dionysia-Tools/issues",
        # "Documentation": "https://docs.example.com/HelloWorld/",
    },
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],
    entry_points={
        'console_scripts': [
            'dionysia-tools = dionysia_tools.dionysia_tools:app',
        ]
    },
)
