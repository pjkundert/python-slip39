#
# GNU 'make' file
# 

# Change to your own Apple Developer ID, if you want to code-sign the resultant .app


APPLEID		?= perry@kundert.ca
TEAMID		?= ZD8TVTCXDS
# The unique App ID assigned by App Store Connect, under App Information (NOT your Apple ID!!)
APPID		?= 1608360813
#DEVID		?= 3rd Party Mac Developer Application: Perry Kundert ($(TEAMID))
DEVID		?= Developer ID Application: Perry Kundert ($(TEAMID))
PKGID		?= 3rd Party Mac Developer Installer: Perry Kundert ($(TEAMID))
#PKGID		?= Developer ID Installer: Perry Kundert ($(TEAMID))
DSTID		?= Apple Distribution: Perry Kundert ($(TEAMID))
BUNDLEID	?= ca.kundert.perry.SLIP39
APIISSUER	?= 5f3b4519-83ae-4e01-8d31-f7db26f68290
APIKEY		?= 5H98J7LKPC

# PY[3] is the target Python interpreter.  It must have pytest installed.
PY3		?= python3

VERSION=$(shell $(PY3) -c 'exec(open("slip39/version.py").read()); print( __version__ )')

# To see all pytest output, uncomment --capture=no
PYTESTOPTS	= -vv # --capture=no --log-cli-level=INFO

PY3TEST		= $(PY3) -m pytest $(PYTESTOPTS)

# VirtualEnv: Build them in ~/src/python-slip39-1.2.3/
LOCAL		?= ~/src/

GHUB_NAME	= python-slip39
GHUB_REPO	= git@github.com:pjkundert/$(GHUB_NAME)
GHUB_BRCH	= -b feature-dmg
VENV_NAME	= $(GHUB_NAME)-$(VERSION)
VENV_OPTS	= # --copies # Doesn't help; still references some system libs.


.PHONY: all help test doctest analyze pylint build-check build install upload clean FORCE

all:			help

help:
	@echo "GNUmakefile for cpppo.  Targets:"
	@echo "  help			This help"
	@echo "  test			Run unit tests under Python3"
	@echo "  clean			Remove build artifacts"
	@echo "  build			Build clean dist wheel and app under Python3"
	@echo "  install		Install in /usr/local for Python3"
	@echo "  upload			Upload new version to pypi (package maintainer only)"
	@echo "  app			Build the macOS SLIP39.app"
	@echo "  app-packages		Build and sign the macOSSLIP39.app, and all App zip, dmg and pkg format packages"

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


# 
# VirtualEnv build, install and activate
#

venv:			$(LOCAL)/$(VENV_NAME)
venv-activate:		$(LOCAL)/$(VENV_NAME)-activate


$(LOCAL)/$(VENV_NAME):
	@echo; echo "*** Building $@ VirtualEnv..."
	@rm -rf $@ && $(PY3) -m venv $(VENV_OPTS) $@ \
	    && cd $@ && git clone $(GHUB_REPO) $(GHUB_BRCH) \
	    && . ./bin/activate && make -C $(GHUB_NAME) install-dev install

# Activate a given VirtualEnv, and go to its python-slip39 installation
# o Creates a custom venv-activate.sh script in the venv, and uses it start
#   start a sub-shell in that venv, with a CWD in the contained python-slip39 installation
$(LOCAL)/$(VENV_NAME)-activate:	$(LOCAL)/$(VENV_NAME)
	@echo; echo "*** Activating $@ VirtualEnv"
	[ -s $</start ] || echo ". $</bin/activate; cd $</$(GHUB_NAME)" > $</venv-activate.sh
	bash --init-file $</venv-activate.sh -i


wheel:			dist/slip39-$(VERSION)-py3-none-any.whl

dist/slip39-$(VERSION)-py3-none-any.whl: build-check FORCE
	$(PY3) -m build
	@ls -last dist

