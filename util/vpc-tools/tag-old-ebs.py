"""

For a given aws account, go through all un-attached volumes and tag them.

"""
import boto
import boto.utils
import argparse
import logging
import subprocess
import time
import os
from os.path import join, exists, isdir, islink, realpath, basename
import yaml
# needs to be pip installed
import netaddr

LOG_FORMAT = "%(asctime)s %(levelname)s - %(filename)s:%(lineno)s - %(message)s"
log_level = logging.INFO

def tags_for_hostname(hostname, mapping):
    logging.debug("Hostname is {}".format(hostname))
    if not hostname.startswith('ip-'):
        return {}

    octets = hostname.lstrip('ip-').split('-')
    tags = {}

    # Update with env and deployment info
    tags.update(mapping['CIDR_SECOND_OCTET'][octets[1]])

    ip_addr = netaddr.IPAddress(".".join(octets))
    for key, value in mapping['CIDR_REST'].items():
        cidr = ".".join([
            mapping['CIDR_FIRST_OCTET'],
            octets[1],
            key])

        cidrset = netaddr.IPSet([cidr])

        if ip_addr in cidrset:
            tags.update(value)

    return tags
        

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tag unattached ebs volumes.")
    parser.add_argument("--profile", '-p',
        help="AWS Profile to use with boto.")
    parser.add_argument("--noop", "-n", action="store_true",
        help="Don't actually tag anything.")
    parser.add_argument("--verbose", "-v", action="store_true",
        help="More verbose output.")
    parser.add_argument("--device", "-d", default="/dev/xvdf",
        help="The /dev/??? where the volume should be mounted.")
    parser.add_argument("--mountpoint", "-m", default="/mnt",
        help="Location to mount the new device.")
    parser.add_argument("--config", "-c", required=True,
        help="Configuration to map hostnames to tags.")
    # The config should specify what tags to associate with the second
    # and this octet of the hostname which should be the ip address.
    # example:

    args = parser.parse_args()

    mappings = yaml.safe_load(open(args.config,'r'))

    # Setup Logging
    if args.verbose:
        log_level = logging.DEBUG

    logging.basicConfig(format=LOG_FORMAT, level=log_level)

    # setup boto
    ec2 = boto.connect_ec2(profile_name=args.profile)

    # get mounting args
    id_info = boto.utils.get_instance_identity()['document']
    instance_id = id_info['instanceId']
    az = id_info['availabilityZone']
    device = args.device
    mountpoint = args.mountpoint

    # Find all unattached volumes
    filters = { "status": "available", "availability-zone": az }
    potential_volumes = ec2.get_all_volumes(filters=filters)
    logging.debug("Found {} unattached volumes in {}".format(len(potential_volumes), az))

    for vol in potential_volumes:
        # Attach volume to the instance running this process
        logging.debug("Trying to attach {} to {} at {}".format(
            vol.id, instance_id, device))

        ec2.attach_volume(vol.id, instance_id, device)

        try:
            # Wait for the volume to finish attaching.
            waiting_msg = "Waiting for {} to be available at {}"
            while not exists(device):
                time.sleep(2)
                logging.debug(waiting_msg.format(vol.id, device))

            # Mount the volume
            subprocess.check_call(["sudo", "mount", device, mountpoint])

            tag_data = {}
            # Look at some files on it to determine:
            #  - hostname
            #  - environment
            #  - deployment
            #  - cluster
            #  - instance-id
            #  - date created
            hostname_file = join(mountpoint, "etc", "hostname")
            edx_dir = join(mountpoint, 'edx', 'app')
            if exists(hostname_file):
                # This means this was a root volume.
                with open(hostname_file, 'r') as f:
                    hostname = f.readline().strip()
                    tag_data['hostname'] = hostname

                if exists(edx_dir) and isdir(edx_dir):
                    # This is an ansible related ami, we'll try to map
                    # the hostname to a knows deployment and cluster.
                    cluster_tags = tags_for_hostname(hostname, mappings)
                    tag_data.update(cluster_tags)
                else:
                    # Not an ansible created root volume.
                    tag_data['cluster'] = 'unknown'
            else:
                # Not a root volume
                tag_data['cluster'] = "unknown"

            instance_file = join(mountpoint, "var", "lib", "cloud", "instance")
            if exists(instance_file) and islink(instance_file):
                resolved_path = realpath(instance_file)
                old_instance_id = basename(resolved_path)
                tag_data['instance-id'] = old_instance_id

            tag_data['created'] = vol.create_time

            # If they are found tag the instance with them
            if args.noop:
                logging.info("Would have tagged {} with: \n{}".format(vol.id, str(tag_data)))
            else:
                logging.info("Tagging {} with: \n{}".format(vol.id, str(tag_data)))
                vol.add_tags(tag_data)

        finally:
            # Un-mount the volume
            subprocess.check_call(['sudo', 'umount', mountpoint])
            # detach the volume
            ec2.detach_volume(vol.id)
            time.sleep(2)
            while exists(device) or ec2.get_all_volumes(vol.id)[0].status != "available":
                time.sleep(2)
                logging.debug("Waiting for {} to be detached.".format(vol.id))
