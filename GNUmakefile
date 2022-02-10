#
# GNU 'make' file
# 

# Change to your own Apple Developer ID, if you want to code-sign the resultant .app
APPLEID		?= perry@kundert.ca
TEAMID		?= ZD8TVTCXDS
#DEVID		?= 3rd Party Mac Developer Application: Perry Kundert ($(TEAMID))
DEVID		?= Developer ID Application: Perry Kundert ($(TEAMID))
PKGID		?= 3rd Party Mac Developer Installer: Perry Kundert ($(TEAMID))
BUNDLEID	?= ca.kundert.perry.SLIP39
APIISSUER	?= 5f3b4519-83ae-4e01-8d31-f7db26f68290
APIKEY		?= 5H98J7LKPC

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

# Building a macOS App


app:			dist/SLIP39.app

app-upload:		dist/SLIP39-$(VERSION).dmg.uploaded


# Generate, Sign and Package the macOS SLIP39.app GUI for App Store or local/manual installation
app-dmg:		dist/SLIP39-$(VERSION).dmg
app-zip:		dist/SLIP39-$(VERSION).zip
app-pkg:		dist/SLIP39-$(VERSION).pkg


# 
# Build the macOS App, and create and sign the .dmg file
# 
# o Uses https://github.com/sindresorhus/create-dmg
#   - npm install --global create-dmg
#   - Renames the resultant file from "SLIP39 1.2.3.dmg" to "SLIP39-1.2.3.dmg"
#   - It automatically finds the correct signing key (unkown)
# 
dist/SLIP39-$(VERSION).dmg:	dist/SLIP39.app
	@echo "\n\n*** Creating and signing DMG $@..."
	npx create-dmg --overwrite $<
	mv "SLIP39 $(VERSION).dmg" "$@"
	@echo "Checking signature..."; ./SLIP39.metadata/check-signature $@

# Upload the .dmg, unless we've already uploaded it and have a RequestUUID
dist/SLIP39-$(VERSION).dmg.notarization: dist/SLIP39-$(VERSION).dmg
	jq -r '.["notarization-upload"]["RequestUUID"]' $@ 2>/dev/null \
	|| xcrun altool --notarize-app -f $< \
	    --primary-bundle-id $(BUNDLEID) \
	    --team-id $(TEAMID) \
	    --apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
	    --output-format json \
		> $@

# Refresh the ...dmg.notariation-status, unless it is already "Status: success"
dist/SLIP39-$(VERSION).dmg.notarization-status: dist/SLIP39-$(VERSION).dmg.notarization FORCE
	[ -s $@ ] && grep "Status: success" $@ \
	    || xcrun altool \
		--apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
		--notarization-info $$( jq -r '.["notarization-upload"]["RequestUUID"]' $< ) \
		    | tee -a $@

# Check notarization status 'til Status: success, then staple it to ...dmg, and create ...dmg.final marker file
dist/SLIP39-$(VERSION).dmg.valid: dist/SLIP39-$(VERSION).dmg.notarization-status FORCE
	grep "Status: success" $< || \
	    ( tail -10 $<; echo "\n\n!!! App not yet notarized; cannot produce $@"; false )
	( [ -r $@ ] ) \
	    && ( echo "\n\n*** Notarization complete; refreshing $@" && touch $@ ) \
	    || ( \
		xcrun stapler staple   dist/SLIP39-$(VERSION).dmg && \
		xcrun stapler validate dist/SLIP39-$(VERSION).dmg && \
	        echo "\n\n*** Notarization attached to $@" && \
		touch $@ \
	    )

# macOS ...dmg App Upload: Unless the ...dmg.upload file exists and is non-empty
dist/SLIP39-$(VERSION).dmg.uploaded: dist/SLIP39-$(VERSION).dmg dist/SLIP39-$(VERSION).dmg.valid FORCE
	[ -s $@ ] || ( \
	    echo "\n\n*** Uploading the signed DMG file: $<..." && \
	    echo "*** Verifying notarization stapling..." && xcrun stapler validate $< && \
	    echo "*** Checking signature..." && ./SLIP39.metadata/check-signature $< && \
	    echo "*** Upload starting for $<..." && \
	    xcrun altool --upload-package $< \
		--type macos \
		--bundle-id $(BUNDLEID) --bundle-version $(VERSION) --bundle-short-version-string $(VERSION) \
		--apple-id $(APPLEID) --team $(TEAMID) \
		--apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
		    | tee -a $@ \
	)

