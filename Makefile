APT_PREREQS=bzr libffi-dev libssl-dev python-dev python3-dev python-virtualenv
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

.PHONY: test
test:
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
