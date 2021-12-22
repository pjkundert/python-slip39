from setuptools import setup

import os
import sys
import glob
import fnmatch

HERE				= os.path.dirname( os.path.abspath( __file__ ))

# Must work if setup.py is run in the source distribution context, or from
# within the packaged distribution directory.
__version__			= None
try:
    exec( open( 'slip39/version.py', 'r' ).read() )
except FileNotFoundError:
    exec( open( 'version.py', 'r' ).read() )

console_scripts			= [
    'slip39		= slip39.main:main',
]

entry_points			= {
    'console_scripts': 		console_scripts,
}

install_requires		= open( os.path.join( HERE, "requirements.txt" )).readlines()
tests_require			= open( os.path.join( HERE, "requirements-tests.txt" )).readlines()

package_dir			= {
    "slip39":			"./slip39",
}

long_description		= """\
Securing and safely restoring access to cryptocurrency accounts is difficult.

The SLIP39 seed backup format is useful.
"""

classifiers			= [
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
    "License :: Other/Proprietary License",
    "Programming Language :: Python :: 3",
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "Intended Audience :: Financial and Insurance Industry",
    "Environment :: Console",
    "Topic :: Security :: Cryptography",
    "Topic :: Office/Business :: Financial",
]
project_urls			= {
    "Bug Tracker": "https://github.com/pjkundert/python-slip39/issues",
}
setup(
    name			= "slip39",
    version			= __version__,
    tests_require		= tests_require,
    install_requires		= install_requires,
    packages			= package_dir.keys(),
    package_dir			= package_dir,
    zip_safe			= True,
    entry_points		= entry_points,
    author			= "Perry Kundert",
    author_email		= "perry@dominionrnd.com",
    project_urls		= project_urls,
    description			= "The slip39 module implements SLIP39 recovery for Ethereum accounts",
    long_description		= long_description,
    license			= "Dual License; GPLv3 and Proprietary",
    keywords			= "Ethereum cryptocurrency SLIP39 BIP39 seed recovery",
    url				= "https://github.com/pjkundert/python-slip39",
    classifiers			= classifiers,
    python_requires		= ">=3.6",
)
