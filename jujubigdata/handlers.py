# Copyright 2014-2015 Canonical Limited.
#
# This file is part of jujubigdata.
#
# jujubigdata is free software: you can redistribute it and/or modify
# it under the terms of the Apache License version 2.0.
#
# jujubigdata is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# Apache License for more details.

import os
import sys
from subprocess import check_call, check_output
from path import Path

import jujuresources

from charmhelpers.core import hookenv
from charmhelpers.core import unitdata
from charmhelpers.core import host
from charms.templating.jinja2 import render

try:
    from charmhelpers.core.charmframework import helpers
except ImportError:
    helpers = None  # hack-around until transition to layers is complete


from jujubigdata import utils


class HadoopBase(object):
    def __init__(self, dist_config):
        self.dist_config = dist_config
        self.charm_config = hookenv.config()
        self.cpu_arch = utils.cpu_arch()
        self.client_spec = {
            'hadoop': self.dist_config.hadoop_version,
        }

        # dist_config will have simple validation done on primary keys in the
        # dist.yaml, but we need to ensure deeper values are present.
        required_dirs = ['hadoop', 'hadoop_conf', 'hdfs_log_dir',
                         'mapred_log_dir', 'yarn_log_dir']
        missing_dirs = set(required_dirs) - set(self.dist_config.dirs.keys())
        if missing_dirs:
            raise ValueError('dirs option in {} is missing required entr{}: {}'.format(
                self.dist_config.yaml_file,
                'ies' if len(missing_dirs) > 1 else 'y',
                ', '.join(missing_dirs)))

        # Build a list of hadoop resources needed from resources.yaml
        self.resources = {
            'java-installer': 'java-installer',
            'hadoop': 'hadoop-%s' % (self.cpu_arch),
        }
        hadoop_version = self.dist_config.hadoop_version
        versioned_res = 'hadoop-%s-%s' % (hadoop_version, self.cpu_arch)
        if jujuresources.resource_defined(versioned_res):
            self.resources['hadoop'] = versioned_res

        # LZO compression for hadoop is distributed separately. Add it to the
        # list of reqs if defined in resources.yaml
        lzo_res = 'hadoop-lzo-%s' % self.cpu_arch
        if jujuresources.resource_defined(lzo_res):
            self.resources['lzo'] = lzo_res

        # Verify and fetch the required hadoop resources
        self.verify_resources = utils.verify_resources(*self.resources.values())
        self.verify_conditional_resources = self.verify_resources  # for backwards compat

    def spec(self):
        """
        Generate the full spec for keeping charms in sync.

        NB: This has to be a callback instead of a plain property because it is
        passed to the relations during construction of the Manager but needs to
        properly reflect the Java version in the same hook invocation that installs
        Java.
        """
        java_version = unitdata.kv().get('java.version')
        if java_version:
            return {
                'vendor': self.dist_config.vendor,
                'hadoop': self.dist_config.hadoop_version,
                'java': java_version,
                'arch': self.cpu_arch,
            }
        else:
            return None

    def is_installed(self):
        return unitdata.kv().get('hadoop.base.installed')

    def install(self, force=False):
        if not force and self.is_installed():
            return
        hookenv.status_set('maintenance', 'Installing Apache Hadoop base')
        self.configure_hosts_file()
        self.dist_config.add_users()
        self.dist_config.add_dirs()
        self.dist_config.add_packages()
        self.install_base_packages()
        self.setup_hadoop_config()
        self.configure_hadoop()
        unitdata.kv().set('hadoop.base.installed', True)
        unitdata.kv().flush(True)
        hookenv.status_set('waiting', 'Apache Hadoop base installed')

    def configure_hosts_file(self):
        """
        Add the unit's private-address to /etc/hosts to ensure that Java
        can resolve the hostname of the server to its real IP address.
        We derive our hostname from the unit_id, replacing / with -.
        """
        local_ip = utils.resolve_private_address(hookenv.unit_get('private-address'))
        hostname = hookenv.local_unit().replace('/', '-')
        utils.update_kv_hosts({local_ip: hostname})
        utils.manage_etc_hosts()

        # update name of host to more semantically meaningful value
        # (this is required on some providers; the /etc/hosts entry must match
        # the /etc/hostname lest Hadoop get confused about where certain things
        # should be run)
        etc_hostname = Path('/etc/hostname')
        etc_hostname.write_text(hostname)
        check_call(['hostname', '-F', etc_hostname])

    def install_base_packages(self):
        with utils.disable_firewall():
            self.install_java()
            self.install_hadoop()

    def install_java(self):
        """
        Run the java-installer resource to install Java and determine
        the JAVA_HOME and Java version.

        The java-installer must be idempotent and its only output (on stdout)
        should be two lines: the JAVA_HOME path, and the Java version, respectively.

        If there is an error installing Java, the installer should exit
        with a non-zero exit code.
        """
        env = utils.read_etc_env()
        java_installer = Path(jujuresources.resource_path('java-installer'))
        java_installer.chmod(0o755)
        output = check_output([java_installer], env=env).decode('utf8')
        lines = output.strip().splitlines()
        if len(lines) != 2:
            raise ValueError('Unexpected output from java-installer: %s' % output)
        java_home, java_version = lines
        if '_' in java_version:
            java_major, java_release = java_version.split("_")
        else:
            java_major, java_release = java_version, ''
        unitdata.kv().set('java.home', java_home)
        unitdata.kv().set('java.version', java_major)
        unitdata.kv().set('java.version.release', java_release)

    def install_hadoop(self):
        jujuresources.install(self.resources['hadoop'],
                              destination=self.dist_config.path('hadoop'),
                              skip_top_level=True)

        # Install our lzo compression codec if it's defined in resources.yaml
        if 'lzo' in self.resources:
            jujuresources.install(self.resources['lzo'],
                                  destination=self.dist_config.path('hadoop'),
                                  skip_top_level=False)
        else:
            msg = ("The hadoop-lzo-%s resource was not found."
                   "LZO compression will not be available." % self.cpu_arch)
            hookenv.log(msg)

    def setup_hadoop_config(self):
        # copy default config into alternate dir
        conf_dir = self.dist_config.path('hadoop') / 'etc/hadoop'
        self.dist_config.path('hadoop_conf').rmtree_p()
        conf_dir.copytree(self.dist_config.path('hadoop_conf'))
        (self.dist_config.path('hadoop_conf') / 'slaves').remove_p()
        mapred_site = self.dist_config.path('hadoop_conf') / 'mapred-site.xml'
        if not mapred_site.exists():
            (self.dist_config.path('hadoop_conf') / 'mapred-site.xml.template').copy(mapred_site)

    def configure_hadoop(self):
        java_home = Path(unitdata.kv().get('java.home'))
        java_bin = java_home / 'bin'
        hadoop_home = self.dist_config.path('hadoop')
        hadoop_bin = hadoop_home / 'bin'
        hadoop_sbin = hadoop_home / 'sbin'

        # If we have hadoop-addons (like lzo), set those in the environment
        hadoop_extra_classpath = []
        if 'lzo' in self.resources:
            hadoop_extra_classpath.extend(hadoop_home.walkfiles('hadoop-lzo-*.jar'))
        with utils.environment_edit_in_place('/etc/environment') as env:
            env['JAVA_HOME'] = java_home
            if java_bin not in env['PATH']:
                env['PATH'] = ':'.join([java_bin, env['PATH']])  # ensure that correct java is used
            if hadoop_bin not in env['PATH']:
                env['PATH'] = ':'.join([env['PATH'], hadoop_bin])
            if hadoop_sbin not in env['PATH']:
                env['PATH'] = ':'.join([env['PATH'], hadoop_sbin])
            if hadoop_extra_classpath:
                env['HADOOP_EXTRA_CLASSPATH'] = ':'.join(hadoop_extra_classpath)
            env['HADOOP_LIBEXEC_DIR'] = hadoop_home / 'libexec'
            env['HADOOP_INSTALL'] = hadoop_home
            env['HADOOP_HOME'] = hadoop_home
            env['HADOOP_COMMON_HOME'] = hadoop_home
            env['HADOOP_HDFS_HOME'] = hadoop_home
            env['HADOOP_MAPRED_HOME'] = hadoop_home
            env['HADOOP_MAPRED_LOG_DIR'] = self.dist_config.path('mapred_log_dir')
            env['HADOOP_YARN_HOME'] = hadoop_home
            env['HADOOP_CONF_DIR'] = self.dist_config.path('hadoop_conf')
            env['YARN_LOG_DIR'] = self.dist_config.path('yarn_log_dir')
            env['HADOOP_LOG_DIR'] = self.dist_config.path('hdfs_log_dir')

        hadoop_env = self.dist_config.path('hadoop_conf') / 'hadoop-env.sh'
        utils.re_edit_in_place(hadoop_env, {
            r'export JAVA_HOME *=.*': 'export JAVA_HOME=%s' % java_home,
        })

    def register_slaves(self, slaves):
        """
        Add slaves to a hdfs or yarn master, determined by the relation name.

        :param str relation: 'datanode' for registering HDFS slaves;
                             'nodemanager' for registering YARN slaves.
        """
        slaves_file = self.dist_config.path('hadoop_conf') / 'slaves'
        slaves_file.write_lines(
            [
                '# DO NOT EDIT',
                '# This file is automatically managed by Juju',
            ] + slaves
        )
        slaves_file.chown('ubuntu', 'hadoop')

    def run(self, user, command, *args, **kwargs):
        """
        Run a Hadoop command as the `hdfs` user.

        :param str command: Command to run, prefixed with `bin/` or `sbin/`
        :param list args: Additional args to pass to the command
        """
        return utils.run_as(user,
                            self.dist_config.path('hadoop') / command,
                            *args, **kwargs)

    def open_ports(self, service):
        for port in self.dist_config.exposed_ports(service):
            hookenv.open_port(port)

    def close_ports(self, service):
        for port in self.dist_config.exposed_ports(service):
            hookenv.close_port(port)

    def setup_init_script(self, user, servicename):
        daemon = "yarn"
        if user == "hdfs":
            daemon = "hadoop"
        elif user == "mapred":
            daemon = "mr-jobhistory"

        template_name = 'templates/upstart.conf'
        target_template_path = '/etc/init/{}.conf'.format(servicename)
        if host.init_is_systemd():
            template_name = 'templates/systemd.conf'
            target_template_path = '/etc/systemd/system/{}.service'.format(servicename)

        d = os.path.dirname(sys.modules['jujubigdata'].__file__)
        source_template_path = os.path.join(d, template_name)

        if os.path.exists(target_template_path):
            os.remove(target_template_path)

        render(
            source_template_path,
            target_template_path,
            templates_dir="/",
            context={
                'service': servicename,
                'user': user,
                'hadoop_path': self.dist_config.path('hadoop'),
                'hadoop_conf': self.dist_config.path('hadoop_conf'),
                'daemon': daemon,
            },
        )
        if host.init_is_systemd():
            utils.run_as('root', 'systemctl', 'enable', '{}.service'.format(servicename))

        if host.init_is_systemd():
            utils.run_as('root', 'systemctl', 'daemon-reload')