# Install from wheel, including all optional extra dependencies
install-dev:
	$(PY3) -m pip install --upgrade -r requirements-dev.txt

install:		dist/slip39-$(VERSION)-py3-none-any.whl FORCE
	$(PY3) -m pip install --force-reinstall $<[gui,serial,json]

# Building / Signing / Notarizing and Uploading the macOS App
# o TODO: no signed and notarized package yet accepted for upload by macOS App Store
app:			dist/SLIP39.app
app-packages:		app-zip-valid app-dmg-valid app-pkg-valid
app-upload:		app-dmg-upload


# Generate, Sign and Package the macOS SLIP39.app GUI for App Store or local/manual installation
# o Try all the approaches of packaging a macOS App for App Store upload
app-dmg:		dist/SLIP39-$(VERSION).dmg
app-zip:		dist/SLIP39-$(VERSION).zip
app-pkg:		dist/SLIP39-$(VERSION).pkg

app-dmg-valid:		dist/SLIP39-$(VERSION).dmg.valid
app-zip-valid:		dist/SLIP39-$(VERSION).zip.valid
app-pkg-valid:		dist/SLIP39-$(VERSION).pkg.valid

app-dmg-upload:		dist/SLIP39-$(VERSION).dmg.upload-package
app-zip-upload:		dist/SLIP39-$(VERSION).zip.upload-package
app-pkg-upload:		dist/SLIP39-$(VERSION).pkg.upload-package

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

.PHONY: dist/SLIP39-$(VERSION).dmg-verify
dist/SLIP39-$(VERSION).dmg-verify: dist/SLIP39-$(VERSION).dmg
	@echo "\n\n*** Verifying signing of $<..."
	#codesign --verify -v $< \
	#    || ( echo "!!! Unable to verify codesign: "; codesign --verify -vv $<; false )
	spctl --assess --type install --context context:primary-signature -vvv $< || \
	spctl --assess --type execute --context context:primary-signature -vvv $< || \
	spctl --assess --type open    --context context:primary-signature -vvv $< || \
	spctl --assess --type install  -vvv $< || \
	spctl --assess --type execute  -vvv $< || \
	spctl --assess --type open     -vvv $<



# Notarize the .dmg, unless we've already uploaded it and have a RequestUUID
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

# Check notarization status 'til Status: success, then staple it to ...dmg, and create ...dmg.valid marker file
dist/SLIP39-$(VERSION).dmg.valid: dist/SLIP39-$(VERSION).dmg.notarization-status FORCE
	@grep "Status: success" $< || \
	    ( tail -10 $<; echo "\n\n!!! App not yet notarized; try again in a few seconds..."; false )
	( [ -r $@ ] ) \
	    && ( echo "\n\n*** Notarization complete; refreshing $@" && touch $@ ) \
	    || ( \
		xcrun stapler staple   dist/SLIP39-$(VERSION).dmg && \
		xcrun stapler validate dist/SLIP39-$(VERSION).dmg && \
	        echo "\n\n*** Notarization attached to $@" && \
		touch $@ \
	    )

# macOS ...dmg App Upload: Unless the ...dmg.upload file exists and is non-empty.
# o Try either upload-package and upload-app approach
# o NOTE that --apple-id is NOT your "Apple ID", it is the unique App ID
# See: https://github.com/fastlane/fastlane/issues/14783
dist/SLIP39-$(VERSION).dmg.upload-package: dist/SLIP39-$(VERSION).dmg dist/SLIP39-$(VERSION).dmg.valid FORCE
	[ -s $@ ] || ( \
	    echo "\n\n*** Uploading the signed DMG file: $<..." && \
	    echo "*** Verifying notarization stapling..." && xcrun stapler validate $< && \
	    echo "*** Checking signature..." && ./SLIP39.metadata/check-signature $< && \
	    echo "*** Upload starting for $<..." && \
	    xcrun altool --upload-package $< \
		--type macos \
		--bundle-id $(BUNDLEID) --bundle-version $(VERSION) --bundle-short-version-string $(VERSION) \
		--apple-id $(APPID) --team $(TEAMID) \
		--apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
		    | tee -a $@ \
	)

