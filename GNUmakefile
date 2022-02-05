#
# GNU 'make' file
# 

# Change to your own Apple Developer ID, if you want to code-sign the resultant .app
TEAMID		?= ZD8TVTCXDS
DEVID		?= Developer ID Application: Perry Kundert ($(TEAMID))
PKGID		?= 3rd Party Mac Developer Installer: Perry Kundert ($(TEAMID))
BUNDLEID	?= ca.kundert.perry.SLIP39

# PY[3] is the target Python interpreter.  It must have pytest installed.
PY3		?= python3

VERSION=$(shell $(PY3) -c 'exec(open("slip39/version.py").read()); print( __version__ )')

# To see all pytest output, uncomment --capture=no
PYTESTOPTS	= -vv # --capture=no --log-cli-level=INFO

PY3TEST		= $(PY3) -m pytest $(PYTESTOPTS)

.PHONY: all help test doctest analyze pylint build-check build install upload clean FORCE

all:			help

help:
	@echo "GNUmakefile for cpppo.  Targets:"
	@echo "  help			This help"
	@echo "  test			Run unit tests under Python3"
	@echo "  build			Build dist wheel and app under Python3"
	@echo "  install		Install in /usr/local for Python3"
	@echo "  clean			Remove build artifacts"
	@echo "  upload			Upload new version to pypi (package maintainer only)"

test:
	$(PY3TEST)


analyze:
	flake8 -j 1 --max-line-length=200 \
	  --ignore=W503,E201,E202,E221,E223,E226,E231,E241,E242,E251,E265,E272,E274 \
	  slip39

pylint:
	cd .. && pylint slip39 --disable=W,C,R


build-check:
	@$(PY3) -m build --version \
	    || ( echo "\n*** Missing Python modules; run:\n\n        $(PY3) -m pip install --upgrade pip setuptools wheel build\n" \
	        && false )

build:			clean wheel app

wheel:			dist/slip39-$(VERSION)-py3-none-any.whl

dist/slip39-$(VERSION)-py3-none-any.whl: build-check FORCE
	$(PY3) -m build
	@ls -last dist

# Install from wheel, including all optional extra dependencies
install:		dist/slip39-$(VERSION)-py3-none-any.whl FORCE
	$(PY3) -m pip install --force-reinstall $<[gui,serial,json]


app:			dist/SLIP39.app

# Generate, Sign and Zip the macOS SLIP39.app GUI package for local/manual installation
app-zip:		dist/SLIP39-$(VERSION).app.zip

# Generate, Sign and Pacakage the macOS SLIP39.app GUI package for App Store
app-pkg:		dist/SLIP39-$(VERSION).pkg
app-pkg-signed:		dist/SLIP39-$(VERSION)-signed.pkg

#
# Build a deployable macOS App
#     See: https://gist.github.com/txoof/0636835d3cc65245c6288b2374799c43
#     See: https://wiki.lazarus.freepascal.org/Code_Signing_for_macOS
app-upload:	dist/SLIP39-$(VERSION).app.zip
	xcrun altool --validate-app -f $< -t osx --apiKey 5H98J7LKPC --apiIssuer 5f3b4519-83ae-4e01-8d31-f7db26f68290 \
	&& xcrun altool --upload-app -f $< -t osx --apiKey 5H98J7LKPC --apiIssuer 5f3b4519-83ae-4e01-8d31-f7db26f68290 \

# dist/SLIP39-$(VERSION).pkg: dist/SLIP39.app FORCE
# 	pkgbuild --install-location /Applications --component $< $@

dist/SLIP39-$(VERSION).pkg: dist/SLIP39.app FORCE
	rm -rf   dist/SLIP39-$(VERSION)
	mkdir -p dist/SLIP39-$(VERSION)/Applications
	ditto $< dist/SLIP39-$(VERSION)/Applications/SLIP39.app
	ls -l dist/SLIP39-$(VERSION)/Applications/
	productbuild --identifier "$(BUNDLEID)" --sign "$(PKGID)" --timestamp --root \
	         dist/SLIP39-$(VERSION) $@
	xcrun altool --validate-app -f $@ -t osx --apiKey 5H98J7LKPC --apiIssuer 5f3b4519-83ae-4e01-8d31-f7db26f68290

