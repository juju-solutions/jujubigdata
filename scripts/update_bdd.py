#!/usr/bin/env python

import argparse
from glob import glob
from hashlib import sha256
import os
import re
import requests
import shutil
from subprocess import check_call, check_output
import sys
from urlparse import urljoin

import ruamel.yaml

sys.path.append('.')
from charmhelpers.core.host import chdir


def parse_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-B', '--no-build', action='store_true',
                        help="Don't build & push a new jujubigdata, just use most recent in bigdata-data")
    parser.add_argument('-b', '--bigdata-data', default='../bigdata-data', metavar='DIR',
                        help='Directory of the bigdata-data repo')
    parser.add_argument('-c', '--charmdir', default=os.path.join(os.environ['JUJU_REPOSITORY'], 'trusty'),
                        metavar='DIR', help='Directory containing all of the charms')
    parser.add_argument('-m', '--message', default='Updated jujubigdata',
                        help='Commit message for bigdata-data and the charms')
    parser.add_argument('-f', '--force', action='store_true',
                        help="Don't prompt for each charm")
    parser.add_argument('-t', '--test', action='store_true',
                        help="Bundle jujubigdata for local testing")
    parser.add_argument('charms', nargs='*', default=['apache-hadoop-*'],
                        help="Name of one or more charms to update (can contain wildcards)")
    return parser.parse_args(args)


def get_latest(repo):
    with chdir(repo):
        check_call(['bzr', 'pull'])
        filename = glob('common/noarch/jujubigdata-*')[0]
        with open(filename) as fp:
            hash = sha256(fp.read()).hexdigest()
    print "Hash: {}".format(hash)
    return os.path.abspath(filename), hash


def build():
    check_call(['make', 'clean'])
    check_call(['make', 'sdist'])
    filename = glob('dist/jujubigdata-*.tar.gz')[0]
    with open(filename) as fp:
        hash = sha256(fp.read()).hexdigest()
    print "Hash: {}".format(hash)
    return os.path.abspath(filename), hash


def upload(filename, repo, message, testing):
    with chdir(repo):
        check_call(['bzr', 'pull'])
    shutil.copy(filename, os.path.join(repo, 'common/noarch'))
    if not testing:
        with chdir(repo):
            check_call(['bzr', 'commit', '-m', message])
            check_call(['bzr', 'push'])


def get_url(filename, testing):
    if not testing:
        download_page = 'http://bazaar.launchpad.net/~bigdata-dev/bigdata-data/trunk/files/head:/common/noarch/'
        page = requests.get(download_page)
        match = re.search(r'<a href="([^"]*)" title="Download jujubigdata-', page.text)
        assert match, 'Unable to find download URL'
        url = urljoin(download_page, match.group(1))
    else:
        url = 'file:resources/{}'.format(os.path.basename(filename))
    return url


def update_charm(charm, url, hash, hash_type, filename, message, force, testing):
    charmname = os.path.basename(charm)
    with chdir(charm):
        if not os.path.exists('resources.yaml'):
            print 'Skipping (no resources): {}'.format(charmname)
            return
        if not force:
            input = raw_input('Update {}? [Y/n] '.format(charmname))
            if input.strip().lower() not in ('', 'y', 'yes'):
                print '  Skipping'
                return
            print '  Updating'
        else:
            print 'Updating: {}'.format(charmname)
        with open('resources.yaml', 'r') as fp:
            resources = ruamel.yaml.load(fp, ruamel.yaml.RoundTripLoader)
        if 'jujubigdata' not in resources['resources']:
            print 'Skipping (no jujubigdata): {}'.format(charm)
            return
        resources['resources']['jujubigdata'].update({
            'pypi': url,
            'hash': hash,
            'hash_type': hash_type,
        })
        with open('resources.yaml', 'w') as fp:
            ruamel.yaml.dump(resources, fp, Dumper=ruamel.yaml.RoundTripDumper)
        for oldfile in glob('resources/jujubigdata-*'):
            os.remove(oldfile)
        if testing:
            shutil.copy(filename, 'resources')
            check_call(['bzr', 'add', 'resources'])
        last_log = check_output(['bzr', 'log', '--line', '-l1'])
        if '[wip]' in last_log:
            check_call(['bzr', 'uncommit', '--force'])
        if testing:
            message = '[wip] {}'.format(message)
        check_call(['bzr', 'commit', '-m', message])


def main(opts):
    if opts.no_build:
        filename, hash = get_latest(opts.bigdata_data)
    else:
        filename, hash = build()
        upload(filename, opts.bigdata_data, opts.message, opts.test)
    url = get_url(filename, opts.test)
    for charmpat in opts.charms:
        charms = glob(os.path.join(opts.charmdir, charmpat))
        for charm in charms:
            update_charm(charm, url, hash, 'sha256', filename, opts.message, opts.force, opts.test)


if __name__ == '__main__':
    opts = parse_args(sys.argv[1:])
    main(opts)
