from setuptools import setup
import os


version_file = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            'VERSION'))
with open(version_file) as v:
    VERSION = v.read().strip()


SETUP = {
    'name': "jujubigdata",
    'version': VERSION,
    'author': "Ubuntu Developers",
    'author_email': "ubuntu-devel-discuss@lists.ubuntu.com",
    'url': "https://github.com/juju-solutions/jujubigdata",
    'install_requires': [
        "six",
        "pyaml",
        "path.py>=7.0",
        "jujuresources>=0.2.5",
        "setuptools-scm>=1.0.0,<2.0.0",  # needed by path.py (see pypa/pip#410)
        "charms.templating.jinja2>=1.0.0,<2.0.0",
    ],
    'packages': [
        "jujubigdata",
    ],
    'scripts': [
    ],
    'license': "Apache License v2.0",
    'long_description': open('README.rst').read(),
    'description': 'Helpers for Juju Charm development for Big Data',
    'package_data': {'jujubigdata': ['templates/*']},
}

try:
    from sphinx_pypi_upload import UploadDoc
    SETUP['cmdclass'] = {'upload_sphinx': UploadDoc}
except ImportError:
    pass

if __name__ == '__main__':
    setup(**SETUP)