dist/SLIP39-$(VERSION)-signed.pkg:  dist/SLIP39-$(VERSION).pkg
	productsign --timestamp --sign "$(PKGID)" $< $@
	spctl -vv --assess --type install $@




#(cd dist; zip -r SLIP39.app-$(VERSION).zip SLIP39.app)
# Create a ZIP archive suitable for notarization.
dist/SLIP39-$(VERSION).app.zip: dist/SLIP39.app FORCE
	rm -f $@
	# grep -q "CFBundleVersion" "$</Contents/Info.plist" || sed -i "" -e 's:<dict>:<dict>\n\t<key>CFBundleVersion</key>\n\t<string>0.0.0</string>:' "$</Contents/Info.plist"
	# sed -i "" -e "s:0.0.0:$(VERSION):" "$</Contents/Info.plist"
	# cat $</Contents/Info.plist
	# codesign -dv -r- $<
	# codesign -vv $<
	# codesign --deep --force --options=runtime --timestamp \
	#     --entitlements ./SLIP39.metadata/entitlements.plist \
	#     --sign "$(DEVID)" \
	#     $<
	codesign -dv -r- $<
	codesign -vv $<
	/usr/bin/ditto -c -k --keepParent "$<" "$@"
	@ls -last dist

# Rebuild the gui App; ensure we discard any partial/prior build and gui artifacts
# The --onefile approach doesn't seem to work, as we need to sign things after packaging.
# We need to customize the SLIP39.spec file (eg. for version), so we do not target SLIP39.py
# 
dist/SLIP39.app: SLIP39.spec images/SLIP39.icns
	rm -rf build $@*
	grep "version='$(VERSION)'" $< || sed -i "" -e "s/version='[0-9.]*'/version='$(VERSION)'/" $<
	grep "'CFBundleVersion':'$(VERSION)'" $< || sed -i "" -e "s/'CFBundleVersion:'[0-9.]*'/CFBundleVersion:'$(VERSION)'/" $<
	pyinstaller --noconfirm $<

# Only used for initial creation of SLIP39.spec.  
SLIP39.spec: SLIP39.py
	pyinstaller --noconfirm --windowed \
	    --codesign-identity "$(DEVID)" \
	    --osx-bundle-identifier "$(BUNDLEID)" \
	    --osx-entitlements-file ./SLIP39.metadata/entitlements.plist \
	    --collect-data shamir_mnemonic \
		$<

images/SLIP39.icns: images/SLIP39.iconset
	( cd images && iconutil -c icns SLIP39.iconset )

images/SLIP39.iconset: images/SLIP39.png
	mkdir $@
	sips -z 16 16     $< --out $@/icon_16x16.png
	sips -z 32 32     $< --out $@/icon_16x16@2x.png
	sips -z 32 32     $< --out $@/icon_32x32.png
	sips -z 64 64     $< --out $@/icon_32x32@2x.png
	sips -z 128 128   $< --out $@/icon_128x128.png
	sips -z 256 256   $< --out $@/icon_128x128@2x.png
	sips -z 256 256   $< --out $@/icon_256x256.png
	sips -z 512 512   $< --out $@/icon_256x256@2x.png
	sips -z 512 512   $< --out $@/icon_512x512.png
	cp                $<       $@/icon_512x512@2x.png


# Support uploading a new version of slip32 to pypi.  Must:
#   o advance __version__ number in slip32/version.py
#   o log in to your pypi account (ie. for package maintainer only)

upload-check:
	@$(PY3) -m twine --version \
	    || ( echo "\n*** Missing Python modules; run:\n\n        $(PY3) -m pip install --upgrade twine\n" \
	        && false )
upload: 	upload-check wheel
	python3 -m twine upload --repository pypi dist/slip39-$(VERSION)*

clean:
	@rm -rf MANIFEST *.png build dist auto *.egg-info $(shell find . -name '*.pyc' -o -name '__pycache__' )


# Run only tests with a prefix containing the target string, eg test-blah
test-%:
	$(PY3TEST) *$*_test.py

unit-%:
	$(PY3TEST) -k $*


#
# Target to allow the printing of 'make' variables, eg:
#
#     make print-CXXFLAGS
#
print-%:
	@echo $* = $($*)
	@echo $*\'s origin is $(origin $*)
