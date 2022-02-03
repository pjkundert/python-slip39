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
    'slip39-recovery	= slip39.recovery.main:main',
    'slip39-generator	= slip39.generator.main:main',
    'slip39-gui		= slip39.gui.main:main',
]

entry_points			= {
    'console_scripts': 		console_scripts,
}

install_requires		= open( os.path.join( HERE, "requirements.txt" )).readlines()
tests_require			= open( os.path.join( HERE, "requirements-tests.txt" )).readlines()
extras_require			= {
    option: open( os.path.join( HERE, f"requirements-{option}.txt" )).readlines()
    for option in [
        'serial',	# slip39[serial]: Support serial I/O of generated wallet data
        'json',		# slip39[json]:   Support output of encrypted Ethereum JSON wallets
        'gui',		# slip39[gui]:    Support PySimpleGUI/tkinter Graphical UI App
    ]
}

package_dir			= {
    "slip39":			"./slip39",
    "slip39.recovery":		"./slip39/recovery",
    "slip39.generator":		"./slip39/generator",
    "slip39.gui":		"./slip39/gui",
}

long_description_content_type	= 'text/markdown'
long_description		= """\
Creating Ethereum, Bitcoin and other accounts is complex and fraught with potential for loss of funds.

A BIP-39 seed recovery phrase helps, but a *single* lapse in security dooms the account (and all
derived accounts, in fact).  If someone finds your recovery phrase (or you lose it), the accounts
derived from that seed are /gone/.

The SLIP-39 standard allows you to split the seed between 1, 2, or more groups of several mnemonic
recovery phrases.  This is better, but creating such accounts is difficult; presently, only the
Trezor supports these, and they can only be created "manually".  Writing down 5 or more sets of 20
words is difficult, error-prone and time consuming.

The python-slip39 project exists to assist in the safe creation and documentation of Ethereum HD
Wallet seeds and derived accounts, with various SLIP-39 sharing parameters.  It generates the new
random wallet seed, and generates the expected standard Ethereum account(s) (at derivation path
=m/44'/60'/0'/0/0= by default) and Bitcoin accounts (at Bech32 derivation path =m/84'/0'/0'/0/0= by
default), with wallet address and QR codee (compatible with Trezor derivations).  It produces the
required SLIP-39 phrases, and outputs a single PDF containing all the required printable cards to
document the seed (and the specified derived accounts).

On an secure (ideally air-gapped) computer, new seeds can safely be generated and the PDF saved to a
USB drive for printing (or directly printed without the file being saved to disk.).  Presently,
=slip39= can output example ETH, BTC, LTC and DOGE addresses derived from the seed, to illustrate
what accounts are associated with the backed-up seed.  Recovery of the seed to a Trezor is simple,
by entering the mnemonics right on the device.

    $ python3 -m slip39 -v Personal      # or run: slip39 -v Personal
    2022-01-26 13:55:30 slip39           First(1/1): Recover w/ 2 of 4 groups First(1), Second(1), Fam(2/4), Frens(2/6)
    2022-01-26 13:55:30 slip39           1st  1 sister     8 cricket   15 unhappy
    2022-01-26 13:55:30 slip39                2 acid       9 mental    16 ocean
    2022-01-26 13:55:30 slip39                3 acrobat   10 veteran   17 mayor
    2022-01-26 13:55:30 slip39                4 romp      11 phantom   18 promise
    2022-01-26 13:55:30 slip39                5 anxiety   12 grownup   19 wrote
    2022-01-26 13:55:30 slip39                6 laser     13 skunk     20 romp
    2022-01-26 13:55:30 slip39                7 cricket   14 anatomy
    2022-01-26 13:55:30 slip39           Second(1/1): Recover w/ 2 of 4 groups First(1), Second(1), Fam(2/4), Frens(2/6)
    2022-01-26 13:55:30 slip39           1st  1 sister     8 belong    15 spirit
    2022-01-26 13:55:30 slip39                2 acid       9 survive   16 royal
    2022-01-26 13:55:30 slip39                3 beard     10 home      17 often
    2022-01-26 13:55:30 slip39                4 romp      11 herd      18 silver
    2022-01-26 13:55:30 slip39                5 again     12 mountain  19 grocery
    2022-01-26 13:55:30 slip39                6 orbit     13 august    20 antenna
    2022-01-26 13:55:30 slip39                7 very      14 evening
    2022-01-26 13:55:30 slip39           Fam(2/4): Recover w/ 2 of 4 groups First(1), Second(1), Fam(2/4), Frens(2/6)
    2022-01-26 13:55:30 slip39           1st  1 sister     8 rainbow   15 husky
    2022-01-26 13:55:30 slip39                2 acid       9 swing     16 crowd
    2022-01-26 13:55:30 slip39                3 ceramic   10 credit    17 learn
    2022-01-26 13:55:30 slip39                4 roster    11 piece     18 priority
    2022-01-26 13:55:30 slip39                5 already   12 puny      19 hand
    2022-01-26 13:55:30 slip39                6 quiet     13 senior    20 watch
    2022-01-26 13:55:30 slip39                7 erode     14 listen
    2022-01-26 13:55:30 slip39           2nd  1 sister     8 holy      15 revenue
    2022-01-26 13:55:30 slip39                2 acid       9 execute   16 junction
    2022-01-26 13:55:30 slip39                3 ceramic   10 lift      17 elite
    2022-01-26 13:55:30 slip39                4 scared    11 spark     18 flexible
    2022-01-26 13:55:30 slip39                5 domestic  12 yoga      19 inform
    2022-01-26 13:55:30 slip39                6 exact     13 medical   20 predator
    2022-01-26 13:55:30 slip39                7 finger    14 grief
    ...
    2022-01-26 13:55:30 slip39           ETH    m/44'/60'/0'/0/0    : 0x8FBCe53111817DcE01F9f4C4A6319eA1Ca0c3bf1
    2022-01-26 13:55:30 slip39           BTC    m/84'/0'/0'/0/0     : bc1q6u7qk0tepkxdm8wkhpqzwwy0w8zfls9yvghaxq
    ...
    2022-01-26 13:55:30 slip39           Wrote SLIP39-encoded wallet for 'Personal' to: Personal-2022-01-26+13.55.30-ETH-0x8FBCe53111817DcE01F9f4C4A6319eA1Ca0c3bf1.pdf

Later, if you need to recover the Ethereum wallet, keep entering SLIP-39 mnemonics until the secret
is recovered (invalid/duplicate mnemonics will be ignored):

    $ python3 -m slip39.recovery -v      # or run: slip39-recovery -v
    Enter 1st SLIP-39 mnemonic: sister acid acrobat romp anxiety laser cricket cricket mental veteran phantom grownup skunk anatomy unhappy ocean mayor promise wrote romp
    2021-12-29 13:24:25 slip39.recovery  Could not recover SLIP-39 master secret with 1 supplied mnemonics: Insufficient number of mnemonic groups. The required number of groups is 2.
    Enter 2nd SLIP-39 mnemonic: a bc
    2021-12-29 13:24:53 slip39.recovery  Could not recover SLIP-39 master secret with 2 supplied mnemonics: Invalid mnemonic word 'a'.
    Enter 3rd SLIP-39 mnemonic: sister acid ceramic roster already quiet erode rainbow swing credit piece puny senior listen husky crowd learn priority hand watch
    2021-12-29 13:24:58 slip39.recovery  Could not recover SLIP-39 master secret with 3 supplied mnemonics: Invalid mnemonic word 'a'.
    Enter 4th SLIP-39 mnemonic: sister acid ceramic scared domestic exact finger holy execute lift spark yoga medical grief revenue junction elite flexible inform predator
    2021-12-29 13:25:14 slip39.recovery  Recovered SLIP-39 secret with 3 (1st, 3rd, 4th) of 4 supplied mnemonics
    2021-12-29 13:25:14 slip39.recovery  Recovered SLIP-39 secret; To re-generate, send it to: python3 -m slip39 --secret -
    32448aabb50cb6b022fdf17d960720df

Finally, regenerate the Ethereum wallet, perhaps including an encrypted JSON wallet file for import
into a software wallet; note that the same Ethereum wallet address 0x8FBC...3bf1 is recovered:

    $ python3 -m slip39 --secret 32448aabb50cb6b022fdf17d960720df --json -
    2022-01-26 14:06:14 slip39           It is recommended to not use '-s|--secret <hex>'; specify '-' to read from input
    2022-01-26 14:06:14 slip39           ETH    m/44'/60'/0'/0/0    : 0x8FBCe53111817DcE01F9f4C4A6319eA1Ca0c3bf1
    2022-01-26 14:06:14 slip39           BTC    m/84'/0'/0'/0/0     : bc1q6u7qk0tepkxdm8wkhpqzwwy0w8zfls9yvghaxq
    JSON key file password:
    2022-01-26 14:06:21 slip39           Wrote JSON SLIP39's encrypted ETH wallet 0x8FBCe53111817DcE01F9f4C4A6319eA1Ca0c3bf1 \
                                                derived at m/44'/60'/0'/0/0 to: SLIP39-2022-01-26+14.06.14-ETH-0x8FBCe53111817DcE01F9f4C4A6319eA1Ca0c3bf1.json
    2022-01-26 14:06:21 slip39           Wrote SLIP39-encoded wallet for '' to: SLIP39-2022-01-26+14.06.14-ETH-0x8FBCe53111817DcE01F9f4C4A6319eA1Ca0c3bf1.pdf


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

'''
# For py2{app,exe} App Generation.  TODO: Does not work; use PyInstaller instead
mainscript			= "SLIP39.py"

if sys.platform == 'darwin':
    extra_options		= dict(
        setup_requires	= [ 'py2app' ],
        app		= [ mainscript ],
        # Cross-platform applications generally expect sys.argv to
        # be used for opening files.
        # Don't use this with GUI toolkits, the argv
        # emulator causes problems and toolkits generally have
        # hooks for responding to file-open events.
        options		= dict(
            py2app	= dict(
                argv_emulation	= True,
                iconfile	= 'images/SLIP39.icns',
                includes	= 'tkinter',
            ),
        ),
    )
elif sys.platform == 'win32':
    extra_options		= dict(
        setup_requires	= [ 'py2exe' ],
        app		= [ mainscript ],
    )
else:
    extra_options		= dict(
        # Normally unix-like platforms will use "setup.py install"
        # and install the main script as such
        scripts		= [ mainscript ],
    )
'''

setup(
    name			= "slip39",
    version			= __version__,
    install_requires		= install_requires,
    tests_require		= tests_require,
    extras_require		= extras_require,
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
    python_requires		= ">=3.9",
    #**extra_options
)