# 
# Create the .pkg, ensuring that the App was created and signed appropriately
# o Sign this w/ the ...Developer ID?
#   - Nope: "...An installer signing identity (not an application signing identity) is required for signing flat-style products."
# See: https://lessons.livecode.com/m/4071/l/876834-signing-and-uploading-apps-to-the-mac-app-store
# o Need ... --product <path-to-app-bundle-Info.plist>
# 
dist/SLIP39-$(VERSION).pkg:	dist/SLIP39.app		\
				dist/SLIP39.app-signed
	productbuild --sign "$(PKGID)" --timestamp \
	    --identifier "$(BUNDLEID).pkg" \
	    --version $(VERSION) \
	    --component $< /Applications \
	    $@
	xcrun altool --validate-app -f $@ -t osx --apiKey $(APIKEY) --apiIssuer $(APIISSUER)

dist/SLIP39.pkg:		dist/SLIP39.app # dist/SLIP39.app-signed
	@echo "Checking signature..."; ./SLIP39.metadata/check-signature $<
	productbuild --sign "$(PKGID)" --timestamp \
	    --identifier "$(BUNDLEID).pkg" \
	    --version $(VERSION) \
	    --component $< /Applications \
	    $@
	xcrun altool --validate-app -f $@ -t osx --apiKey $(APIKEY) --apiIssuer $(APIISSUER)

.PHONY: dist/SLIP39.pkg-verify
dist/SLIP39.pkg-verify: dist/SLIP39.pkg
	@echo "\n\n*** Verifying signing of $<..."
	#codesign --verify -v $< \
	#    || ( echo "!!! Unable to verify codesign: "; codesign --verify -vv $<; false )
	spctl --assess --type install --context context:primary-signature -vvv $< || \
	spctl --assess --type execute --context context:primary-signature -vvv $< || \
	spctl --assess --type open    --context context:primary-signature -vvv $< || \
	spctl --assess --type install  -vvv $< || \
	spctl --assess --type execute  -vvv $< || \
	spctl --assess --type open     -vvv $<


# 
# Sign the pkg with the Installer ID, if not already done.
#  
# o doesn't work -- notarization complains:  "The binary is not signed with a valid Developer ID certificate."
# 
dist/SLIP39-signed.pkg:  dist/SLIP39.pkg FORCE
	@echo "\n\n*** Signing $<..."
	productsign --timestamp --sign "$(PKGID)" $< $@


#
# macOS Package Notarization
# See: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution/resolving_common_notarization_issues
# See: https://oozou.com/blog/scripting-notarization-for-macos-app-distribution-38
# o The .pkg version doesn't work due to incorrect signing keys for the .pkg (unknown reason)
# o The .zip version works, but the notarization cannot be stapled to the zip;
#   - We have to receive notification that the SLIP39.zip.notarization-status Status: success
#   - Then, re-package the zip and 
dist/SLIP39.pkg.notarization: dist/SLIP39.pkg
	jq -r '.["notarization-upload"]["RequestUUID"]' $@ 2>/dev/null \
	|| xcrun altool --notarize-app -f $< \
	    --primary-bundle-id $(BUNDLEID) \
	    --team-id $(TEAMID) \
	    --apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
	    --output-format json \
		> $@

dist/SLIP39.pkg.notarization-status:  dist/SLIP39.pkg.notarization FORCE
	xcrun altool \
	    --apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
	    --notarization-info $$( jq -r '.["notarization-upload"]["RequestUUID"]' $< ) \
		| tee -a $@

dist/SLIP39.zip.notarization: dist/SLIP39.zip
	jq -r '.["notarization-upload"]["RequestUUID"]' $@ 2>/dev/null \
	|| xcrun altool --notarize-app -f $< \
	    --primary-bundle-id $(BUNDLEID) \
	    --team-id $(TEAMID) \
	    --apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
	    --output-format json \
		> $@

