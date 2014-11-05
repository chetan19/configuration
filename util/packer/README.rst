Packer
=======

- ``jenkins_worker.json`` is the `packer configuration template`_ that tells packer how to build the image.
* `template variable`_ pattern ``"foo": "{{env `BAR`}}"``

 * What this does is take the value of the environment variable BAR which was set in the shell that kicks off the ``packer build jenkins_worker.json`` command (for example in a jenkins job) and pass it through to the user variable "foo".
 * This the user variable "foo" will now be available globally within the template.
 * If the environment variable is not set in the shell that kicks off the packer build command, the user variable value will be the empty string.

* `file provisioner`_ pattern ``"type": "file" pattern``

 * What this does is write out a file onto the machine being built by packer.
 * If the source file contains references to user variables, e.g. {{user `foo`}} then the value of that variable will be written to the file.
 * In our example, this would be whatever the environment variable BAR was set to (see above bullet).


- ``extra_vars.json`` are passed to the `ansible-playbook command`_ that is used to run the jenkins_worker role, via the -e (--extra-vars) option
* playbook variable pattern ``"bar": "{{user `foo`}}"``

 * Packer has written out the value of the template user variable "foo" which was set up in jenkins_worker.json (see above)
 * Ansible will use this as the value for the playbook variable "bar" when running the play.
 * This is because in jenkins_worker.json we are provisioning with a shell command that executes the ansible-playbook command with ``-e '@extra_vars.json'``, which loads those variables from the JSON file `sent through the command line`_.

.. _packer configuration template: http://www.packer.io/docs/templates/introduction.html
.. _template variable: http://www.packer.io/docs/templates/user-variables.html
.. _file provisioner: http://www.packer.io/docs/provisioners/file.html
.. _ansible-playbook command: http://docs.ansible.com/playbooks_intro.html#executing-a-playbook
.. _sent through the command line: http://docs.ansible.com/playbooks_variables.html#passing-variables-on-the-command-line
