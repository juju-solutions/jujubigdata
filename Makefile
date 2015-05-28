APT_PREREQS=bzr libffi-dev libssl-dev python-dev python3-dev python-virtualenv
PROJECT=jujubigdata
SUITE=unstable
TESTS=tests/

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
	rm -rf .venv
	rm -rf .venv3
	rm -rf docs/_build

.PHONY: docclean
docclean:
	-rm -rf docs/_build

.PHONY: userinstall
userinstall:
	scripts/update-rev
	python setup.py install --user

.venv:
	@echo Processing apt package prereqs
	@for i in $(APT_PREREQS); do dpkg -l | grep -w $$i >/dev/null || sudo apt-get install -y $$i; done
	virtualenv .venv
	.venv/bin/pip install -IUr test_requirements.txt

.venv3:
	@echo Processing apt package prereqs
	@for i in $(APT_PREREQS); do dpkg -l | grep -w $$i >/dev/null || sudo apt-get install -y $$i; done
	virtualenv .venv3 --python=python3
	.venv3/bin/pip install -IUr test_requirements.txt

# Note we don't even attempt to run tests if lint isn't passing.
.PHONY: test
test: lint test2 test3

.PHONY: test2
test2:
	@echo Starting Py2 tests...
	.venv/bin/nosetests -s --nologcapture tests/

.PHONY: test3
test3:
	@echo Starting Py3 tests...
	.venv3/bin/nosetests -s --nologcapture tests/

.PHONY: ftest
ftest: lint
	@echo Starting fast tests...
	.venv/bin/nosetests --attr '!slow' --nologcapture tests/
	.venv3/bin/nosetests --attr '!slow' --nologcapture tests/

.PHONY: lint
lint: .venv .venv3
	@echo Checking for Python syntax...
	.venv/bin/flake8 --max-line-length=120 $(PROJECT) $(TESTS) \
	    && echo Py2 OK
	.venv3/bin/flake8 --max-line-length=120 $(PROJECT) $(TESTS) \
	    && echo Py3 OK

.PHONY: docs
docs: .venv
	- [ -z "`.venv/bin/pip list | grep -i 'sphinx '`" ] && .venv/bin/pip install sphinx
	- [ -z "`.venv/bin/pip list | grep -i sphinx-pypi-upload`" ] && .venv/bin/pip install sphinx-pypi-upload
	# If sphinx is installed on the system, pip installing into the venv does not
	# put the binaries into .venv/bin. Test for and use the .venv binary if it's
	# there; otherwise, we probably have a system sphinx in /usr/bin, so use that.
	SPHINX=$$(test -x .venv/bin/sphinx-build && echo \"../.venv/bin/sphinx-build\" || echo \"../.venv/bin/python /usr/bin/sphinx-build\"); \
	    cd docs && make html SPHINXBUILD=$$SPHINX && cd -

.PHONY: docrelease
docrelease: .venv docs
	.venv/bin/python setup.py register upload_docs

.PHONY: release
release: .venv docs
	scripts/update-rev
	.venv/bin/python setup.py register sdist upload upload_docs