class HDFS(object):
    def __init__(self, hadoop_base):
        self.hadoop_base = hadoop_base

    def stop_namenode(self):
        host.service_stop('namenode')

    def start_namenode(self):
        if not utils.jps('NameNode'):
            host.service_start('namenode')

    def restart_namenode(self):
        self.stop_namenode()
        self.start_namenode()

    def restart_zookeeper(self):
        self.stop_zookeeper()
        self.start_zookeeper()

    def stop_zookeeper(self):
        host.service_stop('zkfc')

    def start_zookeeper(self):
        host.service_start('zkfc')

    def restart_dfs(self):
        self.stop_dfs()
        self.start_dfs()

    def stop_dfs(self):
        self.hadoop_base.run('hdfs', 'sbin/stop-dfs.sh')

    def start_dfs(self):
        self.hadoop_base.run('hdfs', 'sbin/start-dfs.sh')

    def stop_secondarynamenode(self):
        host.service_stop('secondarynamenode')

    def start_secondarynamenode(self):
        if not utils.jps('SecondaryNameNode'):
            host.service_start('secondarynamenode')

    def stop_datanode(self):
        host.service_stop('datanode')

    def start_datanode(self):
        if not utils.jps('DataNode'):
            host.service_start('datanode')

    def restart_datanode(self):
        self.stop_datanode()
        self.start_datanode()

    def stop_journalnode(self):
        host.service_stop('journalnode')

    def start_journalnode(self):
        if not utils.jps('JournalNode'):
            host.service_start('journalnode')

    def restart_journalnode(self):
        self.stop_journalnode()
        self.start_journalnode()

    def configure_namenode(self, namenodes):
        dc = self.hadoop_base.dist_config
        clustername = hookenv.service_name()
        host = hookenv.local_unit().replace('/', '-')
        self.configure_hdfs_base(clustername, namenodes, dc.port('namenode'), dc.port('nn_webapp_http'))
        hdfs_site = dc.path('hadoop_conf') / 'hdfs-site.xml'
        with utils.xmlpropmap_edit_in_place(hdfs_site) as props:
            props['dfs.namenode.datanode.registration.ip-hostname-check'] = 'true'
            props['dfs.namenode.http-address.%s.%s' % (clustername, host)] = '%s:%s' % (host, dc.port('nn_webapp_http'))
            props['dfs.namenode.rpc-bind-host'] = '0.0.0.0'
            props['dfs.namenode.servicerpc-bind-host'] = '0.0.0.0'
            props['dfs.namenode.http-bind-host'] = '0.0.0.0'
            props['dfs.namenode.https-bind-host'] = '0.0.0.0'
        self.hadoop_base.setup_init_script("hdfs", "namenode")

    def configure_zookeeper(self, zookeepers):
        dc = self.hadoop_base.dist_config
        hdfs_site = dc.path('hadoop_conf') / 'hdfs-site.xml'
        with utils.xmlpropmap_edit_in_place(hdfs_site) as props:
            props['dfs.ha.automatic-failover.enabled'] = 'true'
        core_site = dc.path('hadoop_conf') / 'core-site.xml'
        with utils.xmlpropmap_edit_in_place(core_site) as props:
            zk_str = ','.join('{host}:{port}'.format(**zk) for zk in zookeepers)
            hookenv.log("Zookeeper string is: %s" % zk_str)
            props['ha.zookeeper.quorum'] = zk_str
        self.hadoop_base.setup_init_script("hdfs", "zkfc")

    def configure_datanode(self, clustername, namenodes, port, webhdfs_port):
        self.configure_hdfs_base(clustername, namenodes, port, webhdfs_port)
        dc = self.hadoop_base.dist_config
        hdfs_site = dc.path('hadoop_conf') / 'hdfs-site.xml'
        with utils.xmlpropmap_edit_in_place(hdfs_site) as props:
            props['dfs.datanode.http.address'] = '0.0.0.0:{}'.format(dc.port('dn_webapp_http'))
        self.hadoop_base.setup_init_script("hdfs", "datanode")
        self.hadoop_base.setup_init_script("hdfs", "journalnode")

    def configure_journalnode(self):
        dc = self.hadoop_base.dist_config
        hdfs_site = dc.path('hadoop_conf') / 'hdfs-site.xml'
        with utils.xmlpropmap_edit_in_place(hdfs_site) as props:
            props['dfs.journalnode.rpc-address'] = '0.0.0.0:{}'.format(dc.port('journalnode'))
            props['dfs.journalnode.http-address'] = '0.0.0.0:{}'.format(dc.port('jn_webapp_http'))

    def configure_client(self, clustername, namenodes, port, webhdfs_port):
        self.configure_hdfs_base(clustername, namenodes, port, webhdfs_port)

    def configure_hdfs_base(self, clustername, namenodes, port, webhdfs_port):
        dc = self.hadoop_base.dist_config
        core_site = dc.path('hadoop_conf') / 'core-site.xml'
        with utils.xmlpropmap_edit_in_place(core_site) as props:
            props['hadoop.proxyuser.hue.hosts'] = "*"
            props['hadoop.proxyuser.hue.groups'] = "*"
            props['hadoop.proxyuser.oozie.groups'] = '*'
            props['hadoop.proxyuser.oozie.hosts'] = '*'
            if 'lzo' in self.hadoop_base.resources:
                props['io.compression.codecs'] = ('org.apache.hadoop.io.compress.GzipCodec, '
                                                  'org.apache.hadoop.io.compress.DefaultCodec, '
                                                  'org.apache.hadoop.io.compress.BZip2Codec, '
                                                  'org.apache.hadoop.io.compress.SnappyCodec, '
                                                  'com.hadoop.compression.lzo.LzoCodec, '
                                                  'com.hadoop.compression.lzo.LzopCodec')
                props['io.compression.codec.lzo.class'] = 'com.hadoop.compression.lzo.LzoCodec'
            else:
                props['io.compression.codecs'] = ('org.apache.hadoop.io.compress.GzipCodec, '
                                                  'org.apache.hadoop.io.compress.DefaultCodec, '
                                                  'org.apache.hadoop.io.compress.BZip2Codec, '
                                                  'org.apache.hadoop.io.compress.SnappyCodec')
            props['fs.defaultFS'] = "hdfs://{clustername}".format(clustername=clustername, port=port)
        hdfs_site = dc.path('hadoop_conf') / 'hdfs-site.xml'
        with utils.xmlpropmap_edit_in_place(hdfs_site) as props:
            props['dfs.webhdfs.enabled'] = "true"
            props['dfs.namenode.name.dir'] = dc.path('hdfs_dir_base') / 'cache/hadoop/dfs/name'
            props['dfs.datanode.data.dir'] = dc.path('hdfs_dir_base') / 'cache/hadoop/dfs/name'
            props['dfs.permissions'] = 'false'  # TODO - secure this hadoop installation!
            props['dfs.nameservices'] = clustername
            props['dfs.client.failover.proxy.provider.%s' % clustername] = \
                'org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider'
            props['dfs.ha.fencing.methods'] = 'sshfence\nshell(/bin/true)'
            props['dfs.ha.fencing.ssh.private-key-files'] = utils.ssh_priv_key('hdfs')
            props['dfs.ha.namenodes.%s' % clustername] = ','.join(namenodes)
            for node in namenodes:
                props['dfs.namenode.rpc-address.%s.%s' % (clustername, node)] = '%s:%s' % (node, port)
                props['dfs.namenode.http-address.%s.%s' % (clustername, node)] = '%s:%s' % (node, webhdfs_port)

    def init_sharededits(self):
        self._hdfs('namenode', '-initializeSharedEdits', '-nonInteractive', '-force')

    def format_zookeeper(self):
        self._hdfs('zkfc', '-formatZK', '-nonInteractive', '-force')

    def bootstrap_standby(self):
        self._hdfs('namenode', '-bootstrapStandby', '-nonInteractive', '-force')

    def transition_to_active(self, serviceid):
        hookenv.log("Transitioning to active: " + str(serviceid))
        self._hdfs('haadmin', '-transitionToActive', serviceid)

    def ensure_HA_active(self, namenodes, leader):
        '''
        Function to ensure one namenode in an HA Initialized cluster is
        in active and one is in standby in the absence of zookeeper
        to handle automatic failover
        '''
        hookenv.log("ensure HA active function:")
        hookenv.log(str(namenodes) + ", " + str(leader))
        hookenv.log(str(len(namenodes)))
        if len(namenodes) == 2:
            output = []
            for node in namenodes:
                output.append(utils.run_as('hdfs',
                                           'hdfs', 'haadmin', '-getServiceState', '{}'.format(node),
                                           capture_output=True).lower())
            if 'active' not in output:
                self.transition_to_active(leader)

    def format_namenode(self):
        if unitdata.kv().get('hdfs.namenode.formatted'):
            return
        self.stop_namenode()
        # Run without prompting; this will fail if the namenode has already
        # been formatted -- we do not want to reformat existing data!
        clusterid = hookenv.service_name()
        self._hdfs('namenode', '-format', '-noninteractive', '-clusterid', clusterid)
        unitdata.kv().set('hdfs.namenode.formatted', True)
        unitdata.kv().flush(True)

    def create_hdfs_dirs(self):
        if unitdata.kv().get('hdfs.namenode.dirs.created'):
            return
        hookenv.log("Creating HDFS Data dirs...")
        self._hdfs('dfs', '-mkdir', '-p', '/tmp/hadoop/mapred/staging')
        self._hdfs('dfs', '-chmod', '-R', '1777', '/tmp/hadoop/mapred/staging')
        self._hdfs('dfs', '-mkdir', '-p', '/tmp/hadoop-yarn/staging')
        self._hdfs('dfs', '-chmod', '-R', '1777', '/tmp/hadoop-yarn')
        self._hdfs('dfs', '-mkdir', '-p', '/user/ubuntu')
        self._hdfs('dfs', '-chown', '-R', 'ubuntu', '/user/ubuntu')
        # for JobHistory
        self._hdfs('dfs', '-mkdir', '-p', '/mr-history/tmp')
        self._hdfs('dfs', '-chmod', '-R', '1777', '/mr-history/tmp')
        self._hdfs('dfs', '-mkdir', '-p', '/mr-history/done')
        self._hdfs('dfs', '-chmod', '-R', '1777', '/mr-history/done')
        self._hdfs('dfs', '-chown', '-R', 'mapred:hdfs', '/mr-history')
        self._hdfs('dfs', '-mkdir', '-p', '/app-logs')
        self._hdfs('dfs', '-chmod', '-R', '1777', '/app-logs')
        self._hdfs('dfs', '-chown', 'yarn', '/app-logs')
        unitdata.kv().set('hdfs.namenode.dirs.created', True)
        unitdata.kv().flush(True)

    def register_slaves(self, slaves):
        self.hadoop_base.register_slaves(slaves)

    def reload_slaves(self):
        if utils.jps('NameNode'):
            self.hadoop_base.run('hdfs', 'bin/hdfs', 'dfsadmin', '-refreshNodes')

    def register_journalnodes(self, nodes, port):
        clustername = hookenv.service_name()
        hdfs_site = self.hadoop_base.dist_config.path('hadoop_conf') / 'hdfs-site.xml'
        with utils.xmlpropmap_edit_in_place(hdfs_site) as props:
            props['dfs.namenode.shared.edits.dir'] = 'qjournal://{}/{}'.format(
                ';'.join(['%s:%s' % (host, port) for host in nodes]),
                clustername)

    def _hdfs(self, command, *args):
        self.hadoop_base.run('hdfs', 'bin/hdfs', command, *args)