dist/SLIP39-$(VERSION).dmg.upload-app: dist/SLIP39-$(VERSION).dmg dist/SLIP39-$(VERSION).dmg.valid FORCE
	[ -s $@ ] || ( \
	    echo "\n\n*** Uploading the signed DMG file: $<..." && \
	    echo "*** Verifying notarization stapling..." && xcrun stapler validate $< && \
	    echo "*** Checking signature..." && ./SLIP39.metadata/check-signature $< && \
	    echo "*** Upload starting for $<..." && \
	    xcrun altool --upload-app -f $< \
		--type macos \
		--primary-bundle-id $(BUNDLEID) \
		--apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
		    | tee -a $@ \
	)

# 
# Create the .pkg, ensuring that the App was created and signed appropriately
# o Sign this w/ the ...Developer ID?
#   - Nope: "...An installer signing identity (not an application signing identity) is required for signing flat-style products."
# See: https://lessons.livecode.com/m/4071/l/876834-signing-and-uploading-apps-to-the-mac-app-store
# o Need ... --product <path-to-app-bundle-Info.plist>
# According to this article, a "Developer ID Installer:..." signing key is required:
# See: https://forums.ivanti.com/s/article/Obtaining-an-Apple-Developer-ID-Certificate-for-macOS-Provisioning?language=en_US&ui-force-components-controllers-recordGlobalValueProvider.RecordGvp.getRecord=1
# 
dist/SLIP39-$(VERSION).pkg:	dist/SLIP39.app
	productbuild --sign "$(PKGID)" --timestamp \
	    --identifier "$(BUNDLEID).pkg" \
	    --version $(VERSION) \
	    --component $< /Applications \
	    $@


# Confirm that the .pkg is signed w/ the correct certificates.
# See: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution/resolving_common_notarization_issues
# Not these:
# spctl --assess --type install --context context:primary-signature -vvv $< || \
# spctl --assess --type execute --context context:primary-signature -vvv $< || \
# spctl --assess --type open    --context context:primary-signature -vvv $< || \
# spctl --assess --type install  -vvv $< || \
# spctl --assess --type execute  -vvv $< || \
# spctl --assess --type open     -vvv $< || true

# Wrong:
# o The developer.apple.com/documentation is wrong; it is directly in conflict with the error
#   messages returned, demanding the 3rd Party Installer signing key

.PHONY: dist/SLIP39-$(VERSION).pkg-verify
dist/SLIP39-$(VERSION).pkg-verify: dist/SLIP39-$(VERSION).pkg
	@echo "\n\n*** Verifying signing of $<..."
	pkgutil --check-signature $< | grep "Signed with a trusted timestamp"
	#pkgutil --check-signature $< | grep "1. Developer ID Installer:"

#
# macOS Package Notarization
# See: https://oozou.com/blog/scripting-notarization-for-macos-app-distribution-38
# o The .pkg version doesn't work due to incorrect signing keys for the .pkg (unknown reason)
dist/SLIP39-$(VERSION).pkg.notarization: dist/SLIP39-$(VERSION).pkg dist/SLIP39-$(VERSION).pkg-verify
	jq -r '.["notarization-upload"]["RequestUUID"]' $@ 2>/dev/null \
	|| xcrun altool --notarize-app -f $< \
	    --primary-bundle-id $(BUNDLEID) \
	    --team-id $(TEAMID) \
	    --apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
	    --output-format json \
		> $@

dist/SLIP39-$(VERSION).pkg.notarization-status: dist/SLIP39-$(VERSION).pkg.notarization FORCE
	[ -s $@ ] && grep "Status: success" $@ \
	    || xcrun altool \
		--apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
		--notarization-info $$( jq -r '.["notarization-upload"]["RequestUUID"]' $< ) \
		    | tee -a $@

