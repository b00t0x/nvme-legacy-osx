PYTHON ?= python3
RELEASE ?= $(shell date +%Y%m%d)
INPUT ?= input/NVMeGeneric.kext

.PHONY: kexts packages release check clean

kexts:
	$(PYTHON) tools/build_kexts.py "$(INPUT)" build/kexts

packages: kexts
	$(PYTHON) tools/build_packages.py --snow-kext build/kexts/NVMeGeneric-Snow.kext --mavericks-kext build/kexts/NVMeGeneric-Mavericks.kext --release "$(RELEASE)" --output build/packages

release:
	$(PYTHON) tools/build_release.py --input "$(INPUT)" --release "$(RELEASE)" --output dist/$(RELEASE)

check:
	$(PYTHON) tools/check_repo.py

clean:
	rm -rf build dist