dist/SLIP39.zip.notarization-status:  dist/SLIP39.zip.notarization FORCE

	xcrun altool \
	    --apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
	    --notarization-info $$( jq -r '.["notarization-upload"]["RequestUUID"]' $< ) \
		| tee -a $@

dist/SLIP39-$(VERSION)-final.zip: dist/SLIP39.zip.notarization-status
	grep "Status: success" $< || \
	    ( tail -10 $<; echo "\n\n!!! App not yet notarized; cannot produce $@"; false )
	( [ -r $@ ] ) \
	    && ( echo "\n\n*** Notarization compete; not re-generating $@"; true ) \
	    || ( \
		xcrun stapler staple   dist/SLIP39.app; \
		xcrun stapler validate dist/SLIP39.app; \
	        echo "\n\n*** Notarization attached; creating $@"; \
		/usr/bin/ditto -c -k --keepParent "dist/SLIP39.app" "$@"; \
		ls -last dist; \
	    )
# 
# macOS App Upload: Unless the ...zip.upload file exists and is non-zero
# 
dist/SLIP39-$(VERSION)-final.zip.upload: dist/SLIP39-$(VERSION)-final.zip FORCE
	[ -s $@ ] || xcrun altool --upload-package $< \
	    --type macos \
	    --bundle-id $(BUNDLEID) --bundle-version $(VERSION) --bundle-short-version-string $(VERSION) \
	    --apple-id $(APPLEID) \
	    --apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
		| tee -a $@
# 
# Package the macOS App as a Zip file for Notarization
# 
# o Create a ZIP archive suitable for notarization.
# 
dist/SLIP39.zip:		dist/SLIP39.app
	echo "Checking signature..."; ./SLIP39.metadata/check-signature $<
	codesign --verify $<
	codesign -dv -r- $<
	codesign -vv $<
	rm -f $@
	/usr/bin/ditto -c -k --keepParent "$<" "$@"
	@ls -last dist


#
# The macOS gui APP 
# 
# Rebuild the gui App; ensure we discard any partial/prior build and gui artifacts The --onefile
# approach doesn't seem to work, as we need to sign things after packaging.  We need to customize
# the SLIP39.spec file (eg. for version), so we do not target SLIP39.py (which would re-generate it
# without our additions)
#
# Additional .spec file configurations:
# - https://developer.apple.com/documentation/bundleresources/information_property_list/lsminimumsystemversion
#
# o The codesign --verify succeeds w/ the '3rd Party Mac Developer Application ...', but not the spctl --assess?
# 
.PHONY: dist/SLIP39.app-signed
dist/SLIP39.app-signed: 	dist/SLIP39.app		\
				dist/SLIP39.app-checkids
	@echo "\n\n*** Verifying codesigning of $<..."
	codesign --verify -v $< \
	    || ( echo "!!! Unable to verify codesign: "; codesign --verify -vv $<; false )
	spctl --assess --type install --context context:primary-signature -vvv $< || \
	spctl --assess --type execute --context context:primary-signature -vvv $< || \
	spctl --assess --type open    --context context:primary-signature -vvv $< || true

.PHONY: dist/SLIP39.app-checkids
dist/SLIP39.app-checkids:	SLIP39.spec
	@echo "\n\n*** Checking Developer/Installer IDs for $(TEAMID) in $<..."
	security find-identity -vp macappstore
	security find-identity -vp macappstore | grep "$(DEVID)" \
	    || ( echo "!!! Unable to find Developer ID for signing: $(DEVID)"; false )
	security find-identity -vp macappstore | grep "$(PKGID)" \
	    || ( echo "!!! Unable to find Installer ID for signing: $(PKGID)"; false )

# Not necessary?
# 	    --options=runtime --timestamp
# 
# For details on Signing Apps:
# See: https://developer.apple.com/library/archive/technotes/tn2318/_index.html

