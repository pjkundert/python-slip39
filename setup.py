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
    "slip39.recovery":		"./slip39/recovery",
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

    $ python3 -m slip39 -v
    2021-12-25 11:02:20 slip39           ETH(m/44'/60'/0'/0/0): 0xb44A2011A99596671d5952CdC22816089f142FB3
    ...
    2021-12-25 11:02:20 slip39           First(1/1): Need 2 of First(1), Second(1), Fam(2/4), Fren(3/5) to recover.
    2021-12-25 11:02:20 slip39             valuable discuss acrobat romp apart trust earth brother election bundle finance darkness dryer capacity chubby laundry diet glasses fiction general
    2021-12-25 11:02:20 slip39           Second(1/1): Need 2 of First(1), Second(1), Fam(2/4), Fren(3/5) to recover.
    2021-12-25 11:02:20 slip39             valuable discuss beard romp duckling move space bolt wolf junior cargo disaster desert vintage bulb rhythm dictate timber impact losing
    ...
    2021-12-25 11:02:20 slip39           Wrote SLIP39-encoded wallet for '' to: SLIP39-2021-12-25+11.02.20-0xb44A2011A99596671d5952CdC22816089f142FB3.pdf

Later, if you need to recover the Ethereum wallet, keep entering SLIP-39 mnemonics until the secret
is recovered (invalid/duplicate mnemonics will be ignored):

    $ python3 -m slip39.recovery -v
    Enter 1st SLIP-39 mnemonic: ab c
    Enter 2nd SLIP-39 mnemonic: veteran guilt acrobat romp burden campus purple webcam uncover trend best retailer club income coding round mama critical spill endless
    Enter 3rd SLIP-39 mnemonic: veteran guilt acrobat romp burden campus purple webcam uncover trend best retailer club income coding round mama critical spill endless
    Enter 4th SLIP-39 mnemonic: veteran guilt beard romp dragon island merit burden aluminum worthy editor penalty woman beyond divorce check oasis thumb envy spit
    2021-12-25 11:03:33 slip39.recovery  Recovered SLIP-39 secret; Use:  python3 -m slip39 --secret ...
    383597fd63547e7c9525575decd413f7

Finally, regenerate the Ethereum wallet, perhaps including an encrypted JSON wallet file for import
into a software wallet:

    $ python3 -m slip39 --secret 383597fd63547e7c9525575decd413f7 --json -
    2021-12-25 11:09:57 slip39           ETH(m/44'/60'/0'/0/0): 0xb44A2011A99596671d5952CdC22816089f142FB3
    ...
    JSON key file password: <enter JSON wallet password>
    2021-12-25 11:10:38 slip39           Wrote JSON encrypted wallet for '' to: SLIP39-2021-12-25+11.09.57-0xb44A2011A99596671d5952CdC22816089f142FB3.json
    2021-12-25 11:10:39 slip39           Wrote SLIP39-encoded wallet for '' to: SLIP39-2021-12-25+11.09.57-0xb44A2011A99596671d5952CdC22816089f142FB3.pdf
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
