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
Creating Ethereum accounts is complex and fraught with potential for loss of funds.

A BIP-39 seed recovery phrase helps, but a *single* lapse in security dooms the account.  If someone
finds your recovery phrase, the account is /gone/.

The SLIP-39 standard allows you to split the seed between 1 or more groups of multiple recovery
phrases.  This is better, but creating such accounts is difficult; presently, only the Trezor
supports these, and they can only be created "manually".  Writing down 5 or more sets of 20 words is
difficult and time consuming.

The python-slip39 project exists to assist in the safe creation and documentation of Ethereum HD
Wallet accounts, with various SLIP-39 sharing parameters.  It generates the new wallet seed,
generates standard Ethereum account(s) (at derivation path =m/66'/40'/0'/0/0= by default) with
Ethereum wallet address and QR code, produces the required SLIP-39 phrases, and outputs a single PDF
containing all the required printable cards to document the account.

On an secure (ideally air-gapped) computer, new accounts can safely be generated and the PDF saved
to a USB drive for printing (or directly printed without the file being saved to disk.)
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
