Apache Hadoop Core Platform Bundle
==================================

The `platform bundle`_ deploys the core Apache Hadoop platform, providing a
basic Hadoop deployment to use directly, as well as endpoints to which to
connect additional components, such as Apache Hive, Apache Pig, Hue, etc.
It also serves as a reference implementation and starting point for creating
charms for vendor-specific Hadoop platform distributions, such as Cloudera or
Hortonworks.


Deploying the Bundle
--------------------

Deploying the core platform bundle is as easy as::

    juju quickstart apache-core-batch-processing


Connecting Components
---------------------

Once the core platform bundle is deployed, you can add additional components,
such as Apache Hive::

    juju deploy cs:trusty/apache-hive
    juju add-relation apache-hive plugin

Currently available components include:

    * `Apache Hive`_
    * `Apache Pig`_
    * `Hue`_
    * `Apache Spark`_
    * `Apache Zeppelin`_


Charming New Components
-----------------------

New components can be added to the ecosystem using one of the following two
relations on the `apache-hadoop-plugin`_ endpoint charm:

    * **hadoop-rest**:  This interface is intended for components that interact
      with Hadoop only via the REST API, such as Hue.  Charms using this interface
      are provided with the REST API endpoint information for both the NameNode and
      the ResourceManager.  The details of the protocol used by this interface are
      documented in the :class:`helper class <jujubigdata.relations.HadoopREST>`,
      which is the recommended way to use this interface.

    * **hadoop-plugin**: This interface is intended for components that interact
      with Hadoop via either the Java API libraries, or the command-line interface
      (CLI).  Charms using this interface will have a JRE installed, the Hadoop
      API Java libraries installed, the Hadoop configuration managed in
      ``/etc/hadoop/conf``, and the environment configured in ``/etc/environment``.
      The endpoint will ensure that the distribution, version, Java, etc. are all
      compatible to ensure a properly functioning Hadoop ecosystem.  The details of
      the protocol used by this interface are documented in the
      :class:`helper class <jujubigdata.relations.HadoopPlugin>`,
      which is the recommended way to use this interface.


Replacing the Core
------------------

As long as it supports the same interfaces described above, the core platform
can be replaced with a different distribution.  The recommended way to create
charms for another distribution is to use the core platform charms as the base
and modify the ``dist.yaml`` and ``resources.yaml``.


.. _platform bundle: https://jujucharms.com/u/bigdata-dev/apache-core-batch-processing/
.. _apache-hadoop-plugin: https://jujucharms.com/u/bigdata-dev/apache-hadoop-plugin/
.. _Apache Hive: https://jujucharms.com/u/bigdata-dev/apache-hive/
.. _Apache Pig: https://jujucharms.com/u/bigdata-dev/apache-pig/
.. _Hue: https://jujucharms.com/u/bigdata-dev/apache-hue/
.. _Apache Spark: https://jujucharms.com/u/bigdata-dev/apache-spark/
.. _Apache Zeppelin: https://jujucharms.com/u/bigdata-dev/apache-zeppelin/
