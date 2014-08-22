#!/usr/bin/env python


import argparse
import subprocess
import time
import uuid

from neutronclient.v2_0 import client as neutron
from novaclient.exceptions import NotFound
from novaclient.v1_1 import client as nova


class TimeoutError(RuntimeError):
    pass


def get_network_body():
    network_body = {
        'network': {}
    }
    return network_body


def get_subnet_body(network_id):
    subnet_body = {
        'subnet': {
            'network_id': network_id,
            'cidr': '192.168.199.0/24',
            'ip_version': 4,
            'dns_nameservers': [
                '8.8.8.8',
                '8.8.4.4'
            ]
        }
    }
    return subnet_body


def get_router_body(external_network_id):
    router_body = {
        'router': {
            'external_gateway_info': {
                'network_id': external_network_id
            }
        }
    }
    return router_body


def get_router_interface_body(subnet_id):
    router_interface_body = {
        'subnet_id': subnet_id
    }
    return router_interface_body


def get_external_network_id():
    networks = neutron_cl.list_networks()
    for network in networks['networks']:
        if network['router:external']:
            return network['id']


def create_network():
    print 'Creating network'
    network = neutron_cl.create_network(get_network_body())
    return network['network']['id']


def delete_network(network_id):
    print 'Deleting network'
    neutron_cl.delete_network(network_id)


def create_subnet(network_id):
    print 'Creating subnet'
    subnet = neutron_cl.create_subnet(get_subnet_body(network_id))
    return subnet['subnet']['id']


def delete_subnet(subnet_id):
    print 'Deleting subnet'
    neutron_cl.delete_subnet(subnet_id)


def create_router(external_network_id):
    print 'Creating router'
    router = neutron_cl.create_router(get_router_body(external_network_id))
    return router['router']['id']


def delete_router(router_id):
    print 'Deleting router'
    neutron_cl.delete_router(router_id)


def create_router_interface(router_id, subnet_id):
    print 'Creating router interface'
    interface = \
        neutron_cl.add_interface_router(router_id,
                                        get_router_interface_body(subnet_id))
    return interface['port_id']


def delete_router_interface(router_id, subnet_id):
    print 'Deleting router interface'
    neutron_cl.remove_interface_router(router_id,
                                       get_router_interface_body(subnet_id))


def create_ssh_key():
    print 'Creating SSH key'
    with open('.ssh/workflow_test_key.pub') as key_file:
        keypair = nova_cl.keypairs.create(name='workflow_key',
                                          public_key=key_file.read().strip())
    return keypair


def delete_ssh_key(keypair):
    print 'Deleting SSH key'
    keypair.delete()


def allocate_floating_ip():
    print 'Allocating floating IP'
    floating_ip_pools = nova_cl.floating_ip_pools.list()
    floating_ip_pool = floating_ip_pools[0].name
    floating_ip = nova_cl.floating_ips.create(floating_ip_pool)
    return floating_ip


def deallocate_floating_ip(floating_ip):
    print 'Deallocating floating IP'
    nova_cl.floating_ips.delete(floating_ip)


def associate_floating_ip(instance, floating_ip):
    print 'Associating floating IP'
    nova_cl.servers.add_floating_ip(instance, floating_ip)


def create_instance(image, flavor):
    print 'Creating instance'
    return nova_cl.servers.create(name=str(uuid.uuid1()),
                                  image=image,
                                  flavor=flavor,
                                  key_name='workflow_key')


def delete_instance(instance):
    print 'Deleting instance'
    instance.delete()


def wait_for_instance_active(instance):
    start_time = int(time.time())
    timeout = 120
    while True:
        time.sleep(1)
        print 'Waiting for instance to build'
        status = nova_cl.servers.get(instance).status
        if status == 'ACTIVE':
            print 'Instance created'
            return
        timed_out = int(time.time()) - start_time >= timeout
        if timed_out:
            raise TimeoutError('Instance creation timed out')


def wait_for_instance_deleted(instance):
    start_time = int(time.time())
    timeout = 300
    while True:
        time.sleep(1)
        print 'Waiting for instance to disappear'
        try:
            nova_cl.servers.get(instance)
        except NotFound:
            print 'Instance deleted'
            return
        timed_out = int(time.time()) - start_time >= timeout
        if timed_out:
            raise TimeoutError('Instance deletion timed out')


def wait_for_ssh_connection(ip):
    command = 'ssh -o StrictHostKeyChecking=no -i .ssh/workflow_test_key' \
              ' -l ubuntu {} "ping -c 1 google.com"'.format(ip)
    start_time = int(time.time())
    timeout = 60
    while True:
        time.sleep(1)
        print 'Checking SSH connection'
        check = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        output = check.communicate()
        print output
        code = check.returncode
        if not code:
            print 'SSH connection OK'
            return
        timed_out = int(time.time()) - start_time >= timeout
        if timed_out:
            raise TimeoutError('SSH to instance timed out')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--keystone_url', required=True,
                        help='Keystone endpoint URL')
    parser.add_argument('-u', '--user', required=True,
                        help='Keystone username')
    parser.add_argument('-p', '--password', required=True,
                        help='Keystone password')
    parser.add_argument('-t', '--tenant', required=True,
                        help='Keystone tenant name')
    parser.add_argument('-f', '--flavor', required=True,
                        help='Flavor ID to use for instances')
    parser.add_argument('-i', '--image', required=True,
                        help='Image ID to create instances from')
    args = parser.parse_args()

    neutron_cl = neutron.Client(username=args.user, password=args.password,
                                tenant_name=args.tenant,
                                auth_url=args.keystone_url)

    nova_cl = nova.Client(username=args.user, api_key=args.password,
                          project_id=args.tenant, auth_url=args.keystone_url)

    external_network_id = get_external_network_id()
    network_id = create_network()
    subnet_id = create_subnet(network_id)
    router_id = create_router(external_network_id)
    create_router_interface(router_id, subnet_id)

    floating_ip = allocate_floating_ip()
    keypair = create_ssh_key()

    start_time = int(time.time())
    instance = create_instance(args.image, args.flavor)
    timeout = {'occurred': False, 'message': ''}
    try:
        wait_for_instance_active(instance)
        instance_build_end_time = int(time.time())
        instance_build_time = instance_build_end_time - start_time
        print 'Instance build took {} seconds'.format(instance_build_time)
        associate_floating_ip(instance, floating_ip)
        ssh_start_time = int(time.time())
        wait_for_ssh_connection(floating_ip.ip)
        ssh_end_time = int(time.time())
        ssh_time = ssh_end_time - ssh_start_time
        print 'SSH took {} seconds'.format(ssh_time)
        with open('build_time.csv', 'w') as f:
            f.write('build_time,ssh_time\n{},{}'.format(instance_build_time,
                                                        ssh_time))
        end_time = int(time.time())
        print 'All took {} seconds'.format(end_time - start_time)
    except TimeoutError, e:
        timeout = {'occurred': True, 'message': e}
    except Exception, e:
        timeout = {'occurred': True,
                   'message': 'An error occurred: {}'.format(e)}
    finally:
        delete_instance(instance)
        wait_for_instance_deleted(instance)

        deallocate_floating_ip(floating_ip)
        delete_ssh_key(keypair)
        delete_router_interface(router_id, subnet_id)
        delete_network(network_id)
        delete_router(router_id)
        if timeout['occurred']:
            raise TimeoutError(e)