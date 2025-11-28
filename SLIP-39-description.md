Creating Ethereum, Bitcoin and other accounts is complex and fraught
with potential for loss of funds.

A BIP-39 seed recovery phrase helps, but a *single* lapse in security
dooms the account (and all derived accounts, in fact).  If someone finds
your recovery phrase (or you lose it), the accounts derived from that
seed are /gone/.

The SLIP-39 standard allows you to split the seed between 1, 2, or more
groups of several mnemonic recovery phrases.  This is better, but
creating such accounts is difficult; presently, only the Trezor supports
these, and they can only be created "manually".  Writing down 5 or more
sets of 20 words is difficult, error-prone and time consuming.

# Hardware Wallet "Seed" Configuration

>  Your keys, your Bitcoin.  Not your keys, not your Bitcoin.
>  
>  ---Andreas Antonopoulos

The [python-slip39] project (and the [SLIP-39 macOS/win32 App]) exists
to assist in the safe creation, backup and documentation of
[Hierarchical Deterministic (HD) Wallet] seeds and derived accounts,
with various SLIP-39 sharing parameters.  It generates the new random
wallet seed, and generates the expected standard Ethereum account(s)
(at [derivation path] *m/44'/60'/0'/0/0* by default) and Bitcoin
accounts (at Bech32 derivation path *m/84'/0'/0'/0/0* by default),
with wallet address and QR code (compatible with Trezor and Ledger
derivations).  It produces the required SLIP-39 phrases, and outputs a
single PDF containing all the required printable cards to document the
seed (and the specified derived accounts).

On an secure (ideally air-gapped) computer, new seeds can /safely/ be
generated (*without trusting this program*) and the PDF saved to a USB
drive for printing (or directly printed without the file being saved
to disk.).  Presently, `slip39' can output example ETH, BTC, LTC,
DOGE, BNB, and XRP addresses derived from the seed, to /illustrate/
what accounts are associated with the backed-up seed.  Recovery of the
seed to a [Trezor Safe 3] is simple, by entering the mnemonics right
on the device.

We also support the backup of existing insecure and unreliable 12- or
24-word BIP-39 Mnemonic Phrases as SLIP-39 Mnemonic cards, for
existing BIP-39 hardware wallets like the [Ledger Nano], etc.!
Recover from your existing BIP-39 Seed Phrase Mnemonic, select "Using
BIP-39" (and enter your BIP-39 passphrase), and generate a set of
SLIP-39 Mnemonic cards.  Later, use the SLIP-39 App to recover from
your SLIP-39 Mnemonic cards, click "Using BIP-39" to get your BIP-39
Mnemonic back, and use it (and your passphrase) to recover your
accounts to your Ledger (or other) hardware wallet.

Output of BIP-38 or JSON encrypted Paper Wallets is also supported,
for import into standard software cryptocurrency wallets.
