APT_PREREQS=gcc libffi-dev libssl-dev python-dev python3-dev python-virtualenv
PROJECT=jujubigdata
SUITE=unstable
TESTS=tests/
VERSION=$(shell cat VERSION)

.PHONY: all
all:
	@echo "make test"
	@echo "make source - Create source package"
	@echo "make clean"
	@echo "make userinstall - Install locally"
	@echo "make docs - Build html documentation"
	@echo "make release - Build and upload package and docs to PyPI"

.PHONY: source
source: setup.py
	scripts/update-rev
	python setup.py sdist

.PHONY: clean
clean:
	-python setup.py clean
	find . -name '*.pyc' -delete
	rm -rf dist/*
	rm -rf .tox
	rm -rf docs/_build

.PHONY: docclean
docclean:
	-rm -rf docs/_build

.PHONY: userinstall
userinstall:
	scripts/update-rev
	python setup.py install -e --user

.PHONY: apt_prereqs
apt_prereqs:
	echo Processing apt package prereqs
	for i in $(APT_PREREQS); do dpkg -l | grep -w $$i[^-] >/dev/null || sudo apt-get install -y $$i; done
	# Need tox, but dont install the apt version unless we have to (dont want to conflict with pip)
	which tox >/dev/null || sudo apt-get install -y python-tox

.PHONY: test
test: apt_prereqs
	tox

.PHONY: ftest
ftest:
	tox -- -x --attr '!slow'

.PHONY: lint
lint:
	tox -e lint

.PHONY: docs
docs: test
	SPHINX="../.tox/docs/bin/sphinx-build"; \
	    cd docs && \
	    make html SPHINXBUILD=$$SPHINX && \
	    cd -

.PHONY: docrelease
docrelease: docs
	.tox/docs/bin/python setup.py register upload_docs

.PHONY: release
release: docs
	git remote | xargs -L1 git fetch --tags
	scripts/update-rev
	.tox/docs/bin/python setup.py register sdist upload upload_docs
	git tag release-${VERSION}
	git remote | xargs -L1 git push --tags