# * In order for code signing to succeed, your code signing key(s) MUST have all of their dependent
#   (issuer) keys downloaded to your Keychain, from https://www.apple.com/certificateauthority.
#   - Use Keychain Access, right-click on your signing key and click Evaluate "...".
#   - Find each dependent key, and look at its SHA fingerprint, and then see if you have
#     that one in your System keychain, downloading all the named keys from apple 'til
#     you find the one with the matching fingerprint.  Grr...  Repeat 'til check-signature works.
dist/SLIP39.app: 		SLIP39.spec		\
				SLIP39.metadata/entitlements.plist \
				images/SLIP39.icns
	@echo "\n\n*** Rebuilding $@, version $(VERSION)..."
	rm -rf build $@*
	sed -I "" -E "s/version=.*/version='$(VERSION)',/" $<
	sed -I "" -E "s/'CFBundleVersion':.*/'CFBundleVersion':'$(VERSION)',/" $<
	sed -I "" -E "s/codesign_identity=.*/codesign_identity='$(DEVID)',/" $<
	pyinstaller --noconfirm $<
	echo "Checking signature (pyinstaller signed)..."; ./SLIP39.metadata/check-signature $@ || true
	codesign --verify $@
	# codesign --deep --force \
	#     --all-architectures --options=runtime --timestamp \
	#     --sign "$(DEVID)" \
	#     $@
	# echo "Checking signature (app code signed)..."; ./SLIP39.metadata/check-signature $@ || true
	# codesign --verify $@
	# codesign --deep --force \
	#     --all-architectures --options=runtime --timestamp \
	#     --entitlements ./SLIP39.metadata/entitlements.plist \
	#     --sign "$(DEVID)" \
	#     $@
	# echo "Checking signature (app code + entitlements signed w/ $(DEVID))..."; ./SLIP39.metadata/check-signature $@ || true
	# codesign --verify $@
	touch $@  # try to avoid unnecessary rebuilding

#
# Only used for initial creation of SLIP39.spec; it must be customized, so this target cannot be
# used to achieve a complete, operational SLIP39.spec file!
#
# Roughly, change:
# 
#     app = BUNDLE(coll,
#                  name='SLIP39.app',
#    -             icon=None,
#    +             icon='images/SLIP39.icns',
#    +             version='6.4.1',
#    +             info_plist={
#    +                 'CFBundleVersion':'6.4.1',
#    +                 'LSApplicationCategoryType':'public.app-category.utilities',
#    +                 'LSMinimumSystemVersion':'10.15.0',
#    +             })
#    +
#                 bundle_identifier='ca.kundert.perry.SLIP39')

SLIP39.spec: SLIP39.py
	@echo "\n\n!!! Rebuilding $@; Must be manually edited..."
	pyinstaller --noconfirm --windowed \
	    --codesign-identity "$(DEVID)" \
	    --osx-bundle-identifier "$(BUNDLEID)" \
	    --osx-entitlements-file ./SLIP39.metadata/entitlements.plist \
	    --collect-data shamir_mnemonic \
		$<
	false

# 
# macOS Icons
# 
# Requires a source images/SLIP39.png at least 1024x1024
# 
# See: https://stackoverflow.com/questions/12306223/how-to-manually-create-icns-files-using-iconutil
#
images/SLIP39.icns: images/SLIP39.iconset 
	iconutil --convert icns -o $@ $<

images/SLIP39.iconset: images/SLIP39.png
	rm -rf $@
	mkdir $@
	sips -z   16   16 $< --out $@/icon_16x16.png
	sips -z   32   32 $< --out $@/icon_16x16@2x.png
	sips -z   32   32 $< --out $@/icon_32x32.png
	sips -z   64   64 $< --out $@/icon_32x32@2x.png
	sips -z  128  128 $< --out $@/icon_128x128.png
	sips -z  256  256 $< --out $@/icon_128x128@2x.png
	sips -z  256  256 $< --out $@/icon_256x256.png
	sips -z  512  512 $< --out $@/icon_256x256@2x.png
	sips -z  512  512 $< --out $@/icon_512x512.png
	sips -z 1024 1024 $< --out $@/icon_512x512@2x.png


#
# Pypi pip packaging
# 
# Support uploading a new version of slip32 to pypi.  Must:
#   o advance __version__ number in slip32/version.py
#   o log in to your pypi account (ie. for package maintainer only)
#
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