class YARN(object):
    def __init__(self, hadoop_base):
        self.hadoop_base = hadoop_base

    def stop_resourcemanager(self):
        host.service_stop('resourcemanager')

    def start_resourcemanager(self):
        if not utils.jps('ResourceManager'):
            host.service_start('resourcemanager')

    def restart_resourcemanager(self):
        self.stop_resourcemanager()
        self.start_resourcemanager()

    def stop_jobhistory(self):
        host.service_stop('historyserver')

    def start_jobhistory(self):
        if not utils.jps('JobHistoryServer'):
            host.service_start('historyserver')

    def stop_nodemanager(self):
        host.service_stop('nodemanager')

    def start_nodemanager(self):
        if not utils.jps('NodeManager'):
            host.service_start('nodemanager')

    def restart_nodemanager(self):
        self.stop_nodemanager()
        self.start_nodemanager()

    def _local(self):
        """
        Return the local hostname (which we derive from our unit name),
        and resourcemanager port from our dist.yaml
        """
        host = hookenv.local_unit().replace('/', '-')
        port = self.hadoop_base.dist_config.port('resourcemanager')
        history_http = self.hadoop_base.dist_config.port('jh_webapp_http')
        history_ipc = self.hadoop_base.dist_config.port('jobhistory')
        return host, port, history_http, history_ipc

    def configure_resourcemanager(self):
        self.configure_yarn_base(*self._local())
        dc = self.hadoop_base.dist_config
        yarn_site = dc.path('hadoop_conf') / 'yarn-site.xml'
        with utils.xmlpropmap_edit_in_place(yarn_site) as props:
            # 0.0.0.0 will listen on all interfaces, which is what we want on the server
            props['yarn.resourcemanager.webapp.address'] = '0.0.0.0:{}'.format(dc.port('rm_webapp_http'))
            # TODO: support SSL
            # props['yarn.resourcemanager.webapp.https.address'] = '0.0.0.0:{}'.format(dc.port('rm_webapp_https'))
        self.hadoop_base.setup_init_script(user='yarn', servicename='resourcemanager')

    def configure_jobhistory(self):
        self.configure_yarn_base(*self._local())
        dc = self.hadoop_base.dist_config
        mapred_site = dc.path('hadoop_conf') / 'mapred-site.xml'
        with utils.xmlpropmap_edit_in_place(mapred_site) as props:
            # 0.0.0.0 will listen on all interfaces, which is what we want on the server
            props["mapreduce.jobhistory.address"] = "0.0.0.0:{}".format(dc.port('jobhistory'))
            props["mapreduce.jobhistory.webapp.address"] = "0.0.0.0:{}".format(dc.port('jh_webapp_http'))
            props["mapreduce.jobhistory.intermediate-done-dir"] = "/mr-history/tmp"
            props["mapreduce.jobhistory.done-dir"] = "/mr-history/done"
        self.hadoop_base.setup_init_script(user='mapred', servicename='historyserver')

    def configure_nodemanager(self, host, port, history_http, history_ipc):
        self.configure_yarn_base(host, port, history_http, history_ipc)
        self.hadoop_base.setup_init_script(user="yarn", servicename="nodemanager")

    def configure_client(self, host, port, history_http, history_ipc):
        self.configure_yarn_base(host, port, history_http, history_ipc)

    def configure_yarn_base(self, host, port, history_http, history_ipc):
        dc = self.hadoop_base.dist_config
        yarn_site = dc.path('hadoop_conf') / 'yarn-site.xml'
        with utils.xmlpropmap_edit_in_place(yarn_site) as props:
            props['yarn.nodemanager.aux-services'] = 'mapreduce_shuffle'
            props['yarn.nodemanager.vmem-check-enabled'] = 'false'
            if host:
                props['yarn.resourcemanager.hostname'] = '{}'.format(host)
                props['yarn.resourcemanager.address'] = '{}:{}'.format(host, port)
                props["yarn.log.server.url"] = "{}:{}/jobhistory/logs/".format(host, history_http)
        mapred_site = dc.path('hadoop_conf') / 'mapred-site.xml'
        with utils.xmlpropmap_edit_in_place(mapred_site) as props:
            if host and history_ipc:
                props["mapreduce.jobhistory.address"] = "{}:{}".format(host, history_ipc)
            if host and history_http:
                props["mapreduce.jobhistory.webapp.address"] = "{}:{}".format(host, history_http)
            props["mapreduce.framework.name"] = 'yarn'
            props["mapreduce.jobhistory.intermediate-done-dir"] = "/mr-history/tmp"
            props["mapreduce.jobhistory.done-dir"] = "/mr-history/done"
            props["mapreduce.map.output.compress"] = 'true'
            props["mapred.map.output.compress.codec"] = 'org.apache.hadoop.io.compress.SnappyCodec'
            props["mapreduce.application.classpath"] = "$HADOOP_HOME/share/hadoop/mapreduce/*,\
                $HADOOP_HOME/share/hadoop/mapreduce/lib/*,\
                $HADOOP_HOME/share/hadoop/tools/lib/*"

    def install_demo(self):
        if unitdata.kv().get('yarn.client.demo.installed'):
            return
        # Copy our demo (TeraSort) to the target location and set mode/owner
        demo_source = 'scripts/terasort.sh'
        demo_target = '/home/ubuntu/terasort.sh'

        Path(demo_source).copy(demo_target)
        Path(demo_target).chmod(0o755)
        Path(demo_target).chown('ubuntu', 'hadoop')
        unitdata.kv().set('yarn.client.demo.installed', True)
        unitdata.kv().flush(True)

    def register_slaves(self, slaves):
        self.hadoop_base.register_slaves(slaves)
        if utils.jps('ResourceManager'):
            self.hadoop_base.run('mapred', 'bin/yarn', 'rmadmin', '-refreshNodes')