# Check notarization status 'til Status: success, then staple it to ...pkg, and create ...pkg.valid marker file
dist/SLIP39-$(VERSION).pkg.valid: dist/SLIP39-$(VERSION).pkg.notarization-status FORCE
	@grep "Status: success" $< || \
	    ( tail -10 $<; echo "\n\n!!! App not yet notarized; try again in a few seconds..."; false )
	( [ -r $@ ] ) \
	    && ( echo "\n\n*** Notarization complete; refreshing $@" && touch $@ ) \
	    || ( \
		xcrun stapler staple   dist/SLIP39-$(VERSION).pkg && \
		xcrun stapler validate dist/SLIP39-$(VERSION).pkg && \
	        echo "\n\n*** Notarization attached to $@" && \
		touch $@ \
	    )

# macOS ...pkg App Upload: Unless the ...dmg.upload file exists and is non-empty.
# o Could also use Transporter
# o Try either upload-package and upload-app approach
# o NOTE that --apple-id is NOT your "Apple ID", it is the unique App ID (see above)
dist/SLIP39-$(VERSION).pkg.upload-package: dist/SLIP39-$(VERSION).pkg dist/SLIP39-$(VERSION).pkg.valid FORCE
	[ -s $@ ] || ( \
	    echo "\n\n*** Uploading the signed PKG file: $<..." && \
	    echo "*** Verifying notarization stapling..." && xcrun stapler validate $< && \
	    echo "*** Checking signature..." && ./SLIP39.metadata/check-signature $< && \
	    echo "*** Upload starting for $<..." && \
	    xcrun altool --upload-package $< \
		--type macos \
		--bundle-id $(BUNDLEID) --bundle-version $(VERSION) --bundle-short-version-string $(VERSION) \
		--apple-id $(APPID) --team $(TEAMID) \
		--apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
		    | tee -a $@ \
	)



# 
# Build the macOS App, and Package the macOS App as a Zip file for Notarization
# 
# o Create a ZIP archive suitable for notarization.
# 
dist/SLIP39-$(VERSION).zip:	dist/SLIP39.app
	@echo "\n\n*** Creating and signing DMG $@..."
	@echo "Checking signature..." && ./SLIP39.metadata/check-signature $<
	codesign --verify $<
	codesign -dv -r- $<
	codesign -vv $<
	rm -f $@
	/usr/bin/ditto -c -k --keepParent "$<" "$@"
	@ls -last dist

# Upload and notarize the .zip, unless we've already uploaded it and have a RequestUUID
dist/SLIP39-$(VERSION).zip.notarization: dist/SLIP39-$(VERSION).zip
	jq -r '.["notarization-upload"]["RequestUUID"]' $@ 2>/dev/null \
	|| xcrun altool --notarize-app -f $< \
	    --primary-bundle-id $(BUNDLEID) \
	    --team-id $(TEAMID) \
	    --apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
	    --output-format json \
		> $@

# Refresh the ...zip.notariation-status, unless it is already "Status: success"
dist/SLIP39-$(VERSION).zip.notarization-status:  dist/SLIP39-$(VERSION).zip.notarization FORCE
	[ -s $@ ] && grep "Status: success" $@ \
	    || xcrun altool \
		--apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
		--notarization-info $$( jq -r '.["notarization-upload"]["RequestUUID"]' $< ) \
		    | tee -a $@


# Check notarization status 'til Status: success, then mark the ...zip.valid
# o We can't staple anything to a zip, but the contained app will now pass Gateway
#   on the client system, b/c it will check w/ Apple's servers that the app was notarized.
dist/SLIP39-$(VERSION).zip.valid: dist/SLIP39-$(VERSION).zip.notarization-status FORCE
	@grep "Status: success" $< || \
	    ( tail -10 $<; echo "\n\n!!! App not yet notarized; try again in a few seconds..."; false )
	@echo "\n\n*** Notarization complete; refreshing $@" \
	    && touch $@

