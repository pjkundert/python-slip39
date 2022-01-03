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
    'slip39-recovery	= slip39.recovery.__main__:main',
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

long_description_content_type	= 'text/markdown'
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
generates standard Ethereum account(s) (at derivation path =m/44'/60'/0'/0/0= by default) with
Ethereum wallet address and QR code, produces the required SLIP-39 phrases, and outputs a single PDF
containing all the required printable cards to document the account.

On an secure (ideally air-gapped) computer, new accounts can safely be generated and the PDF saved
to a USB drive for printing (or directly printed without the file being saved to disk.)

    $ python3 -m slip39 -v
    2021-12-29 13:21:57 slip39           ETH m/44'/60'/0'/0/0    : 0x8686D2cb685A934233eB8a4907d17e45257eBaD0
    ...
    2021-12-29 13:21:57 slip39           First(1/1): Recover w/ 2 of 4 groups First(1), Second(1), Fam(2/4), Fren(2/6)
    2021-12-29 13:21:57 slip39             withdraw pajamas acrobat romp afraid engage sniff olympic rescue taxi careful calcium radar thank realize join thank parcel desktop tofu
    2021-12-29 13:21:57 slip39           Second(1/1): Recover w/ 2 of 4 groups First(1), Second(1), Fam(2/4), Fren(2/6)
    2021-12-29 13:21:57 slip39             withdraw pajamas beard romp ajar cricket medical human unkind undergo legend briefing climate learn member change glasses maximum critical photo
    2021-12-29 13:21:57 slip39           Fam(2/4): Recover w/ 2 of 4 groups First(1), Second(1), Fam(2/4), Fren(2/6)
    2021-12-29 13:21:57 slip39             withdraw pajamas ceramic roster daisy voice bike spider rhyme stay slow devote phantom cricket carpet favorite decent society ending elite
    2021-12-29 13:21:57 slip39             withdraw pajamas ceramic scared calcium says spew fake blue exceed actress velvet romp ounce mild smear sled kernel divorce oral
    ...
    2021-12-29 13:21:57 slip39           Wrote SLIP39-encoded wallet for '' to: SLIP39-2021-12-29+13.21.57-0x8686D2cb685A934233eB8a4907d17e45257eBaD0.pdf

Later, if you need to recover the Ethereum wallet, keep entering SLIP-39 mnemonics until the secret
is recovered (invalid/duplicate mnemonics will be ignored):

    $ python3 -m slip39.recovery -v
    Enter 1st SLIP-39 mnemonic: withdraw pajamas acrobat romp afraid engage sniff olympic rescue taxi careful calcium radar thank realize join thank parcel desktop tofu
    2021-12-29 13:24:25 slip39.recovery  Could not recover SLIP-39 master secret with 1 supplied mnemonics: Insufficient number of mnemonic groups. The required number of groups is 2.
    Enter 2nd SLIP-39 mnemonic: a bc
    2021-12-29 13:24:53 slip39.recovery  Could not recover SLIP-39 master secret with 2 supplied mnemonics: Invalid mnemonic word 'a'.
    Enter 3rd SLIP-39 mnemonic:  withdraw pajamas ceramic roster daisy voice bike spider rhyme stay slow devote phantom cricket carpet favorite decent society ending elite
    2021-12-29 13:24:58 slip39.recovery  Could not recover SLIP-39 master secret with 3 supplied mnemonics: Invalid mnemonic word 'a'.
    Enter 4th SLIP-39 mnemonic: withdraw pajamas ceramic scared calcium says spew fake blue exceed actress velvet romp ounce mild smear sled kernel divorce oral
    2021-12-29 13:25:14 slip39.recovery  Recovered SLIP-39 secret with 3 (1st, 3rd, 4th) of 4 supplied mnemonics
    2021-12-29 13:25:14 slip39.recovery  Recovered SLIP-39 secret; To re-generate, send it to: python3 -m slip39 --secret -
    9658a84b5138f63c428f6086be6e82b5

Finally, regenerate the Ethereum wallet, perhaps including an encrypted JSON wallet file for import
into a software wallet; note that the same Ethereum wallet address 0x8686...BaD0 is recovered:

    $ python3 -m slip39 --secret 9658a84b5138f63c428f6086be6e82b5 --json -
    2021-12-29 13:26:04 slip39           It is recommended to not use '-s|--secret <hex>'; specify '-' to read from input
    2021-12-29 13:26:04 slip39           ETH m/44'/60'/0'/0/0    : 0x8686D2cb685A934233eB8a4907d17e45257eBaD0
    JSON key file password: <enter JSON wallet password>
    2021-12-29 13:26:29 slip39           Wrote JSON encrypted wallet for '' to: SLIP39-2021-12-29+13.26.04-0x8686D2cb685A934233eB8a4907d17e45257eBaD0.json
    2021-12-29 13:26:29 slip39           Wrote SLIP39-encoded wallet for '' to: SLIP39-2021-12-29+13.26.04-0x8686D2cb685A934233eB8a4907d17e45257eBaD0.pdf

The whole toolchain is suitable for pipelining:

    $ python3 -m slip39 --text --no-card -q \\
        | sort -r \\
        | python3 -m slip39.recovery \\
        | python3 -m slip39 --secret - --no-card -q
    2021-12-28 10:55:17 slip39           ETH m/44'/60'/0'/0/0    : 0x68dD9B59D5dF605f4e9612E8b427Ab31187E2C54
    2021-12-28 10:55:18 slip39.recovery  Recovered SLIP-39 secret with 4 (1st, 2nd, 7th, 8th) of 8 supplied mnemonics
    2021-12-28 10:55:18 slip39           ETH m/44'/60'/0'/0/0    : 0x68dD9B59D5dF605f4e9612E8b427Ab31187E2C54

Here's an example of PDF containing the SLIP-39 recovery mnemonic cards produced:

![slip39 mnemonic cards][slip39-pdf]

[slip39-pdf]: https://github.com/pjkundert/python-slip39/raw/master/images/slip39-pdf.png "slip39 mnemonic cards PDF"
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
    long_description_content_type = long_description_content_type,
    license			= "Dual License; GPLv3 and Proprietary",
    keywords			= "Ethereum cryptocurrency SLIP39 BIP39 seed recovery",
    url				= "https://github.com/pjkundert/python-slip39",
    classifiers			= classifiers,
    python_requires		= ">=3.6",
)
