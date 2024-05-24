"""
Netprobify dynamic inventory module adding endpoints for a given service to the list of netprobify targets.
Handles IPv4 and IPv6 targets

Configuration file schema:
* namespace: Namespace of the service to watch
* service_name: Name of the service to watch
* dst_port: Target port for created ports. Defaults to 80
* target_options: Additional options to set on the Netprobify probe - any thing you can set on a target object of the netprobify config is acceptable
  Required keys:
  * groups: must be set to an array of netprobify group names to add discovered targets to
"""

from ipaddress import ip_address
from kubernetes import client, config as kube_config, watch
from time import sleep

import logging
import os.path
import yaml

log = logging.getLogger(__name__)

def start(targets, module_name, logging_level, config_file="kube_svc_endpoints.yaml"):
    log.setLevel(logging_level)

    # Initialize our targets list
    targets[module_name] = []

    if not os.path.isfile(config_file):
        log.info(f"Missing configuration file {config_file}. Disabling module")
        return

    # Load the configuration from the given file - as YAML
    with open(config_file, "r") as conf_file:
        config = yaml.safe_load(conf_file)

    for required_key in ["namespace", "service_name", "dst_port", "target_options"]:
        if not config.get(required_key):
            raise Exception(f"Kube_svc_endpoint configuration is missing required value '{required_key}'")

    if len(config["target_options"].get('groups', [])) == 0:
        raise Exception(f"Kube_svc_endpoint configuration is invalid: target_options.groups must be set to an array of groups to add target to")

    # Kubernetes configuration loading
    try:
        # Start by trying to discover configuration as running from inside a pod
        kube_config.load_incluster_config()
    except:
        log.warn("Could not load in-cluster kubernetes configuration. Trying default kubeconfig loading...")
        try:
            kube_config.load_kube_config()
        except:
            log.exception("Could not load Kubernetes configuration")
            return


    def update_targets(owner, addresses = set(), hostname_map = {}):
        """
        Update targets from the given owner to match exactly the given set of addresses.
        Removes addresses that are not anymore in the addresses set, adds missing addresses.

        * owner: the owner of th address list to update (should be the endpointslice name)
        * addresses: a set of addresses to set for this owner. Each address can be IPv4 or IPv6, each is processed independently
        * hostname_map: a dictionnary mapping an address to the hostname to use. If an address does not exist in this map, its hostname will be set to the IP
        """
        # Remove targets that don't exist anymore
        updated_targets = [target for target in targets[module_name] if target["owner"] != owner or target["destination"] in addresses]

        # Build a set of addresses already registered for this endpoint slice
        known_addresses = set(target["destination"] for target in updated_targets if target["owner"] == owner)

        for address in addresses:
            # Skip addresses we already registered for this endpoint slice
            if address in known_addresses:
                continue

            # This address was not registered as a target yet. Add it
            ip = ip_address(address)
            target = {
                "description": f"{owner} - {address}",
                "type": "TCPsyn",
                "destination": address,
                "address_family": "ipv{}".format(ip.version),
                "is_subnet": False,
                "dst_port": config.get("dst_port", 80),
                "owner": owner,
                "hostname": hostname_map.get(address, address),
            }

            # Config overrides
            if config.get("target_options"):
                assert type(config["target_options"]) is dict
                target |= config["target_options"]

            log.debug(f"Adding new address {address} ({target['hostname']}) from endpoint {owner}")

            updated_targets.append(target)

        # Finally, update the targets
        log.debug(f"Updated targets - old length {len(targets[module_name])} / new length {len(updated_targets)}")
        targets[module_name] = updated_targets


    ## Main loop
    while True:
        try:
            v1 = client.DiscoveryV1Api()
            w = watch.Watch()
            for event in w.stream(v1.list_namespaced_endpoint_slice, config.get('namespace'), label_selector=f"kubernetes.io/service-name={config.get('service_name')}"):
                if type(event) is not dict:
                    log.error(f"Caught event with an unexpected data type: {type(event)} - {event}")
                    continue

                kind = event['object'].kind
                if kind != "EndpointSlice":
                    log.error(f"Caught event with an unexpected object kind: {kind} (expected EndpointSlice) - {event}")
                    continue

                name = event['object'].metadata.name
                log.debug(f"Processing new {event['type']} event for {name} from the kube API: {event}")

                addresses = set()
                hostname_map = {}
                if event['type'] != 'DELETED':
                    for endpoint in event['object'].endpoints:
                        conditions = endpoint.conditions
                        # Skip endpoints not taking requests
                        if conditions.terminating or not conditions.ready or not conditions.serving:
                            log.debug(f"Skipping endpoint because it's not ready: {endpoint}")
                            continue
                        for address in endpoint.addresses:
                            hostname_map[address] = f"{endpoint.target_ref.name} / {endpoint.node_name}"
                        addresses |= set(endpoint.addresses)

                log.info(f"Got an updated address set for endpoint slice {name} with {len(addresses)} addresses")

                update_targets(name, addresses, hostname_map)

        except KeyboardInterrupt:
            break
        except BaseException:
            log.exception("Our kubernetes objects watch loop raised an exception. Restarting in 10 seconds...")
        else:
            log.error("Our kubernetes watch unexpectedly stopped. Restarting in 10 seconds...")
        sleep(10)
