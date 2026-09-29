"""Module for Iperf bandwidth test."""
import logging
import subprocess

from netprobify.protocol.target import Target

log_iperf = logging.getLogger(__name__)


def get_sum_from_stream(iterable, index):
    """Return sum from a column.

    Keyword arguments:
    iterable -- lists to iter on
    index -- column of the lists to sum up
    """
    return sum([int(line.split(",")[index]) for line in iterable])


class Iperf(Target):
    """Iperf target.

    Only iperf2 is supported. Iperf3 servers are missing multiple client feature.
    """

    def __init__(
        self,
        name,
        active,
        description,
        destination,
        config_destination,
        address_family,
        dst_port,
        threshold,
        state,
        alert_level,
        is_dynamic,
        dns_update_interval,
        groups,
        duration,
        bandwidth,
        protocol,
        num_streams,
        creation_date,
        lifetime,
    ):
        """Initialize.

        Keyword arguments:
        name -- name of the target
        active -- state of the target
        description -- short description of the target
        destination -- hostname or ip address to target
        config_destination -- original destination before DNS resolution
        address_family -- address family to use for probing
        duration -- duration of the iperf test
        dst_port -- destination port for TCP request
        bandwidth -- IP payload size to generate
        protocol -- protocol used by iperf (udp or tcp)
        is_dynamic -- if coming from a dynamic inventory. False if coming from the main config file.
        dns_update_interval -- interval for DNS resolution
        """
        Target.__init__(
            self,
            name,
            active,
            description,
            destination,
            config_destination,
            address_family,
            None,  # unused (dont_fragment)
            False,  # unused (is_subnet)
            None,  # unused (nb_packets)
            None,  # unused (interval)
            None,  # unused (timeout)
            None,  # unused (ip_payload_size)
            threshold,
            state,
            alert_level,
            is_dynamic,
            dns_update_interval,
            groups,
            creation_date,
            lifetime,
        )
        self.dst_port = dst_port
        self.duration = duration
        self.bandwidth = bandwidth
        self.protocol = "-u" if protocol == "udp" else None
        self.num_streams = num_streams
        self.is_special = True

    def send_packets(self, res, logging_level, *args):
        """Send the packets stored in self.packets.

        Keyword arguments:
        res -- variable to store results (manager list)
        logging_level -- logging level for targets class
        args -- to catch unused variable
        """
        # Build the command as an argument list and run it without a shell so
        # config-supplied values (destination, port, bandwidth, ...) can never
        # be interpreted as shell syntax. The UDP flag is only appended for UDP
        # targets; TCP runs must not receive a literal "None" argument.
        command = [
            "iperf",
            "-c", str(self.destination),
            "-p", str(self.dst_port),
        ]
        if self.protocol:
            command.append(self.protocol)
        command += [
            "-b", str(self.bandwidth),
            "-t", str(self.duration),
            "--reportexclude", "CDMS",
            "--reportstyle", "C",
            "-P", str(self.num_streams),
        ]
        try:
            iperf_results = subprocess.check_output(
                command,
                stderr=subprocess.DEVNULL,
                universal_newlines=True,
            )
        except subprocess.SubprocessError as error:
            log_iperf.error("iperf failed to proceed. Error is: {0}".format(error))
            return

        stream_results = [line for line in iperf_results.split("\n") if line]
        # get the results from the output
        try:
            res.append(
                {
                    "name": self.name,
                    "probing_type": "iperf",
                    "groups": self.groups,
                    "state": self.state,
                    "alert_level": self.alert_level,
                    "duration": self.duration,
                    "destination": self.destination,
                    "address_family": self.address_family,
                    "bandwidth": get_sum_from_stream(stream_results, 8),
                    "loss": get_sum_from_stream(stream_results, 10),
                    "sent": get_sum_from_stream(stream_results, 11),
                    "out_of_order": get_sum_from_stream(stream_results, 13),
                }
            )
        except (IndexError, ValueError) as error:
            log_iperf.warning("Invalid output from iperf: {}".format(error))