# Submit App Zip w/o notarization stapled.
# o Doesn't work; same "Unsupported toolchain." error as ...-notarized.zip.upload
dist/SLIP39-$(VERSION).zip.upload-package: dist/SLIP39-$(VERSION).zip dist/SLIP39-$(VERSION).zip.valid FORCE
	[ -s $@ ] || xcrun altool --upload-package $< \
	    --type macos \
	    --bundle-id $(BUNDLEID) --bundle-version $(VERSION) --bundle-short-version-string $(VERSION) \
	    --apple-id $(APPID) \
	    --apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
		| tee -a $@

# Check notarization status 'til Status: success, then staple it to ...app, and create ...-notarized.zip
# o The .zip version works, but the notarization cannot be stapled to the zip;
#   - It should usually be checked via Gatekeeper, by the recipient of the App in the .zip
#   - We have to receive notification that the SLIP39.zip.notarization-status Status: success
#   - So, once we confirm notarization, just submit/publish the original .zip file
# o For other purposes (eg. just for manual installation), we can package the Notarized app
dist/SLIP39-$(VERSION)-notarized.zip: dist/SLIP39-$(VERSION).app dist/SLIP39-$(VERSION).zip.valid
	( [ -r $@ ] ) \
	    && ( echo "\n\n*** Notarization compete; not re-generating $@"; true ) \
	    || ( \
		xcrun stapler staple   $<; \
		xcrun stapler validate $<; \
	        echo "\n\n*** Notarization attached to $<; creating $@"; \
		/usr/bin/ditto -c -k --keepParent "$<" "$@"; \
		ls -last dist; \
	    )

# macOS ...zip App Upload: Unless the ...zip.upload file exists and is non-zero
# o I don't think it is possible to construct, notarize and submit an App for the macOS store via Zip
#   - We can't staple the notarization onto it.  Must use a .pkg or .dmg...
# *** Error: Error uploading 'dist/SLIP39-6.6.4-notarized.zip'.
# *** Error: Unsupported toolchain. Packages submitted to the App Store must be created either through Xcode, or using the productbuild[1] tool, as described in "Submitting your Mac apps to the App Store." Packages created by other tools, including PackageMaker, are not acceptable. [SIS] With error code STATE_ERROR.VALIDATION_ERROR.90270 for id 39784451-3843-428b-97ec-37c1b196ca35 Asset validation failed (-19208)
dist/SLIP39-$(VERSION)-notarized.zip.upload: dist/SLIP39-$(VERSION)-notarized.zip FORCE
	[ -s $@ ] || xcrun altool --upload-package $< \
	    --type macos \
	    --bundle-id $(BUNDLEID) --bundle-version $(VERSION) --bundle-short-version-string $(VERSION) \
	    --apple-id $(APPID) \
	    --apiKey $(APIKEY) --apiIssuer $(APIISSUER) \
		| tee -a $@


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
	pyinstaller --noconfirm --windowed --onefile $<
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
#    +                 'CFBundlePackageType':'APPL',
#    +                 'LSApplicationCategoryType':'public.app-category.utilities',
#    +                 'LSMinimumSystemVersion':'10.15.0',
#    +             })
#    +
#                 bundle_identifier='ca.kundert.perry.SLIP39')

SLIP39.spec: SLIP39.py
	@echo "\n\n!!! Rebuilding $@; Must be manually edited..."
	pyinstaller --noconfirm --windowed --onefile \
	    --codesign-identity "$(DEVID)" \
	    --osx-bundle-identifier "$(BUNDLEID)" \
	    --osx-entitlements-file ./SLIP39.metadata/entitlements.plist \
	    --collect-data shamir_mnemonic \
		$<
	@echo "!!! Regenerated $@: must be manually corrected!"
	false  # Make the build fail if we've regenerated the .spec

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
